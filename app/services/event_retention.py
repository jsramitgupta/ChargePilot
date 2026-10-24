from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.models.event import AutomationEvent
from app.models.telemetry import BatteryReading

EVENT_RETENTION_DAYS = 30
TELEMETRY_RETENTION_DAYS = 30


def purge_expired_events(db: Session, now: datetime | None = None) -> int:
    cutoff = (now or datetime.now(UTC)) - timedelta(days=EVENT_RETENTION_DAYS)
    deleted = (
        db.query(AutomationEvent)
        .filter(AutomationEvent.created_at < cutoff)
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted


def purge_expired_telemetry(db: Session, now: datetime | None = None) -> int:
    cutoff = (now or datetime.now(UTC)) - timedelta(days=TELEMETRY_RETENTION_DAYS)
    deleted = (
        db.query(BatteryReading)
        .filter(BatteryReading.timestamp < cutoff)
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted
