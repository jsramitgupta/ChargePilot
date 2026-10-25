import asyncio
import json
from datetime import UTC, datetime, timedelta

from app.core.database import SessionLocal
from app.models.connector import DeviceCommand, SiteConnector
from app.models.device import Device
from app.models.endpoint import Endpoint
from app.models.event import AutomationEvent
from app.models.mapping import Mapping
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


def test_stale_or_non_opted_in_endpoint_samples_never_run_mappings():
    now = datetime.now(UTC)
    with SessionLocal() as db:
        endpoint = Endpoint(
            hostname="TELEMETRY-ONLY-MAC",
            tenant_id=None,
            platform="macos",
            installation_id="f49d742f-89c0-4dab-a6ba-95b57a35a210",
            battery_percentage=50,
            charging=False,
            ac_connected=None,
            last_seen_at=now,
            enabled=True,
            automation_enabled=False,
        )
        device = Device(
            name="test switch",
            device_id="telemetry-only-switch",
            encrypted_local_key="unused",
            tenant_id=None,
        )
        stale_endpoint = Endpoint(
            hostname="STALE-WINDOWS",
            tenant_id=None,
            platform="windows",
            battery_percentage=50,
            charging=False,
            ac_connected=False,
            last_seen_at=now - timedelta(hours=1),
            enabled=True,
            automation_enabled=True,
        )
        db.add_all([endpoint, device, stale_endpoint])
        db.flush()
        db.add(
            Mapping(
                endpoint_id=endpoint.id,
                device_id=device.id,
                tenant_id=None,
                enabled=True,
                on_threshold=80,
                off_threshold=99,
            )
        )
        db.add(
            Mapping(
                endpoint_id=stale_endpoint.id,
                device_id=device.id,
                tenant_id=None,
                enabled=True,
                on_threshold=80,
                off_threshold=99,
            )
        )
        db.commit()
        endpoint_id = endpoint.id
        stale_endpoint_id = stale_endpoint.id
        payload = TelemetryPayload(
            hostname=endpoint.hostname,
            installation_id=endpoint.installation_id,
            platform="macos",
            battery_percentage=50,
            charging=False,
            ac_connected=None,
            timestamp=now,
            agent_version="0.1.0",
        )

        processed = asyncio.run(
            process_telemetry_event(
                db,
                event_id="00000000-0000-0000-0000-000000000003",
                endpoint_id=endpoint_id,
                tenant_id=None,
                payload=payload,
            )
        )
        assert processed is True
        assert db.query(AutomationEvent).count() == 0

        delayed_payload = TelemetryPayload(
            hostname=stale_endpoint.hostname,
            battery_percentage=50,
            charging=False,
            ac_connected=False,
            timestamp=datetime.now(UTC) - timedelta(hours=1),
            agent_version="1.0.0",
        )
        processed_delayed = asyncio.run(
            process_telemetry_event(
                db,
                event_id="00000000-0000-0000-0000-000000000004",
                endpoint_id=stale_endpoint_id,
                tenant_id=None,
                payload=delayed_payload,
            )
        )
        assert processed_delayed is True
        assert db.query(AutomationEvent).count() == 0


def test_connector_automation_checks_live_state_before_queueing_a_decision():
    now = datetime.now(UTC)
    with SessionLocal() as db:
        connector = SiteConnector(
            tenant_id="connector-automation-tenant",
            name="Automation LAN",
            token_hash="connector-automation-token-hash",
            is_active=True,
        )
        endpoint = Endpoint(
            hostname="CONNECTOR-AUTOMATION-ENDPOINT",
            tenant_id="connector-automation-tenant",
            platform="windows",
            battery_percentage=50,
            charging=False,
            last_seen_at=now,
            enabled=True,
            automation_enabled=True,
        )
        db.add_all([connector, endpoint])
        db.flush()
        device = Device(
            tenant_id=connector.tenant_id,
            connector_id=connector.id,
            name="Connector switch",
            device_id="connector-automation-switch",
            encrypted_local_key="unused",
            current_state=True,
        )
        db.add(device)
        db.flush()
        db.add(
            Mapping(
                tenant_id=connector.tenant_id,
                endpoint_id=endpoint.id,
                device_id=device.id,
                enabled=True,
                on_threshold=80,
                off_threshold=99,
            )
        )
        db.commit()

        processed = asyncio.run(
            process_telemetry_event(
                db,
                event_id="00000000-0000-0000-0000-000000000005",
                endpoint_id=endpoint.id,
                tenant_id=connector.tenant_id,
                payload=TelemetryPayload(
                    hostname=endpoint.hostname,
                    battery_percentage=50,
                    charging=False,
                    ac_connected=False,
                    timestamp=now,
                    agent_version="1.0.0",
                ),
            )
        )

        command = db.query(DeviceCommand).filter(DeviceCommand.device_id == device.id).one()
        assert processed is True
        assert command.operation == "get_status"
        assert json.loads(command.context_json)["automation_reconcile"] is True
        assert db.query(DeviceCommand).filter(DeviceCommand.operation == "set_state").count() == 0


def test_local_automation_skips_decision_when_live_switch_status_is_unavailable(monkeypatch):
    now = datetime.now(UTC)

    class OfflineTuyaService:
        @staticmethod
        def from_device(_device):
            return OfflineTuyaService()

        async def get_status(self, _device_id, channel=1):
            return {"online": False, "state": False, "channel": channel}

        async def set_state(self, **_kwargs):
            raise AssertionError("Automation must not act on an unknown switch state.")

    monkeypatch.setattr("app.services.automation_processor.TuyaService", OfflineTuyaService)
    with SessionLocal() as db:
        endpoint = Endpoint(
            hostname="OFFLINE-SWITCH-ENDPOINT",
            battery_percentage=50,
            charging=False,
            last_seen_at=now,
            enabled=True,
            automation_enabled=True,
        )
        device = Device(
            name="Offline switch",
            device_id="offline-switch-device",
            encrypted_local_key="unused",
            current_state=True,
        )
        db.add_all([endpoint, device])
        db.flush()
        db.add(
            Mapping(
                endpoint_id=endpoint.id,
                device_id=device.id,
                enabled=True,
                on_threshold=80,
                off_threshold=99,
            )
        )
        db.commit()

        processed = asyncio.run(
            process_telemetry_event(
                db,
                event_id="00000000-0000-0000-0000-000000000006",
                endpoint_id=endpoint.id,
                tenant_id=None,
                payload=TelemetryPayload(
                    hostname=endpoint.hostname,
                    battery_percentage=50,
                    charging=False,
                    ac_connected=False,
                    timestamp=now,
                    agent_version="1.0.0",
                ),
            )
        )

        assert processed is True
        assert db.query(AutomationEvent).count() == 0
