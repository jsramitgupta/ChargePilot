import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Query, Session

from app.core.config import settings
from app.models.endpoint import Endpoint
from app.models.smart_group import SensorAssignment, SensorExecution, SmartGroup
from app.services.telemetry_policy import (
    telemetry_freshness_limit_seconds,
    tenant_reporting_interval_minutes,
)

SENSOR_CATALOG: dict[str, dict[str, Any]] = {
    "os_version": {
        "name": "Operating system version",
        "description": "Reports the operating system version string.",
        "value_type": "string",
    },
    "uptime_seconds": {
        "name": "System uptime",
        "description": "Reports seconds since the operating system last started.",
        "value_type": "integer",
    },
    "system_disk_free_bytes": {
        "name": "System disk free space",
        "description": "Reports available bytes on the system volume.",
        "value_type": "integer",
    },
}
SENSOR_CLAIM_LEASE = timedelta(minutes=2)
SENSOR_EXECUTION_TTL = timedelta(hours=24)
MAX_SENSOR_VALUE_STRING_LENGTH = 512
MAX_SENSOR_INTEGER = (1 << 63) - 1


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def decode_group_criteria(group: SmartGroup) -> dict[str, Any]:
    try:
        criteria = json.loads(group.criteria_json)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Smart group {group.id} has invalid stored criteria."
        ) from error
    if not isinstance(criteria, dict):
        raise ValueError(f"Smart group {group.id} criteria must be an object.")
    return criteria


def endpoint_matches_criteria(endpoint: Endpoint, criteria: dict[str, Any]) -> bool:
    if (
        endpoint.tenant_id is None
        or endpoint.platform not in {"windows", "macos"}
        or endpoint.installation_id is None
        or endpoint.token_hash is None
        or not endpoint.enabled
    ):
        return False
    if endpoint.platform not in criteria.get("platforms", []):
        return False
    endpoint_ids = criteria.get("endpoint_ids")
    if endpoint_ids is not None and endpoint.id not in endpoint_ids:
        return False
    name_query = criteria.get("name_contains")
    if (
        name_query
        and name_query.casefold() not in (endpoint.name or endpoint.hostname).casefold()
    ):
        return False
    battery_min = criteria.get("battery_min")
    if battery_min is not None and endpoint.battery_percentage < battery_min:
        return False
    battery_max = criteria.get("battery_max")
    if battery_max is not None and endpoint.battery_percentage > battery_max:
        return False
    charging = criteria.get("charging")
    return charging is None or endpoint.charging is charging


def endpoint_is_fresh(
    db: Session, endpoint: Endpoint, *, now: datetime | None = None
) -> bool:
    if endpoint.last_seen_at is None or endpoint.tenant_id is None:
        return False
    current_time = now or datetime.now(UTC)
    last_seen = endpoint.last_seen_at
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=UTC)
    age = (current_time - last_seen).total_seconds()
    interval = tenant_reporting_interval_minutes(db, endpoint.tenant_id)
    return (
        -settings.telemetry_max_future_skew_seconds
        <= age
        <= telemetry_freshness_limit_seconds(interval)
    )


def matching_group_endpoints(
    db: Session,
    group: SmartGroup,
    *,
    fresh_only: bool = True,
    limit: int | None = None,
) -> list[Endpoint]:
    criteria = decode_group_criteria(group)
    query = _matching_group_endpoint_query(db, group, criteria, fresh_only=fresh_only)
    if limit is not None:
        query = query.limit(limit)
    return query.all()


def matching_group_endpoint_count(
    db: Session,
    group: SmartGroup,
    *,
    fresh_only: bool = True,
) -> int:
    criteria = decode_group_criteria(group)
    return _matching_group_endpoint_query(
        db,
        group,
        criteria,
        fresh_only=fresh_only,
    ).count()


def _matching_group_endpoint_query(
    db: Session,
    group: SmartGroup,
    criteria: dict[str, Any],
    *,
    fresh_only: bool,
) -> Query:
    query = db.query(Endpoint).filter(
        Endpoint.tenant_id == group.tenant_id,
        Endpoint.platform.in_(criteria.get("platforms", [])),
        Endpoint.installation_id.is_not(None),
        Endpoint.token_hash.is_not(None),
        Endpoint.enabled.is_(True),
    )
    endpoint_ids = criteria.get("endpoint_ids")
    if endpoint_ids is not None:
        query = query.filter(Endpoint.id.in_(endpoint_ids))
    name_query = criteria.get("name_contains")
    if name_query:
        pattern = (
            "%"
            + name_query.casefold()
            .replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
            + "%"
        )
        query = query.filter(
            func.coalesce(Endpoint.name, Endpoint.hostname).ilike(pattern, escape="\\")
        )
    battery_min = criteria.get("battery_min")
    if battery_min is not None:
        query = query.filter(Endpoint.battery_percentage >= battery_min)
    battery_max = criteria.get("battery_max")
    if battery_max is not None:
        query = query.filter(Endpoint.battery_percentage <= battery_max)
    charging = criteria.get("charging")
    if charging is not None:
        query = query.filter(Endpoint.charging.is_(charging))
    if fresh_only:
        now = datetime.now(UTC)
        reporting_interval = tenant_reporting_interval_minutes(db, group.tenant_id)
        freshness_limit = telemetry_freshness_limit_seconds(reporting_interval)
        query = query.filter(
            Endpoint.last_seen_at.is_not(None),
            Endpoint.last_seen_at >= now - timedelta(seconds=freshness_limit),
            Endpoint.last_seen_at
            <= now + timedelta(seconds=settings.telemetry_max_future_skew_seconds),
        )
    return query.order_by(Endpoint.name.asc().nullslast(), Endpoint.hostname.asc())


