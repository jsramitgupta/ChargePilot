import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.device import Device
from app.models.user import User
from app.services.smartlife_service import SmartLifeError, smartlife_service
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
async def scan_local_network(request: Request, db: Session = Depends(get_db)):
    _require_user(request, db)
    try:
        discovered = await TuyaService().discover()
    except RuntimeError as exc:
        logger.exception("Local device scan failed.")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    existing_ids = {
        device.device_id
        for device in db.query(Device.device_id).filter(
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
