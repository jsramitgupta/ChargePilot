import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.device import Device, DeviceChannel
from app.models.endpoint import Endpoint
from app.models.event import AutomationEvent
from app.models.mapping import Mapping
from app.models.messaging import TelemetryAutomationCursor
from app.schemas.telemetry import TelemetryPayload
from app.services.broadcaster import publish_event
from app.services.connector_service import queue_device_command
from app.services.rule_engine import evaluate_battery_action
from app.services.telemetry_policy import (
    telemetry_freshness_limit_seconds,
    tenant_reporting_interval_minutes,
)
from app.services.tuya_service import TuyaService, coerce_switch_state

logger = logging.getLogger("chargepilot.automation")


def _automation_reason(
    decision: str,
    *,
    battery: int,
    is_charging: bool,
    mapping: Mapping,
) -> str:
    if decision == "TURN_ON":
        return (
            f"Battery {battery}% is at or below "
            f"the turn-on threshold of {mapping.on_threshold}%."
        )
    if (
        mapping.turn_off_when_charging_enabled
        and is_charging
        and battery >= mapping.charging_off_threshold
    ):
        return (
            f"Battery {battery}% is charging and at or above "
            f"the charging turn-off threshold of {mapping.charging_off_threshold}%."
        )
    return (
        f"Battery {battery}% is at or above "
        f"the turn-off threshold of {mapping.off_threshold}%."
    )