def validate_sensor_value(sensor_id: str, value: Any) -> str:
    definition = SENSOR_CATALOG.get(sensor_id)
    if definition is None:
        raise ValueError("This sensor is not in the approved read-only catalog.")
    if definition["value_type"] == "string":
        if not isinstance(value, str) or not value.strip():
            raise ValueError("This sensor must return a non-empty string.")
        if len(value) > MAX_SENSOR_VALUE_STRING_LENGTH:
            raise ValueError("Sensor string values cannot exceed 512 characters.")
        if any(ord(character) < 32 for character in value):
            raise ValueError("Sensor string values cannot contain control characters.")
    elif (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not 0 <= value <= MAX_SENSOR_INTEGER
    ):
        raise ValueError("This sensor must return a non-negative integer.")
    return json.dumps({"value": value}, separators=(",", ":"), ensure_ascii=False)


def claim_sensor_execution(
    db: Session,
    *,
    endpoint: Endpoint,
) -> tuple[SensorExecution, str] | None:
    if (
        endpoint.tenant_id is None
        or endpoint.platform not in {"windows", "macos"}
        or not endpoint.enabled
        or endpoint.installation_id is None
        or not endpoint_is_fresh(db, endpoint)
    ):
        return None

    now = datetime.now(UTC)
    for _ in range(10):
        execution = (
            db.query(SensorExecution)
            .filter(
                SensorExecution.endpoint_id == endpoint.id,
                SensorExecution.tenant_id == endpoint.tenant_id,
                SensorExecution.status.in_(("queued", "claimed")),
            )
            .order_by(SensorExecution.created_at.asc())
            .with_for_update(skip_locked=True)
            .first()
        )
        if execution is None:
            return None
        if execution.status == "claimed" and (
            execution.lease_expires_at is not None
            and _as_utc(execution.lease_expires_at) > now
        ):
            return None
        group = (
            db.query(SmartGroup)
            .filter(
                SmartGroup.id == execution.group_id,
                SmartGroup.tenant_id == endpoint.tenant_id,
            )
            .first()
        )
        assignment = (
            db.query(SensorAssignment)
            .filter(
                SensorAssignment.id == execution.assignment_id,
                SensorAssignment.group_id == execution.group_id,
                SensorAssignment.tenant_id == endpoint.tenant_id,
                SensorAssignment.sensor_id == execution.sensor_id,
                SensorAssignment.enabled.is_(True),
            )
            .first()
        )
        if (
            group is None
            or assignment is None
            or execution.sensor_id not in SENSOR_CATALOG
            or not endpoint_matches_criteria(endpoint, decode_group_criteria(group))
        ):
            execution.status = "cancelled"
            execution.completed_at = now
            continue
        created_at = _as_utc(execution.created_at)
        if created_at + SENSOR_EXECUTION_TTL <= now:
            execution.status = "expired"
            execution.completed_at = now
            continue
        claim_token = secrets.token_urlsafe(32)
        execution.status = "claimed"
        execution.claimed_at = now
        execution.lease_expires_at = now + SENSOR_CLAIM_LEASE
        execution.lease_token_hash = hashlib.sha256(
            claim_token.encode("ascii")
        ).hexdigest()
        return execution, claim_token
    return None


def complete_sensor_execution(
    db: Session,
    *,
    endpoint: Endpoint,
    execution_id: str,
    claim_token: str,
    value: Any | None,
    error: str | None,
) -> SensorExecution | None:
    execution = (
        db.query(SensorExecution)
        .filter(
            SensorExecution.id == execution_id,
            SensorExecution.endpoint_id == endpoint.id,
            SensorExecution.tenant_id == endpoint.tenant_id,
        )
        .with_for_update()
        .first()
    )
    if execution is None:
        return None
    if execution.status in {"completed", "failed", "cancelled", "expired"}:
        return execution
    if execution.status != "claimed":
        return execution
    expected_hash = execution.lease_token_hash
    presented_hash = hashlib.sha256(claim_token.encode("ascii")).hexdigest()
    if expected_hash is None or not hmac.compare_digest(expected_hash, presented_hash):
        raise PermissionError("This sensor claim is no longer valid.")

    now = datetime.now(UTC)
    if execution.lease_expires_at is None:
        raise PermissionError("This sensor claim has expired.")
    lease_expires_at = _as_utc(execution.lease_expires_at)
    if lease_expires_at <= now:
        raise PermissionError("This sensor claim has expired.")
    execution.completed_at = now
    execution.lease_expires_at = None
    execution.lease_token_hash = None
    if error:
        execution.status = "failed"
        execution.error = error[:255]
    else:
        execution.result_json = validate_sensor_value(execution.sensor_id, value)
        execution.status = "completed"
        execution.error = None
    return execution


def purge_expired_sensor_executions(db: Session, *, retention_days: int = 30) -> int:
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    deleted = (
        db.query(SensorExecution)
        .filter(SensorExecution.created_at < cutoff)
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted
