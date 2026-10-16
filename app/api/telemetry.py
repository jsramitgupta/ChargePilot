import json
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.authorization import get_authenticated_user, is_super_admin_user
from app.models.endpoint import Endpoint
from app.models.messaging import TelemetryOutbox
from app.models.user import User
from app.schemas.telemetry import TelemetryPayload, TelemetryResponse
from app.services.endpoint_service import authenticate_endpoint_token

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

# Accept telemetry that is recent enough to be useful for dashboards and rules,
# while still rejecting clearly stale payloads from dead or misconfigured agents.
MAX_TELEMETRY_AGE_SECONDS = 60 * 60 * 24 * 7


@router.post("", response_model=TelemetryResponse)
async def receive_telemetry(
    payload: TelemetryPayload,
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
):
    is_valid, tenant = authenticate_endpoint_token(authorization, db)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing endpoint token.",
        )

    timestamp = payload.timestamp
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)

    age_seconds = (datetime.now(UTC) - timestamp).total_seconds()
    if age_seconds > MAX_TELEMETRY_AGE_SECONDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Telemetry timestamp is too old.",
        )

    endpoint_query = db.query(Endpoint).filter(Endpoint.hostname == payload.hostname)
    if tenant is not None:
        endpoint_query = endpoint_query.filter(Endpoint.tenant_id == tenant.id)
    endpoint = endpoint_query.first()
    if endpoint is None:
        endpoint = Endpoint(
            name=payload.hostname,
            hostname=payload.hostname,
            tenant_id=tenant.id if tenant is not None else None,
            ip_address=payload.ip_address,
            battery_percentage=payload.battery_percentage,
            charging=payload.charging,
            ac_connected=payload.ac_connected,
            last_seen_at=timestamp,
            agent_version=payload.agent_version,
            enabled=True,
        )
        db.add(endpoint)
    else:
        endpoint.name = payload.hostname
        endpoint.ip_address = payload.ip_address
        endpoint.battery_percentage = payload.battery_percentage
        endpoint.charging = payload.charging
        endpoint.ac_connected = payload.ac_connected
        endpoint.last_seen_at = timestamp
        endpoint.agent_version = payload.agent_version
        endpoint.enabled = True

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
        battery_percentage=payload.battery_percentage,
        message="Telemetry accepted for asynchronous automation processing.",
    )
