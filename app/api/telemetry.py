import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.authorization import get_authenticated_user, is_super_admin_user
from app.models.device import Device, DeviceChannel
from app.models.endpoint import Endpoint
from app.models.event import AutomationEvent
from app.models.mapping import Mapping
from app.models.user import User
from app.schemas.telemetry import TelemetryPayload, TelemetryResponse
from app.services.endpoint_service import authenticate_endpoint_token
from app.services.rule_engine import evaluate_battery_action
from app.services.tuya_service import TuyaService
from app.services.broadcaster import publish_event

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
    db.commit()
    db.refresh(endpoint)

    mappings = (
        db.query(Mapping)
        .filter(
            Mapping.endpoint_id == endpoint.id,
            Mapping.tenant_id == endpoint.tenant_id,
            Mapping.enabled.is_(True),
        )
        .all()
    )

    for mapping in mappings:
        device = (
            db.query(Device)
            .filter(Device.id == mapping.device_id, Device.tenant_id == endpoint.tenant_id)
            .first()
        )
        if device is None:
            continue

        channel = None
        channel_index = 1
        if mapping.channel_id:
            channel = (
                db.query(DeviceChannel)
                .filter(DeviceChannel.id == mapping.channel_id, DeviceChannel.device_id == device.id)
                .first()
            )
            if channel is not None:
                channel_index = channel.channel_index

        current_state = bool(device.current_state)
        live_status = await TuyaService.from_device(device).get_status(device.device_id, channel=channel_index)
        if isinstance(live_status, dict) and "state" in live_status and live_status.get("online", True):
            current_state = bool(live_status["state"])

        decision = evaluate_battery_action(
            battery=payload.battery_percentage,
            current_state=current_state,
            on_threshold=mapping.on_threshold,
            off_threshold=mapping.off_threshold,
            minimum_interval_seconds=mapping.minimum_state_change_interval,
            last_state_change_at=device.last_state_change_at,
            now=datetime.now(UTC),
        )

        if decision == "NO_ACTION":
            continue

        action_result = await TuyaService.from_device(device).set_state(
            device_id=device.device_id,
            on=decision == "TURN_ON",
            channel=channel_index,
        )

        previous_state = device.current_state
        new_state = decision == "TURN_ON"
        device.current_state = new_state
        device.last_state_change_at = datetime.now(UTC)
        device.updated_at = datetime.now(UTC)

        if decision == "TURN_ON":
            reason = (
                f"Battery {payload.battery_percentage}% is at or below "
                f"the turn-on threshold of {mapping.on_threshold}%."
            )
        else:
            reason = (
                f"Battery {payload.battery_percentage}% is at or above "
                f"the turn-off threshold of {mapping.off_threshold}%."
            )

        db.add(
            AutomationEvent(
                tenant_id=endpoint.tenant_id,
                event_type=decision,
                reason=reason,
                endpoint_id=endpoint.id,
                device_id=device.id,
                channel_id=mapping.channel_id,
                battery_percentage=payload.battery_percentage,
                previous_state=str(previous_state).lower(),
                new_state=str(new_state).lower(),
                success=bool(action_result.get("success", True)),
                error=None if action_result.get("success", True) else action_result.get("error"),
            )
        )
        db.commit()
        # Publish device state change event for SSE clients
        try:
            publish_event({
                "type": "device_state_change",
                "tenant_id": endpoint.tenant_id,
                "device_id": device.id,
                "channel_id": mapping.channel_id,
                "previous_state": previous_state,
                "new_state": new_state,
                "timestamp": datetime.now(UTC).isoformat(),
            })
        except Exception:
            pass

    return TelemetryResponse(
        status="accepted",
        hostname=payload.hostname,
        battery_percentage=payload.battery_percentage,
        message="Telemetry accepted and endpoint updated.",
    )
