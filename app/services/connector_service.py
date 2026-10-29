import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.connector import DeviceCommand, SiteConnector
from app.models.device import Device, DeviceChannel
from app.models.endpoint import Endpoint
from app.models.event import AutomationEvent
from app.models.mapping import Mapping
from app.services.local_key_service import decrypt_local_key
from app.services.tuya_energy import apply_meter_result
from app.services.telemetry_policy import (
    telemetry_freshness_limit_seconds,
    tenant_reporting_interval_minutes,
)

COMMAND_TTL = timedelta(minutes=5)
COMMAND_LEASE = timedelta(seconds=60)
MAX_COMMAND_ATTEMPTS = 5
CONNECTOR_ONLINE_WINDOW = timedelta(seconds=90)
METER_POLL_INTERVAL = timedelta(seconds=60)
MAPPING_STATUS_POLL_INTERVAL = timedelta(seconds=60)


def _notify_connector_command_available(db: Session, connector_id: str) -> None:
    if db.get_bind().dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_notify('chargepilot_connector_commands', :connector_id)"),
            {"connector_id": connector_id},
        )


def hash_connector_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def queue_device_command(
    db: Session,
    *,
    device: Device,
    operation: str,
    channel_index: int | None = None,
    channel_id: str | None = None,
    desired_state: bool | None = None,
    context: dict | None = None,
) -> DeviceCommand:
    if operation not in {"set_state", "get_status", "inspect_meter", "discover"}:
        raise ValueError("Unsupported connector command.")
    if operation == "set_state" and desired_state is None:
        raise ValueError("Desired state is required for a state command.")
    if not device.enabled:
        raise ValueError("The switch is disabled.")
    if not device.connector_id:
        raise ValueError("Assign this switch to a site connector before using cloud control.")
    connector = (
        db.query(SiteConnector)
        .filter(
            SiteConnector.id == device.connector_id,
            SiteConnector.tenant_id == device.tenant_id,
            SiteConnector.is_active.is_(True),
            SiteConnector.token_hash.is_not(None),
        )
        .first()
    )
    if connector is None:
        raise ValueError("The assigned site connector is not enrolled or active.")

    if operation in {"set_state", "get_status", "inspect_meter"}:
        outstanding = (
            db.query(DeviceCommand)
            .filter(
                DeviceCommand.device_id == device.id,
                DeviceCommand.channel_id == channel_id,
                DeviceCommand.operation == operation,
                DeviceCommand.status.in_(("queued", "leased")),
                DeviceCommand.expires_at > datetime.now(UTC),
            )
            .first()
        )
        if outstanding is not None:
            if operation == "get_status":
                if context:
                    existing_context = json.loads(outstanding.context_json or "{}")
                    existing_context.update(context)
                    outstanding.context_json = json.dumps(existing_context)
                return outstanding
            if outstanding.desired_state == desired_state:
                return outstanding
            raise ValueError("A different switch command is already pending for this channel.")

    command = DeviceCommand(
        id=str(uuid4()),
        tenant_id=device.tenant_id,
        connector_id=connector.id,
        device_id=device.id if operation != "discover" else None,
        channel_id=channel_id,
        operation=operation,
        desired_state=desired_state,
        channel_index=channel_index,
        context_json=json.dumps(context or {}),
        status="queued",
        expires_at=datetime.now(UTC) + COMMAND_TTL,
    )
    db.add(command)
    db.flush()
    _notify_connector_command_available(db, connector.id)
    return command


def queue_discovery_command(db: Session, connector: SiteConnector) -> DeviceCommand:
    if (
        not connector.is_active
        or connector.token_hash is None
        or not connector.tenant_id
    ):
        raise ValueError("The site connector is not enrolled and active.")
    command = DeviceCommand(
        tenant_id=connector.tenant_id,
        connector_id=connector.id,
        operation="discover",
        context_json="{}",
        status="queued",
        expires_at=datetime.now(UTC) + COMMAND_TTL,
    )
    db.add(command)
    db.flush()
    _notify_connector_command_available(db, connector.id)
    return command


def connector_is_online(connector: SiteConnector, now: datetime | None = None) -> bool:
    if not connector.is_active or connector.last_seen_at is None:
        return False
    now = now or datetime.now(UTC)
    last_seen = connector.last_seen_at
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=UTC)
    return now - last_seen <= CONNECTOR_ONLINE_WINDOW


def expire_overdue_commands(db: Session) -> int:
    now = datetime.now(UTC)
    commands = (
        db.query(DeviceCommand)
        .filter(
            DeviceCommand.status.in_(("queued", "leased")),
            DeviceCommand.expires_at <= now,
        )
        .with_for_update(skip_locked=True)
        .all()
    )
    for command in commands:
        finalize_command(db, command, success=False, error="Command expired before execution.")
    if commands:
        db.commit()
    return len(commands)


