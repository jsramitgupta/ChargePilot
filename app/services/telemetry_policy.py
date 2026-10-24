from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.tenant import Tenant

DEFAULT_REPORTING_INTERVAL_MINUTES = 5
MIN_REPORTING_INTERVAL_MINUTES = 1
MAX_REPORTING_INTERVAL_MINUTES = 1440


def tenant_reporting_interval_minutes(db: Session, tenant_id: str | None) -> int:
    if tenant_id is None:
        return DEFAULT_REPORTING_INTERVAL_MINUTES
    interval = (
        db.query(Tenant.telemetry_interval_minutes)
        .filter(Tenant.id == tenant_id)
        .scalar()
    )
    return interval or DEFAULT_REPORTING_INTERVAL_MINUTES


def telemetry_freshness_limit_seconds(reporting_interval_minutes: int) -> int:
    return min(
        settings.telemetry_max_age_seconds,
        max(
            settings.telemetry_automation_max_age_seconds,
            reporting_interval_minutes * 2 * 60,
        ),
    )


def endpoint_offline_limit_seconds(reporting_interval_minutes: int) -> int:
    return max(settings.endpoint_offline_timeout_seconds, reporting_interval_minutes * 2 * 60)
