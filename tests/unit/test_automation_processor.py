import asyncio
from datetime import UTC, datetime, timedelta

from app.core.database import SessionLocal
from app.models.endpoint import Endpoint
from app.models.messaging import TelemetryAutomationCursor
from app.schemas.telemetry import TelemetryPayload
from app.services.automation_processor import process_telemetry_event


def test_automation_consumer_processes_a_telemetry_event_only_once():
    payload = TelemetryPayload(
        hostname="IDEMPOTENT-LAPTOP",
        ip_address="192.168.0.53",
        battery_percentage=50,
        charging=False,
        ac_connected=False,
        timestamp=datetime.now(UTC),
        agent_version="1.0.0",
    )
    with SessionLocal() as db:
        endpoint = Endpoint(
            hostname=payload.hostname,
            tenant_id=None,
            battery_percentage=payload.battery_percentage,
            charging=payload.charging,
            ac_connected=payload.ac_connected,
            enabled=True,
        )
        db.add(endpoint)
        db.commit()
        endpoint_id = endpoint.id

        first = asyncio.run(
            process_telemetry_event(
                db,
                event_id="00000000-0000-0000-0000-000000000001",
                endpoint_id=endpoint_id,
                tenant_id=None,
                payload=payload,
            )
        )
        second = asyncio.run(
            process_telemetry_event(
                db,
                event_id="00000000-0000-0000-0000-000000000001",
                endpoint_id=endpoint_id,
                tenant_id=None,
                payload=payload,
            )
        )
        out_of_order = asyncio.run(
            process_telemetry_event(
                db,
                event_id="00000000-0000-0000-0000-000000000002",
                endpoint_id=endpoint_id,
                tenant_id=None,
                payload=payload.model_copy(
                    update={"timestamp": payload.timestamp - timedelta(seconds=1)}
                ),
            )
        )

        assert first is True
        assert second is False
        assert out_of_order is False
        assert db.query(TelemetryAutomationCursor).count() == 1
        assert db.get(TelemetryAutomationCursor, endpoint_id).last_event_id == (
            "00000000-0000-0000-0000-000000000001"
        )
