from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.device import Device, DeviceChannel
from app.models.endpoint import Endpoint
from app.models.event import AutomationEvent
from app.models.mapping import Mapping
from app.schemas.telemetry import TelemetryPayload, TelemetryResponse
from app.services.endpoint_service import validate_endpoint_auth
from app.services.rule_engine import evaluate_battery_action
from app.services.tuya_service import TuyaService

router = APIRouter(prefix="/telemetry", tags=["telemetry"])

# Accept telemetry that is recent enough to be useful for dashboards and rules,
# while still rejecting clearly stale payloads from dead or misconfigured agents.
MAX_TELEMETRY_AGE_SECONDS = 60 * 60 * 24 * 7


@router.post("", response_model=TelemetryResponse)
async def receive_telemetry(
    payload: TelemetryPayload,
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
):
    if not validate_endpoint_auth(authorization):
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

    endpoint = db.query(Endpoint).filter(Endpoint.hostname == payload.hostname).first()
    if endpoint is None:
        endpoint = Endpoint(
            name=payload.hostname,
            hostname=payload.hostname,
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
        .filter(Mapping.endpoint_id == endpoint.id, Mapping.enabled.is_(True))
        .all()
    )

    for mapping in mappings:
        device = db.query(Device).filter(Device.id == mapping.device_id).first()
        if device is None:
            continue

        channel = None
        channel_index = 1
        if mapping.channel_id:
            channel = db.query(DeviceChannel).filter(DeviceChannel.id == mapping.channel_id).first()
            if channel is not None:
                channel_index = channel.channel_index

        current_state = bool(device.current_state)
        live_status = await TuyaService.from_device(device).get_status(device.device_id, channel=channel_index)
        if isinstance(live_status, dict) and "state" in live_status and live_status.get("online", True):
            current_state = bool(live_status["state"])

        if payload.switch_state is not None:
            requested_state = bool(payload.switch_state)
            if requested_state != current_state:
                decision = "TURN_ON" if requested_state else "TURN_OFF"
            else:
                decision = "NO_ACTION"
        else:
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

        db.add(
            AutomationEvent(
                event_type=decision,
                reason=f"battery {payload.battery_percentage}% reached {mapping.on_threshold if decision == 'TURN_ON' else mapping.off_threshold}% rule",
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

    return TelemetryResponse(
        status="accepted",
        hostname=payload.hostname,
        battery_percentage=payload.battery_percentage,
        message="Telemetry accepted and endpoint updated.",
    )
