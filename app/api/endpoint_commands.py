from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.endpoint import Endpoint
from app.services.endpoint_service import authenticate_installed_endpoint
from app.services.endpoint_shutdown_service import (
    acknowledge_shutdown_command,
    claim_shutdown_command,
)

router = APIRouter(prefix="/endpoint-commands", tags=["endpoint commands"])


class ShutdownAcknowledgement(BaseModel):
    outcome: Literal["scheduled", "cancelled", "failed"]
    error: str | None = Field(default=None, max_length=255)


def _require_installed_endpoint(
    authorization: str | None,
    db: Session,
) -> Endpoint:
    endpoint = authenticate_installed_endpoint(authorization, db)
    if endpoint is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid enrolled endpoint credential is required.",
        )
    if (
        endpoint.platform not in {"windows", "macos"}
        or endpoint.installation_id is None
        or endpoint.tenant_id is None
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is not eligible to receive shutdown requests.",
        )
    return endpoint


@router.post("/claim")
async def claim_endpoint_command(
    response: Response,
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
):
    endpoint = _require_installed_endpoint(authorization, db)
    command = claim_shutdown_command(db, endpoint=endpoint)
    db.commit()
    response.headers["Cache-Control"] = "private, no-store"
    if command is None:
        return {"command": None}
    return {
        "command": {
            "id": command.id,
            "operation": "shutdown",
            "grace_period_seconds": 60,
            "expires_at": command.expires_at.isoformat(timespec="seconds"),
        }
    }


@router.post("/{command_id}/acknowledge")
async def acknowledge_endpoint_command(
    command_id: UUID,
    payload: ShutdownAcknowledgement,
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
):
    endpoint = _require_installed_endpoint(authorization, db)
    command = acknowledge_shutdown_command(
        db,
        endpoint=endpoint,
        command_id=str(command_id),
        outcome=payload.outcome,
        error=payload.error,
    )
    if command is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint command not found.")
    if command.status not in {"scheduled", "cancelled", "failed", "expired"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Endpoint command has not been claimed or has expired.",
        )
    db.commit()
    return {"status": command.status}