def _queue_due_meter_poll(db: Session, connector: SiteConnector, now: datetime) -> bool:
    cutoff = now - METER_POLL_INTERVAL
    device = (
        db.query(Device)
        .filter(
            Device.connector_id == connector.id,
            Device.tenant_id == connector.tenant_id,
            Device.enabled.is_(True),
            or_(Device.power_dp_id.is_not(None), Device.energy_dp_id.is_not(None)),
            or_(Device.meter_last_sample_at.is_(None), Device.meter_last_sample_at <= cutoff),
            or_(Device.meter_poll_requested_at.is_(None), Device.meter_poll_requested_at <= cutoff),
        )
        .order_by(Device.meter_last_sample_at.asc().nullsfirst(), Device.created_at.asc())
        .with_for_update(skip_locked=True)
        .first()
    )
    if device is None:
        return False

    queue_device_command(
        db,
        device=device,
        operation="get_status",
        channel_index=1,
        context={"meter_poll": True},
    )
    device.meter_poll_requested_at = now
    db.flush()
    return True


def _queue_due_automation_status_poll(
    db: Session,
    connector: SiteConnector,
    now: datetime,
) -> bool:
    cutoff = now - MAPPING_STATUS_POLL_INTERVAL
    channel_matches = or_(
        and_(
            Mapping.channel_id.is_(None),
            DeviceCommand.channel_id.is_(None),
        ),
        DeviceCommand.channel_id == Mapping.channel_id,
    )
    latest_status_at = (
        select(func.max(DeviceCommand.completed_at))
        .where(
            DeviceCommand.device_id == Mapping.device_id,
            DeviceCommand.operation == "get_status",
            channel_matches,
        )
        .correlate(Mapping)
        .scalar_subquery()
    )
    pending_status = (
        select(DeviceCommand.id)
        .where(
            DeviceCommand.device_id == Mapping.device_id,
            DeviceCommand.operation == "get_status",
            DeviceCommand.status.in_(("queued", "leased")),
            DeviceCommand.expires_at > now,
            channel_matches,
        )
        .exists()
    )
    candidates = (
        db.query(Mapping, Device, Endpoint)
        .join(
            Device,
            and_(
                Device.id == Mapping.device_id,
                Device.tenant_id == Mapping.tenant_id,
            ),
        )
        .join(
            Endpoint,
            and_(
                Endpoint.id == Mapping.endpoint_id,
                Endpoint.tenant_id == Mapping.tenant_id,
            ),
        )
        .filter(
            Mapping.tenant_id == connector.tenant_id,
            Mapping.enabled.is_(True),
            Device.connector_id == connector.id,
            Device.enabled.is_(True),
            Endpoint.enabled.is_(True),
            Endpoint.automation_enabled.is_(True),
            Endpoint.platform.in_(settings.automation_telemetry_platforms),
            Endpoint.last_seen_at.is_not(None),
            Endpoint.last_seen_at >= now - timedelta(seconds=settings.telemetry_max_age_seconds),
            ~pending_status,
            or_(latest_status_at.is_(None), latest_status_at <= cutoff),
        )
        .order_by(latest_status_at.asc().nullsfirst(), Mapping.created_at.asc())
        .limit(100)
        .all()
    )

    for mapping, device, endpoint in candidates:
        last_seen_at = endpoint.last_seen_at
        if last_seen_at.tzinfo is None:
            last_seen_at = last_seen_at.replace(tzinfo=UTC)
        sample_age_seconds = (now - last_seen_at).total_seconds()
        reporting_interval_minutes = tenant_reporting_interval_minutes(db, endpoint.tenant_id)
        if not (
            -settings.telemetry_max_future_skew_seconds
            <= sample_age_seconds
            <= telemetry_freshness_limit_seconds(reporting_interval_minutes)
        ):
            continue

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
            if channel is None:
                continue
            channel_index = channel.channel_index

        queue_device_command(
            db,
            device=device,
            operation="get_status",
            channel_index=channel_index,
            channel_id=mapping.channel_id,
            context={"automation_reconcile": True},
        )
        db.flush()
        return True
    return False


