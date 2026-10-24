from datetime import UTC, datetime, timedelta

from app.core.database import SessionLocal
from app.models.event import AutomationEvent
from app.models.telemetry import BatteryReading
from app.services.event_retention import purge_expired_events, purge_expired_telemetry


def test_purge_expired_events_removes_only_events_older_than_30_days():
    now = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
    with SessionLocal() as db:
        db.add_all(
            [
                AutomationEvent(
                    event_type="EXPIRED",
                    created_at=now - timedelta(days=31),
                ),
                AutomationEvent(
                    event_type="AT_RETENTION_BOUNDARY",
                    created_at=now - timedelta(days=30),
                ),
                AutomationEvent(
                    event_type="RECENT",
                    created_at=now - timedelta(days=1),
                ),
            ]
        )
        db.commit()

        deleted_count = purge_expired_events(db, now)

        remaining_types = {
            event.event_type for event in db.query(AutomationEvent).all()
        }

    assert deleted_count == 1
    assert remaining_types == {"AT_RETENTION_BOUNDARY", "RECENT"}


def test_purge_expired_telemetry_removes_only_readings_older_than_30_days():
    now = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
    with SessionLocal() as db:
        db.add_all(
            [
                BatteryReading(
                    endpoint_id="endpoint-old",
                    battery_percentage=50,
                    charging=False,
                    ac_connected=False,
                    timestamp=now - timedelta(days=31),
                    system_metrics_json='{"cpu_usage_percent":12.5}',
                ),
                BatteryReading(
                    endpoint_id="endpoint-boundary",
                    battery_percentage=60,
                    charging=False,
                    ac_connected=False,
                    timestamp=now - timedelta(days=30),
                ),
                BatteryReading(
                    endpoint_id="endpoint-recent",
                    battery_percentage=70,
                    charging=True,
                    ac_connected=True,
                    timestamp=now - timedelta(days=1),
                ),
            ]
        )
        db.commit()

        deleted_count = purge_expired_telemetry(db, now)

        remaining_endpoints = {
            reading.endpoint_id for reading in db.query(BatteryReading).all()
        }

    assert deleted_count == 1
    assert remaining_endpoints == {"endpoint-boundary", "endpoint-recent"}
