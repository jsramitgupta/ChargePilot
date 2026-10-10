import asyncio
import json
import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.core.authorization import tenant_scoped_query
from app.core.database import get_db
from app.models.connector import DeviceCommand, SiteConnector
from app.models.device import Device
from app.models.user import User
from app.services.smartlife_service import SmartLifeError, smartlife_service
from app.services.connector_service import connector_is_online, queue_discovery_command
from app.services.tuya_service import TuyaService

logger = logging.getLogger("chargepilot.onboarding")
router = APIRouter(prefix="/devices", tags=["device onboarding"])


class SmartLifeLoginRequest(BaseModel):
    user_code: str = Field(min_length=1, max_length=120)
    qr_scheme: Literal["smartlife", "tuyaSmart"] = "smartlife"

    @field_validator("user_code")
    @classmethod
    def validate_user_code(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Smart Life user code cannot be blank.")
        return value


class SmartLifePreferenceRequest(BaseModel):
    user_code: str = Field(default="", max_length=120)
    remember: bool = False


class NetworkScanRequest(BaseModel):
    source: Literal["server", "connector"] = "server"
    connector_id: str | None = Field(default=None, max_length=36)


def _require_user(request: Request, db: Session) -> User:
    user_id = request.session.get("user_id")
    user = db.query(User).filter(User.id == user_id).first() if user_id else None
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    return user


@router.post("/smartlife/preferences")
async def save_smartlife_preference(
    payload: SmartLifePreferenceRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    user = _require_user(request, db)
    user_code = payload.user_code.strip()
    user.smartlife_user_code = user_code if payload.remember and user_code else None
    db.commit()
    return {"saved": user.smartlife_user_code is not None}


@router.post("/scan")
async def scan_local_network(
    request: Request,
    payload: NetworkScanRequest | None = None,
    db: Session = Depends(get_db),
):
    user = _require_user(request, db)
    payload = payload or NetworkScanRequest()
    if payload.source == "server":
        try:
            discovered = await TuyaService().discover()
        except RuntimeError as exc:
            logger.exception("TinyTuya scan on the ChargePilot server network failed.")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="ChargePilot could not scan the server's local network. Check LAN access and TinyTuya discovery traffic.",
            ) from exc
    else:
        connector_query = db.query(SiteConnector).filter(
            SiteConnector.is_active.is_(True),
            SiteConnector.token_hash.is_not(None),
        )
        if user.tenant_id is not None:
            connector_query = connector_query.filter(SiteConnector.tenant_id == user.tenant_id)
        if payload.connector_id:
            connector_query = connector_query.filter(SiteConnector.id == payload.connector_id)
        connectors = connector_query.order_by(SiteConnector.last_seen_at.desc().nullslast()).all()
        connector = next((item for item in connectors if connector_is_online(item)), None)
        if connector is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No active site connector is online for that tenant. Start a connector or scan the ChargePilot server network.",
            )

        command = queue_discovery_command(db, connector)
        db.commit()
        deadline = asyncio.get_running_loop().time() + 60
        while asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.5)
            db.expire_all()
            command = db.query(DeviceCommand).filter(DeviceCommand.id == command.id).first()
            if command is None:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Discovery command was lost.")
            if command.status in {"succeeded", "failed", "expired"}:
                result = json.loads(command.result_json or "{}")
                if command.status != "succeeded":
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail=result.get("error") or "Site connector could not complete LAN discovery.",
                    )
                discovered = result.get("devices", [])
                break
        else:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="The connector did not complete LAN discovery before the request timed out. Check connector status and try again.",
            )

    existing_query = db.query(Device.device_id)
    existing_query = tenant_scoped_query(existing_query, Device, user)
    existing_ids = {
        device_id
        for (device_id,) in existing_query.filter(
            Device.device_id.in_([item["device_id"] for item in discovered])
        )
    } if discovered else set()
    return {
        "devices": [
            {
                "name": item["name"],
                "device_id": item["device_id"],
                "ip_address": item["ip_address"],
                "protocol_version": item["protocol_version"],
                "device_type": item["device_type"],
                "already_added": item["device_id"] in existing_ids,
            }
            for item in discovered
        ]
    }


@router.post("/smartlife/start")
async def start_smartlife_login(
    payload: SmartLifeLoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    user = _require_user(request, db)
    try:
        return await smartlife_service.start_login(
            str(user.id),
            payload.user_code.strip(),
            payload.qr_scheme,
        )
    except SmartLifeError as exc:
        logger.warning("Could not start SmartLife pairing: %s", exc)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Could not start SmartLife pairing.")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not contact SmartLife to start pairing. Please try again.",
        ) from exc


@router.get("/smartlife/{login_id}")
async def poll_smartlife_login(
    login_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    user = _require_user(request, db)
    try:
        return await smartlife_service.poll_login(str(user.id), login_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except SmartLifeError as exc:
        logger.warning("Could not complete SmartLife pairing: %s", exc)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Could not complete SmartLife pairing.")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="SmartLife pairing could not be completed. Please restart the pairing flow.",
        ) from exc
