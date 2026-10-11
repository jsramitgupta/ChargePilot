import hmac
import json
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.authorization import get_authenticated_user, is_super_admin_user, tenant_scoped_query
from app.core.database import get_db
from app.core.security import get_bearer_token, generate_token
from app.models.connector import DeviceCommand, SiteConnector
from app.models.device import Device
from app.models.user import User
from app.services.connector_service import (
    claim_next_command,
    finalize_command,
    hash_connector_token,
)
from app.services.broadcaster import publish_event

router = APIRouter(prefix="/connectors", tags=["site connectors"])


class EnrollmentRequest(BaseModel):
    version: str = Field(default="unknown", max_length=40)


class HeartbeatRequest(BaseModel):
    version: str = Field(default="unknown", max_length=40)


class CommandResultRequest(BaseModel):
    success: bool
    result: dict = Field(default_factory=dict)
    error: str | None = Field(default=None, max_length=255)


@router.get("")
async def list_connectors(
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    connectors = tenant_scoped_query(db.query(SiteConnector), SiteConnector, user).order_by(
        SiteConnector.name.asc()
    ).all()
    return [
        {
            "id": connector.id,
            "name": connector.name,
            "tenant_id": connector.tenant_id,
            "is_active": connector.is_active,
            "is_enrolled": connector.token_hash is not None,
            "is_online": connector_is_online(connector),
            "last_seen_at": connector.last_seen_at,
        }
        for connector in connectors
    ]


def _connector_from_auth(
    authorization: str | None,
    db: Session,
) -> SiteConnector:
    token = get_bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Connector credential required.")
    candidate = hash_connector_token(token)
    connector = db.query(SiteConnector).filter(SiteConnector.token_hash.is_not(None)).all()
    match = next(
        (item for item in connector if hmac.compare_digest(item.token_hash or "", candidate)),
        None,
    )
    if match is None or not match.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or revoked connector credential.")
    return match


@router.post("/enroll")
async def enroll_connector(
    payload: EnrollmentRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
):
    enrollment_token = get_bearer_token(authorization)
    if not enrollment_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Enrollment code required.")
    candidate = hash_connector_token(enrollment_token)
    connector = (
        db.query(SiteConnector)
        .filter(SiteConnector.enrollment_token_hash == candidate)
        .with_for_update()
        .first()
    )
    now = datetime.now(UTC)
    match = connector
    expires_at = match.enrollment_expires_at if match is not None else None
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if (
        match is not None
        and (
            not match.is_active
            or expires_at is None
            or expires_at <= now
            or match.token_hash is not None
            or not hmac.compare_digest(match.enrollment_token_hash or "", candidate)
        )
    ):
        match = None
    if match is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Enrollment code is invalid, expired, or already used.")

    token = generate_token()
    match.enrollment_token_hash = None
    match.enrollment_expires_at = None
    match.token_hash = hash_connector_token(token)
    match.version = payload.version
    match.last_seen_at = now
    db.commit()
    return {"connector_id": match.id, "name": match.name, "token": token}


@router.post("/heartbeat")
async def connector_heartbeat(
    payload: HeartbeatRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
):
    connector = _connector_from_auth(authorization, db)
    connector.last_seen_at = datetime.now(UTC)
    connector.version = payload.version
    db.commit()
    return {"status": "ok", "server_time": datetime.now(UTC).isoformat()}


@router.post("/commands/claim")
async def claim_command(
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
):
    connector = _connector_from_auth(authorization, db)
    connector.last_seen_at = datetime.now(UTC)
    command = claim_next_command(db, connector)
    return {"command": command}


@router.post("/commands/{command_id}/result")
async def submit_command_result(
    command_id: UUID,
    payload: CommandResultRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
):
    connector = _connector_from_auth(authorization, db)
    command = (
        db.query(DeviceCommand)
        .filter(
            DeviceCommand.id == str(command_id),
            DeviceCommand.connector_id == connector.id,
            DeviceCommand.tenant_id == connector.tenant_id,
        )
        .first()
    )
    if command is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Command not found.")
    if command.status in {"succeeded", "failed", "expired"}:
        return {"status": command.status}
    if command.status != "leased":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Command has not been claimed.")
    if command.expires_at.tzinfo is None:
        command.expires_at = command.expires_at.replace(tzinfo=UTC)
    if command.expires_at <= datetime.now(UTC):
        finalize_command(db, command, success=False, error="Command expired before acknowledgement.")
        db.commit()
        return {"status": "expired"}

    result_json = json.dumps(payload.result, default=str)
    if len(result_json) > 32_000:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Command result is too large.")
    finalize_command(
        db,
        command,
        success=payload.success,
        result=payload.result,
        error=payload.error,
    )
    connector.last_seen_at = datetime.now(UTC)
    db.commit()
    if command.device_id:
        publish_event(
            {
                "type": "device_state_change" if payload.success else "device_command_completed",
                "tenant_id": command.tenant_id,
                "device_id": command.device_id,
                "channel_id": command.channel_id,
                "previous_state": json.loads(command.context_json or "{}").get("previous_state"),
                "new_state": json.loads(command.context_json or "{}").get("new_state"),
                "command_status": command.status,
                "timestamp": command.completed_at.isoformat() if command.completed_at else None,
            }
        )
    return {"status": command.status}


@router.get("/commands/{command_id}")
async def read_command(
    command_id: UUID,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    command = tenant_scoped_query(db.query(DeviceCommand), DeviceCommand, user).filter(
        DeviceCommand.id == str(command_id)
    ).first()
    if command is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Command not found.")
    return {
        "id": command.id,
        "status": command.status,
        "result": json.loads(command.result_json) if command.result_json else None,
        "created_at": command.created_at,
        "completed_at": command.completed_at,
    }


@router.post("/{connector_id}/revoke")
async def revoke_connector(
    connector_id: UUID,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    connector = tenant_scoped_query(db.query(SiteConnector), SiteConnector, user).filter(
        SiteConnector.id == str(connector_id)
    ).first()
    if connector is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector not found.")
    if not is_super_admin_user(user) and (user.tenant_id != connector.tenant_id or user.role not in {"tenant_admin", "manager"}):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Connector administration permission required.")
    connector.is_active = False
    connector.token_hash = None
    connector.enrollment_token_hash = None
    connector.enrollment_expires_at = None
    for device in db.query(Device).filter(Device.connector_id == connector.id).all():
        device.connector_id = None
    db.commit()
    return {"status": "revoked"}
