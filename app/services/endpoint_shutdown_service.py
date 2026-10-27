from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.endpoint import Endpoint
from app.models.endpoint_shutdown_command import EndpointShutdownCommand
from app.models.event import AutomationEvent
from app.models.mapping import Mapping
from app.services.telemetry_policy import (
    telemetry_freshness_limit_seconds,
    tenant_reporting_interval_minutes,
)

SHUTDOWN_COMMAND_TTL = timedelta(minutes=10)
SHUTDOWN_COMMAND_LEASE = timedelta(seconds=45)


def queue_shutdown_command(
    db: Session,
    *,
    endpoint: Endpoint,
    mapping: Mapping,
    automation_event_id: str,
) -> EndpointShutdownCommand | None:
    if (
        mapping.use_case != "switch_and_shutdown"
        or endpoint.platform not in {"windows", "macos"}
        or not endpoint.enabled
        or not endpoint.automation_enabled
        or endpoint.tenant_id is None
        or endpoint.installation_id is None
        or endpoint.token_hash is None
    ):
        return None

    existing = (
        db.query(EndpointShutdownCommand)
        .filter(
            EndpointShutdownCommand.endpoint_id == endpoint.id,
            EndpointShutdownCommand.mapping_id == mapping.id,
            EndpointShutdownCommand.automation_event_id == automation_event_id,
        )
        .first()
    )
    if existing is not None:
        return existing

    now = datetime.now(UTC)
    command = EndpointShutdownCommand(
        tenant_id=endpoint.tenant_id,
        endpoint_id=endpoint.id,
        mapping_id=mapping.id,
        automation_event_id=automation_event_id,
        status="pending",
        created_at=now,
        expires_at=now + SHUTDOWN_COMMAND_TTL,
    )
    db.add(command)
    db.flush()
    return command


def claim_shutdown_command(
    db: Session,
    *,
    endpoint: Endpoint,
) -> EndpointShutdownCommand | None:
    now = datetime.now(UTC)
    endpoint_last_seen = endpoint.last_seen_at
    if endpoint_last_seen is None:
        return None
    if endpoint_last_seen.tzinfo is None:
        endpoint_last_seen = endpoint_last_seen.replace(tzinfo=UTC)
    sample_age_seconds = (now - endpoint_last_seen).total_seconds()
    interval = tenant_reporting_interval_minutes(db, endpoint.tenant_id)
    if (
        not endpoint.enabled
        or not endpoint.automation_enabled
        or endpoint.platform not in {"windows", "macos"}
        or not (
            -settings.telemetry_max_future_skew_seconds
            <= sample_age_seconds
            <= telemetry_freshness_limit_seconds(interval)
        )
    ):
        return None

    command = (
        db.query(EndpointShutdownCommand)
        .filter(
            EndpointShutdownCommand.endpoint_id == endpoint.id,
            EndpointShutdownCommand.tenant_id == endpoint.tenant_id,
            EndpointShutdownCommand.status.in_(("pending", "claimed")),
            EndpointShutdownCommand.expires_at > now,
            (
                (EndpointShutdownCommand.status == "pending")
                | (EndpointShutdownCommand.lease_expires_at <= now)
            ),
        )
        .order_by(EndpointShutdownCommand.created_at.asc())
        .with_for_update(skip_locked=True)
        .first()
    )
    if command is None:
        db.query(EndpointShutdownCommand).filter(
            EndpointShutdownCommand.endpoint_id == endpoint.id,
            EndpointShutdownCommand.status.in_(("pending", "claimed")),
            EndpointShutdownCommand.expires_at <= now,
        ).update(
            {"status": "expired", "completed_at": now},
            synchronize_session=False,
        )
        return None

    mapping = (
        db.query(Mapping)
        .filter(
            Mapping.id == command.mapping_id,
            Mapping.endpoint_id == endpoint.id,
            Mapping.tenant_id == endpoint.tenant_id,
            Mapping.enabled.is_(True),
            Mapping.use_case == "switch_and_shutdown",
        )
        .first()
    )
    if mapping is None:
        command.status = "cancelled"
        command.completed_at = now
        return None

    command.status = "claimed"
    command.claimed_at = now
    command.lease_expires_at = now + SHUTDOWN_COMMAND_LEASE
    command.attempts += 1
    return command


def acknowledge_shutdown_command(
    db: Session,
    *,
    endpoint: Endpoint,
    command_id: str,
    outcome: str,
    error: str | None,
) -> EndpointShutdownCommand | None:
    command = (
        db.query(EndpointShutdownCommand)
        .filter(
            EndpointShutdownCommand.id == command_id,
            EndpointShutdownCommand.endpoint_id == endpoint.id,
            EndpointShutdownCommand.tenant_id == endpoint.tenant_id,
        )
        .with_for_update()
        .first()
    )
    if command is None:
        return None
    if command.status in {"scheduled", "cancelled", "failed", "expired"}:
        return command
    if command.status != "claimed":
        return command

    now = datetime.now(UTC)
    expires_at = command.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= now:
        command.status = "expired"
        command.completed_at = now
        command.lease_expires_at = None
        return command

    command.status = outcome
    command.error = error[:255] if error else None
    command.completed_at = now
    command.lease_expires_at = None

    mapping = db.get(Mapping, command.mapping_id)
    db.add(
        AutomationEvent(
            tenant_id=endpoint.tenant_id,
            event_type=f"ENDPOINT_SHUTDOWN_{outcome.upper()}",
            reason=(
                "The Windows/macOS agent accepted the scheduled shutdown."
                if outcome == "scheduled"
                else "The Windows/macOS agent did not schedule shutdown."
            ),
            endpoint_id=endpoint.id,
            device_id=mapping.device_id if mapping is not None else None,
            battery_percentage=endpoint.battery_percentage,
            success=outcome == "scheduled",
            error=command.error,
        )
    )
    return command


def maintain_shutdown_commands(db: Session) -> tuple[int, int]:
    now = datetime.now(UTC)
    expired = (
        db.query(EndpointShutdownCommand)
        .filter(
            EndpointShutdownCommand.status.in_(("pending", "claimed")),
            EndpointShutdownCommand.expires_at <= now,
        )
        .update(
            {
                "status": "expired",
                "completed_at": now,
                "lease_expires_at": None,
            },
            synchronize_session=False,
        )
    )
    cutoff = now - timedelta(days=30)
    purged = (
        db.query(EndpointShutdownCommand)
        .filter(EndpointShutdownCommand.created_at < cutoff)
        .delete(synchronize_session=False)
    )
    db.commit()
    return expired, purged