async def process_telemetry_event(
    db: Session,
    *,
    event_id: str,
    endpoint_id: str,
    tenant_id: str | None,
    payload: TelemetryPayload,
) -> bool:
    cursor = db.get(TelemetryAutomationCursor, endpoint_id)
    if cursor is not None and cursor.last_event_id == event_id:
        return False

    endpoint = (
        db.query(Endpoint)
        .filter(Endpoint.id == endpoint_id, Endpoint.tenant_id == tenant_id)
        .first()
    )
    if endpoint is None:
        raise ValueError("Telemetry event references an unavailable endpoint.")

    event_timestamp = payload.timestamp
    if event_timestamp.tzinfo is None:
        event_timestamp = event_timestamp.replace(tzinfo=UTC)
    if cursor is not None:
        cursor_timestamp = cursor.last_telemetry_at
        if cursor_timestamp.tzinfo is None:
            cursor_timestamp = cursor_timestamp.replace(tzinfo=UTC)
        if event_timestamp < cursor_timestamp:
            return False

    now = datetime.now(UTC)
    sample_age_seconds = (now - event_timestamp).total_seconds()
    reporting_interval_minutes = tenant_reporting_interval_minutes(db, endpoint.tenant_id)
    automation_eligible = (
        endpoint.automation_enabled
        and endpoint.platform in settings.automation_telemetry_platforms
        and -settings.telemetry_max_future_skew_seconds
        <= sample_age_seconds
        <= telemetry_freshness_limit_seconds(reporting_interval_minutes)
    )

    state_changes = []
    mappings = []
    if automation_eligible:
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
                .filter(
                    DeviceChannel.id == mapping.channel_id,
                    DeviceChannel.device_id == device.id,
                )
                .first()
            )
            if channel is not None:
                channel_index = channel.channel_index

        if device.connector_id:
            try:
                queue_device_command(
                    db,
                    device=device,
                    operation="get_status",
                    channel_index=channel_index,
                    channel_id=mapping.channel_id,
                    context={"automation_reconcile": True},
                )
            except ValueError as exc:
                logger.warning("Could not queue switch status check for device %s: %s", device.id, exc)
            continue

        current_state = bool(
            channel.current_state if channel is not None else device.current_state
        )
        live_status = await TuyaService.from_device(device).get_status(
            device.device_id,
            channel=channel_index,
        )
        live_state = (
            coerce_switch_state(live_status.get("state"))
            if isinstance(live_status, dict)
            else None
        )
        if (
            not isinstance(live_status, dict)
            or live_state is None
            or not live_status.get("online", True)
        ):
            logger.warning(
                "Skipping battery automation for device %s because live switch status is unavailable.",
                device.id,
            )
            continue
        current_state = live_state

        decision = evaluate_battery_action(
            battery=payload.battery_percentage,
            current_state=current_state,
            turn_on_enabled=mapping.turn_on_enabled,
            is_charging=payload.charging,
            turn_off_when_charging_enabled=mapping.turn_off_when_charging_enabled,
            on_threshold=mapping.on_threshold,
            off_threshold=mapping.off_threshold,
            charging_off_threshold=mapping.charging_off_threshold,
            minimum_interval_seconds=mapping.minimum_state_change_interval,
            last_state_change_at=device.last_state_change_at,
            now=datetime.now(UTC),
        )
        if decision == "NO_ACTION":
            continue

        new_state = decision == "TURN_ON"
        reason = _automation_reason(
            decision,
            battery=payload.battery_percentage,
            is_charging=payload.charging,
            mapping=mapping,
        )

        action_result = await TuyaService.from_device(device).set_state(
            device_id=device.device_id,
            on=new_state,
            channel=channel_index,
        )
        previous_state = device.current_state
        success = bool(action_result.get("success", False))
        if success:
            now = datetime.now(UTC)
            device.current_state = new_state
            device.last_state_change_at = now
            device.updated_at = now
            if channel is not None:
                channel.current_state = new_state

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
                success=success,
                error=(
                    None
                    if success
                    else str(action_result.get("error") or "Local device command failed.")[:255]
                ),
            )
        )
        if success:
            state_changes.append(
                {
                    "type": "device_state_change",
                    "tenant_id": endpoint.tenant_id,
                    "device_id": device.id,
                    "channel_id": mapping.channel_id,
                    "previous_state": previous_state,
                    "new_state": new_state,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )

    if cursor is None:
        db.add(
            TelemetryAutomationCursor(
                endpoint_id=endpoint_id,
                last_event_id=event_id,
                last_telemetry_at=event_timestamp,
                updated_at=datetime.now(UTC),
            )
        )
    else:
        cursor.last_event_id = event_id
        cursor.last_telemetry_at = event_timestamp
        cursor.updated_at = datetime.now(UTC)
    db.commit()

    for event in state_changes:
        publish_event(event)
    return True


def reconcile_connector_status(
    db: Session,
    *,
    connector_id: str,
    device_id: str,
    tenant_id: str,
    channel_id: str | None,
    current_state: bool,
) -> None:
    device = (
        db.query(Device)
        .filter(
            Device.id == device_id,
            Device.tenant_id == tenant_id,
            Device.connector_id == connector_id,
            Device.enabled.is_(True),
        )
        .first()
    )
    if device is None:
        return

    now = datetime.now(UTC)
    mappings = (
        db.query(Mapping)
        .filter(
            Mapping.device_id == device.id,
            Mapping.tenant_id == tenant_id,
            Mapping.channel_id == channel_id,
            Mapping.enabled.is_(True),
        )
        .all()
    )
    for mapping in mappings:
        channel = None
        if mapping.channel_id:
            channel = (
                db.query(DeviceChannel)
                .filter(
                    DeviceChannel.id == mapping.channel_id,
                    DeviceChannel.device_id == device.id,
                )
                .first()
            )
            if channel is None:
                continue
        endpoint = (
            db.query(Endpoint)
            .filter(
                Endpoint.id == mapping.endpoint_id,
                Endpoint.tenant_id == tenant_id,
                Endpoint.enabled.is_(True),
                Endpoint.automation_enabled.is_(True),
                Endpoint.platform.in_(settings.automation_telemetry_platforms),
            )
            .first()
        )
        if endpoint is None or endpoint.last_seen_at is None:
            continue
        last_seen_at = endpoint.last_seen_at
        if last_seen_at.tzinfo is None:
            last_seen_at = last_seen_at.replace(tzinfo=UTC)
        sample_age_seconds = (now - last_seen_at).total_seconds()
        reporting_interval_minutes = tenant_reporting_interval_minutes(db, tenant_id)
        if not (
            -settings.telemetry_max_future_skew_seconds
            <= sample_age_seconds
            <= telemetry_freshness_limit_seconds(reporting_interval_minutes)
        ):
            continue

        decision = evaluate_battery_action(
            battery=endpoint.battery_percentage,
            current_state=current_state,
            turn_on_enabled=mapping.turn_on_enabled,
            is_charging=endpoint.charging,
            turn_off_when_charging_enabled=mapping.turn_off_when_charging_enabled,
            on_threshold=mapping.on_threshold,
            off_threshold=mapping.off_threshold,
            charging_off_threshold=mapping.charging_off_threshold,
            minimum_interval_seconds=mapping.minimum_state_change_interval,
            last_state_change_at=device.last_state_change_at,
            now=now,
        )
        if decision == "NO_ACTION":
            continue

        new_state = decision == "TURN_ON"
        reason = _automation_reason(
            decision,
            battery=endpoint.battery_percentage,
            is_charging=endpoint.charging,
            mapping=mapping,
        )

        try:
            queue_device_command(
                db,
                device=device,
                operation="set_state",
                channel_index=channel.channel_index if channel is not None else 1,
                channel_id=mapping.channel_id,
                desired_state=new_state,
                context={
                    "event_type": decision,
                    "reason": reason,
                    "endpoint_id": endpoint.id,
                    "battery_percentage": endpoint.battery_percentage,
                    "previous_state": str(current_state).lower(),
                    "new_state": str(new_state).lower(),
                },
            )
        except ValueError as exc:
            logger.warning("Could not queue automation for device %s: %s", device.id, exc)
            db.add(
                AutomationEvent(
                    tenant_id=tenant_id,
                    event_type=decision,
                    reason=reason,
                    endpoint_id=endpoint.id,
                    device_id=device.id,
                    channel_id=mapping.channel_id,
                    battery_percentage=endpoint.battery_percentage,
                    previous_state=str(current_state).lower(),
                    new_state=str(new_state).lower(),
                    success=False,
                    error=str(exc)[:255],
                )
            )
