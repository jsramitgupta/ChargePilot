import json
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.authorization import get_authenticated_user, is_super_admin_user
from app.core.config import settings
from app.models.endpoint import Endpoint
from app.models.messaging import TelemetryOutbox
from app.models.user import User
from app.schemas.telemetry import TelemetryPayload, TelemetryResponse
from app.services.endpoint_service import (
    authenticate_endpoint_token,
    authenticate_installed_endpoint,
)

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


@router.get("/stream")
async def stream_events(
    request: Request,
    user: User = Depends(get_authenticated_user),
):
    """Simple Server-Sent Events stream for device updates.

    Clients should connect with EventSource('/api/v1/telemetry/stream').
    """
    from starlette.responses import StreamingResponse
    import asyncio
    from app.services.broadcaster import register_client, unregister_client
    client_q = register_client()

    async def event_generator():
        try:
            while True:
                # If client disconnects, stop
                if await request.is_disconnected():
                    break
                try:
                    item = await asyncio.wait_for(client_q.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    # heartbeat
                    yield "event: ping\ndata: {}\n\n"
                    continue
                if not is_super_admin_user(user) and (
                    user.tenant_id is None or item.get("tenant_id") != user.tenant_id
                ):
                    continue
                data = json.dumps(item, default=str)
                yield f"data: {data}\n\n"
        finally:
            unregister_client(client_q)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.post("", response_model=TelemetryResponse)
async def receive_telemetry(
    payload: TelemetryPayload,
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
):
    timestamp = payload.timestamp
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)

    age_seconds = (datetime.now(UTC) - timestamp).total_seconds()
    if age_seconds > settings.telemetry_max_age_seconds:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Telemetry timestamp is too old.",
        )
    if age_seconds < -settings.telemetry_max_future_skew_seconds:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Telemetry timestamp is too far in the future.",
        )

    endpoint = authenticate_installed_endpoint(authorization, db)
    if endpoint is not None:
        if endpoint.platform != payload.platform or endpoint.installation_id != (
            str(payload.installation_id) if payload.installation_id else None
        ) or endpoint.device_class != payload.device_class or payload.hardware_uuid is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Telemetry identity does not match the enrolled endpoint.",
            )
        tenant = None
    else:
        is_valid, tenant = authenticate_endpoint_token(authorization, db)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing endpoint token.",
            )
        if payload.platform != "windows":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This platform must use its enrolled installation credential.",
            )
        endpoint = None

    hardware_uuid = str(payload.hardware_uuid) if payload.hardware_uuid else None
    if endpoint is None and hardware_uuid is not None:
        endpoint = (
            db.query(Endpoint)
            .filter(Endpoint.hardware_uuid == hardware_uuid)
            .first()
        )
        if endpoint is not None and endpoint.tenant_id != (tenant.id if tenant else None):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This hardware UUID is already registered to another tenant.",
            )

    endpoint_query = db.query(Endpoint)
    if tenant is None:
        endpoint_query = endpoint_query.filter(Endpoint.tenant_id.is_(None))
    else:
        endpoint_query = endpoint_query.filter(Endpoint.tenant_id == tenant.id)

    if endpoint is None:
        hostname_matches = endpoint_query.filter(
            Endpoint.hostname == payload.hostname,
        ).all()
        if hardware_uuid is not None:
            hostname_matches = [
                match for match in hostname_matches if match.hardware_uuid is None
            ]
        if len(hostname_matches) > 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Multiple endpoints share this hostname; send the hardware UUID to identify this laptop.",
            )
        endpoint = hostname_matches[0] if hostname_matches else None

    if endpoint is None and hardware_uuid is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="hardware_uuid is required to register a new laptop. Update the ChargePilot agent and retry.",
        )

    if endpoint is None:
        endpoint = Endpoint(
            name=payload.hostname,
            hostname=payload.hostname,
            tenant_id=tenant.id if tenant is not None else None,
            hardware_uuid=hardware_uuid,
            platform="windows",
            ip_address=payload.ip_address,
            battery_percentage=payload.battery_percentage,
            charging=payload.charging,
            ac_connected=payload.ac_connected,
            last_seen_at=timestamp,
            agent_version=payload.agent_version,
            enabled=True,
        )
        db.add(endpoint)
    is_newer_snapshot = endpoint.last_seen_at is None
    if endpoint.last_seen_at is not None:
        last_seen_at = endpoint.last_seen_at
        if last_seen_at.tzinfo is None:
            last_seen_at = last_seen_at.replace(tzinfo=UTC)
        is_newer_snapshot = timestamp >= last_seen_at

    if is_newer_snapshot:
        endpoint.name = payload.hostname
        endpoint.hostname = payload.hostname
        if hardware_uuid is not None:
            endpoint.hardware_uuid = hardware_uuid
        endpoint.ip_address = payload.ip_address
        endpoint.battery_percentage = payload.battery_percentage
        endpoint.charging = payload.charging
        endpoint.ac_connected = payload.ac_connected
        endpoint.last_seen_at = timestamp
        endpoint.agent_version = payload.agent_version
        endpoint.enabled = True

    if is_newer_snapshot:
        endpoint.updated_at = datetime.now(UTC)
    db.flush()
    event_id = str(uuid4())
    event_payload = payload.model_dump(mode="json")
    event_payload["endpoint_id"] = endpoint.id
    db.add(
        TelemetryOutbox(
            id=event_id,
            tenant_id=endpoint.tenant_id,
            aggregate_key=f"{endpoint.tenant_id or 'global'}:{endpoint.id}",
            payload_json=json.dumps(event_payload, separators=(",", ":")),
        )
    )
    db.commit()

    return TelemetryResponse(
        status="accepted",
        hostname=payload.hostname,
        hardware_uuid=payload.hardware_uuid,
        platform=payload.platform,
        battery_percentage=payload.battery_percentage,
        message="Telemetry accepted for asynchronous automation processing.",
    )