def claim_next_command(db: Session, connector: SiteConnector) -> dict | None:
    now = datetime.now(UTC)
    expired = (
        db.query(DeviceCommand)
        .filter(
            DeviceCommand.connector_id == connector.id,
            DeviceCommand.status.in_(("queued", "leased")),
            DeviceCommand.expires_at <= now,
        )
        .all()
    )
    for command in expired:
        finalize_command(db, command, success=False, error="Command expired before execution.")

    eligible = db.query(DeviceCommand).filter(
        DeviceCommand.connector_id == connector.id,
        DeviceCommand.expires_at > now,
        (
            (DeviceCommand.status == "queued")
            | (
                (DeviceCommand.status == "leased")
                & (DeviceCommand.lease_expires_at <= now)
                & (DeviceCommand.attempts < MAX_COMMAND_ATTEMPTS)
            )
        ),
    )
    command = eligible.order_by(DeviceCommand.created_at.asc()).with_for_update(skip_locked=True).first()
    if command is None:
        if _queue_due_automation_status_poll(db, connector, now):
            command = eligible.order_by(DeviceCommand.created_at.asc()).with_for_update(skip_locked=True).first()
    if command is None:
        if _queue_due_meter_poll(db, connector, now):
            command = eligible.order_by(DeviceCommand.created_at.asc()).with_for_update(skip_locked=True).first()
    if command is None:
        exhausted = (
            db.query(DeviceCommand)
            .filter(
                DeviceCommand.connector_id == connector.id,
                DeviceCommand.status == "leased",
                DeviceCommand.lease_expires_at <= now,
                DeviceCommand.attempts >= MAX_COMMAND_ATTEMPTS,
            )
            .all()
        )
        for expired_command in exhausted:
            finalize_command(
                db, expired_command, success=False, error="Connector command exceeded its retry limit."
            )
        db.commit()
        return None

    command.status = "leased"
    command.attempts += 1
    command.lease_expires_at = now + COMMAND_LEASE
    payload = {
        "id": command.id,
        "operation": command.operation,
        "device_id": command.device_id,
        "channel_id": command.channel_id,
        "channel_index": command.channel_index,
        "desired_state": command.desired_state,
        "expires_at": command.expires_at.isoformat(),
        "attempt": command.attempts,
    }
    if command.device_id:
        device = (
            db.query(Device)
            .filter(
                Device.id == command.device_id,
                Device.connector_id == connector.id,
                Device.tenant_id == connector.tenant_id,
            )
            .first()
        )
        if device is None:
            finalize_command(db, command, success=False, error="Assigned device is no longer available.")
            db.commit()
            return None
        if not device.enabled or not device.ip_address:
            finalize_command(db, command, success=False, error="Assigned device is disabled or missing its local IP address.")
            db.commit()
            return None
        try:
            local_key = decrypt_local_key(device.encrypted_local_key)
        except RuntimeError:
            finalize_command(db, command, success=False, error="Could not decrypt the registered device local key.")
            db.commit()
            return None
        payload["device"] = {
            "device_id": device.device_id,
            "ip_address": device.ip_address,
            "local_key": local_key,
            "device_type": device.device_type or "default",
            "protocol_version": device.protocol_version or "3.5",
            "power_dp_id": device.power_dp_id,
            "power_multiplier": device.power_multiplier,
            "energy_dp_id": device.energy_dp_id,
            "energy_multiplier": device.energy_multiplier,
        }
    db.commit()
    return payload


def finalize_command(
    db: Session,
    command: DeviceCommand,
    *,
    success: bool,
    result: dict | None = None,
    error: str | None = None,
) -> None:
    if command.status in {"succeeded", "failed", "expired"}:
        return
    now = datetime.now(UTC)
    command.status = "succeeded" if success else ("expired" if "expired" in (error or "").lower() else "failed")
    command.completed_at = now
    command.lease_expires_at = None
    command.result_json = json.dumps(
        result or ({"error": error} if error else {}),
        default=str,
    )
    if command.operation == "discover" or command.device_id is None:
        return

    device = (
        db.query(Device)
        .filter(
            Device.id == command.device_id,
            Device.connector_id == command.connector_id,
            Device.tenant_id == command.tenant_id,
        )
        .first()
    )
    if device is None:
        return

    context = json.loads(command.context_json or "{}")
    channel = None
    if command.channel_id:
        channel = db.query(DeviceChannel).filter(
            DeviceChannel.id == command.channel_id,
            DeviceChannel.device_id == device.id,
        ).first()

    if success and command.operation == "set_state" and command.desired_state is not None:
        if channel is not None:
            channel.current_state = command.desired_state
            device.current_state = any(
                item.current_state
                for item in db.query(DeviceChannel).filter(DeviceChannel.device_id == device.id).all()
            )
        else:
            device.current_state = command.desired_state
        device.last_state_change_at = now
        device.updated_at = now
    elif success and command.operation == "get_status" and isinstance((result or {}).get("state"), bool):
        state = result["state"]
        previous_state = channel.current_state if channel is not None else device.current_state
        had_previous_status = device.last_seen_at is not None
        if channel is not None:
            channel.current_state = state
            device.current_state = any(
                item.current_state
                for item in db.query(DeviceChannel).filter(DeviceChannel.device_id == device.id).all()
            )
        else:
            device.current_state = state
        if had_previous_status and previous_state != state:
            device.last_state_change_at = now
        device.last_seen_at = now
        device.updated_at = now

    if success and command.operation in {"get_status", "set_state"}:
        apply_meter_result(device, result or {}, observed_at=now)

    if context.get("event_type"):
        db.add(
            AutomationEvent(
                tenant_id=command.tenant_id,
                event_type=context["event_type"],
                reason=context.get("reason"),
                endpoint_id=context.get("endpoint_id"),
                device_id=device.id,
                channel_id=command.channel_id,
                battery_percentage=context.get("battery_percentage"),
                previous_state=context.get("previous_state"),
                new_state=context.get("new_state"),
                success=success,
                error=(error or (result or {}).get("error"))[:255] if (error or (result or {}).get("error")) else None,
            )
        )
