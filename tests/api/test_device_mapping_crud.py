import asyncio
import json
from datetime import timedelta
from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from app.core.database import (
    Base,
    SessionLocal,
    _ensure_endpoint_hardware_uuid_index,
    _ensure_table_columns,
    engine,
)
from app.core.security import hash_password
from app.main import app, generate_unique_agent_token
from app.models.tenant import Tenant
from app.models.user import User
from conftest import TEST_GLOBAL_AGENT_TOKEN, api_login, register_tenant_admin


def _recent_timestamp(seconds_ago: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)).isoformat()


def _super_admin_client() -> TestClient:
    client = TestClient(app)
    api_login(client, "admin", "change-me")
    return client


def _create_tenant_client(name: str) -> tuple[TestClient, str, str, str]:
    suffix = uuid4().hex[:10]
    username = f"{name.lower()}-{suffix}"
    with SessionLocal() as db:
        tenant = Tenant(
            name=f"{name} {suffix}",
            slug=f"{name.lower()}-{suffix}",
            agent_token=generate_unique_agent_token(db),
        )
        db.add(tenant)
        db.flush()
        user = User(
            username=username,
            password_hash=hash_password("tenant-password"),
            tenant_id=tenant.id,
            role="tenant_admin",
            is_admin=True,
        )
        db.add(user)
        db.commit()
        tenant_id = tenant.id
        tenant_name = tenant.name
        agent_token = tenant.agent_token

    client = TestClient(app)
    api_login(client, username, "tenant-password")
    return client, tenant_id, tenant_name, agent_token


def _create_endpoint(client: TestClient, hostname: str) -> str:
    response = client.post("/api/v1/endpoints", json={"hostname": hostname})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _mock_tuya_service(monkeypatch):
    class FakeTuyaService:
        @staticmethod
        def from_device(device):
            return FakeTuyaService()

        async def get_status(self, device_id, channel=1):
            return {"device_id": device_id, "channel": channel, "online": False}

        async def set_state(self, device_id, on, channel=1):
            return {"device_id": device_id, "channel": channel, "success": True, "state": "ON" if on else "OFF"}

    monkeypatch.setattr("app.api.devices.TuyaService", FakeTuyaService)
    monkeypatch.setattr("app.services.automation_processor.TuyaService", FakeTuyaService)


def _process_telemetry_outbox(session, hostname: str) -> None:
    from app.models.messaging import TelemetryAutomationCursor, TelemetryOutbox
    from app.schemas.telemetry import TelemetryPayload
    from app.services.automation_processor import process_telemetry_event

    events = session.query(TelemetryOutbox).order_by(TelemetryOutbox.created_at).all()
    for event in events:
        event_payload = json.loads(event.payload_json)
        if event_payload["hostname"] != hostname:
            continue
        endpoint_id = event_payload.pop("endpoint_id")
        cursor = session.get(TelemetryAutomationCursor, endpoint_id)
        if cursor is not None and cursor.last_event_id == event.id:
            continue
        asyncio.run(
            process_telemetry_event(
                session,
                event_id=event.id,
                endpoint_id=endpoint_id,
                tenant_id=event.tenant_id,
                payload=TelemetryPayload.model_validate(event_payload),
            )
        )


def test_ensure_table_columns_adds_missing_device_channel_state_column():
    inspector = inspect(engine)
    if inspector.has_table("device_channels"):
        with engine.begin() as conn:
            conn.execute(text('DROP TABLE "device_channels"'))

    with engine.begin() as conn:
        conn.execute(
            text(
                '''
                CREATE TABLE "device_channels" (
                    "id" VARCHAR(36) NOT NULL,
                    "device_id" VARCHAR(36) NOT NULL,
                    "channel_index" INTEGER NOT NULL,
                    "name" VARCHAR(160) NOT NULL,
                    "dp_id" VARCHAR(50),
                    "enabled" BOOLEAN NOT NULL DEFAULT TRUE,
                    PRIMARY KEY ("id")
                )
                '''
            )
        )

    _ensure_table_columns()

    columns = {column["name"] for column in inspect(engine).get_columns("device_channels")}
    assert "current_state" in columns

    Base.metadata.create_all(bind=engine)


def test_ensure_table_columns_adds_mapping_power_options():
    with engine.begin() as conn:
        for column in (
            "turn_on_enabled",
            "turn_off_when_charging_enabled",
            "charging_off_threshold",
        ):
            conn.execute(text(f'ALTER TABLE "mappings" DROP COLUMN "{column}"'))

    _ensure_table_columns()

    columns = {
        column["name"]: column
        for column in inspect(engine).get_columns("mappings")
    }
    assert columns["turn_on_enabled"]["nullable"] is False
    assert columns["turn_off_when_charging_enabled"]["nullable"] is False
    assert columns["charging_off_threshold"]["nullable"] is False


def test_endpoint_uuid_migration_keeps_existing_rows_and_adds_unique_index():
    from app.models.endpoint import Endpoint

    with SessionLocal() as db:
        db.add(Endpoint(hostname="legacy-hardware-uuid-migration"))
        db.commit()

    with engine.begin() as conn:
        conn.execute(text("DROP INDEX ix_endpoints_hardware_uuid"))
        conn.execute(text("ALTER TABLE endpoints DROP COLUMN hardware_uuid"))

    _ensure_table_columns()
    _ensure_endpoint_hardware_uuid_index()

    columns = {column["name"] for column in inspect(engine).get_columns("endpoints")}
    uuid_index = next(
        index
        for index in inspect(engine).get_indexes("endpoints")
        if index["name"] == "ix_endpoints_hardware_uuid"
    )
    assert "hardware_uuid" in columns
    assert uuid_index["unique"] == 1
    with SessionLocal() as db:
        endpoint = db.query(Endpoint).filter(
            Endpoint.hostname == "legacy-hardware-uuid-migration"
        ).one()
        assert endpoint.hardware_uuid is None


def test_device_and_mapping_crud_flow():
    client = _super_admin_client()

    device_response = client.post(
        "/api/v1/devices",
        json={
            "name": "Desk Plug",
            "device_id": "tuya-device-123",
            "ip_address": "192.168.0.50",
            "device_type": "switch",
            "protocol_version": "3.1",
            "enabled": True,
            "encrypted_local_key": "encrypted-key-value",
        },
    )

    assert device_response.status_code == 201, device_response.text
    device = device_response.json()
    assert device["name"] == "Desk Plug"

    endpoint_id = _create_endpoint(client, "desk-plug-endpoint")
    mapping_response = client.post(
        "/api/v1/mappings",
        json={
            "endpoint_id": endpoint_id,
            "device_id": device["id"],
            "channel_id": None,
            "enabled": True,
            "on_threshold": 20,
            "off_threshold": 99,
            "minimum_state_change_interval": 300,
        },
    )

    assert mapping_response.status_code == 201, mapping_response.text
    mapping = mapping_response.json()
    assert mapping["device_id"] == device["id"]

    list_response = client.get("/api/v1/mappings")
    assert list_response.status_code == 200
    assert any(item["device_id"] == device["id"] for item in list_response.json())


def test_assigning_endpoint_to_tenant_restores_tenant_scoped_telemetry_and_mapping_flow():
    admin = _super_admin_client()
    tenant_client, tenant_id, tenant_name, tenant_token = _create_tenant_client("Assigned")
    endpoint_response = admin.post(
        "/api/v1/endpoints",
        json={"hostname": "assigned-laptop"},
    )
    assert endpoint_response.status_code == 201, endpoint_response.text
    endpoint_id = endpoint_response.json()["id"]

    assignment = admin.patch(
        f"/api/v1/endpoints/{endpoint_id}/tenant",
        json={"tenant_id": tenant_id},
    )
    assert assignment.status_code == 200, assignment.text
    assert assignment.json()["tenant_name"] == tenant_name
    assert tenant_client.patch(
        f"/api/v1/endpoints/{endpoint_id}/tenant",
        json={"tenant_id": tenant_id},
    ).status_code == 403

    agent_setup = admin.get("/api/v1/agent/setup", params={"tenant_id": tenant_id})
    assert agent_setup.status_code == 200, agent_setup.text
    assert agent_setup.json()["token"] == tenant_token
    assert agent_setup.json()["global_token"] != tenant_token
    assert agent_setup.json()["token_scope"] == f"tenant: {tenant_name}"
    assert admin.get("/agent", params={"tenant_id": tenant_id}, follow_redirects=False).status_code == 307
    assert admin.get("/agent/guide", follow_redirects=False).status_code == 307

    device_response = tenant_client.post(
        "/api/v1/devices",
        json={
            "name": "Assigned Tenant Switch",
            "device_id": f"assigned-device-{uuid4().hex[:8]}",
            "encrypted_local_key": "test-local-key",
        },
    )
    assert device_response.status_code == 201, device_response.text
    device = device_response.json()
    assert device["tenant_id"] == tenant_id
    assert device["tenant_name"] == tenant_name

    mapping_response = admin.post(
        "/api/v1/mappings",
        json={"endpoint_id": endpoint_id, "device_id": device["id"]},
    )
    assert mapping_response.status_code == 201, mapping_response.text
    assert mapping_response.json()["tenant_name"] == tenant_name

    hardware_uuid = "a75f47d3-8923-4914-a317-2c64c4adf21e"
    telemetry_payload = {
        "hostname": "assigned-laptop",
        "hardware_uuid": hardware_uuid,
        "ip_address": "192.168.10.25",
        "battery_percentage": 42,
        "charging": False,
        "ac_connected": False,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent_version": "1.0.0",
    }
    telemetry = tenant_client.post(
        "/api/v1/telemetry",
        json=telemetry_payload,
        headers={"Authorization": f"Bearer {tenant_token}"},
    )
    assert telemetry.status_code == 200, telemetry.text

    with SessionLocal() as db:
        from app.models.messaging import TelemetryOutbox
        from app.models.system_setting import SystemSetting

        global_token = db.query(SystemSetting.value).filter(
            SystemSetting.key == "global_agent_token"
        ).scalar()
        outbox = db.query(TelemetryOutbox).one()
        assert outbox.tenant_id == tenant_id

    global_telemetry = admin.post(
        "/api/v1/telemetry",
        json=telemetry_payload,
        headers={"Authorization": f"Bearer {global_token}"},
    )
    assert global_telemetry.status_code == 409
    tenant_config = tenant_client.get(
        "/api/v1/endpoints/agent-config",
        params={"hardware_uuid": hardware_uuid},
        headers={"Authorization": f"Bearer {tenant_token}"},
    )
    assert tenant_config.status_code == 200, tenant_config.text
    assert tenant_config.json()["mappings"][0]["device_id"] == device["id"]
    global_config = admin.get(
        "/api/v1/endpoints/agent-config",
        params={"hardware_uuid": hardware_uuid},
        headers={"Authorization": f"Bearer {global_token}"},
    )
    assert global_config.status_code == 404

    endpoints = tenant_client.get("/api/v1/endpoints")
    assert endpoints.status_code == 200
    assert endpoints.json()[0]["tenant_name"] == tenant_name
    devices = tenant_client.get("/api/v1/devices")
    assert devices.status_code == 200
    assert devices.json()[0]["tenant_name"] == tenant_name
    assert tenant_client.get(f"/api/v1/devices/{device['id']}").json()["tenant_name"] == tenant_name
    mappings = tenant_client.get("/api/v1/mappings")
    assert mappings.status_code == 200
    assert mappings.json()[0]["tenant_name"] == tenant_name

    for path in ("/", "/endpoints", "/devices", "/mappings"):
        assert tenant_client.get(path, follow_redirects=False).status_code == 307


def test_tenant_assignment_does_not_allow_cross_tenant_mapping_or_transfer():
    admin = _super_admin_client()
    tenant_a, tenant_a_id, _, _ = _create_tenant_client("North")
    tenant_b, tenant_b_id, _, _ = _create_tenant_client("South")
    endpoint = admin.post(
        "/api/v1/endpoints",
        json={"hostname": "north-laptop"},
    )
    assert endpoint.status_code == 201, endpoint.text
    endpoint_id = endpoint.json()["id"]
    assigned = admin.patch(
        f"/api/v1/endpoints/{endpoint_id}/tenant",
        json={"tenant_id": tenant_a_id},
    )
    assert assigned.status_code == 200, assigned.text

    device = tenant_b.post(
        "/api/v1/devices",
        json={
            "name": "South Switch",
            "device_id": f"south-device-{uuid4().hex[:8]}",
            "encrypted_local_key": "test-local-key",
        },
    )
    assert device.status_code == 201, device.text
    cross_tenant_mapping = admin.post(
        "/api/v1/mappings",
        json={"endpoint_id": endpoint_id, "device_id": device.json()["id"]},
    )
    assert cross_tenant_mapping.status_code == 404

    transfer = admin.patch(
        f"/api/v1/endpoints/{endpoint_id}/tenant",
        json={"tenant_id": tenant_b_id},
    )
    assert transfer.status_code == 409
    assert tenant_a.patch(
        f"/api/v1/endpoints/{endpoint_id}/tenant",
        json={"tenant_id": tenant_b_id},
    ).status_code == 403


def test_endpoint_with_existing_mapping_cannot_be_assigned_to_a_tenant():
    admin = _super_admin_client()
    _, tenant_id, _, _ = _create_tenant_client("Mapped")
    endpoint = admin.post("/api/v1/endpoints", json={"hostname": "mapped-global-laptop"})
    device = admin.post(
        "/api/v1/devices",
        json={
            "name": "Global switch",
            "device_id": f"global-switch-{uuid4().hex[:8]}",
            "encrypted_local_key": "test-local-key",
        },
    )
    assert endpoint.status_code == 201, endpoint.text
    assert device.status_code == 201, device.text
    mapping = admin.post(
        "/api/v1/mappings",
        json={"endpoint_id": endpoint.json()["id"], "device_id": device.json()["id"]},
    )
    assert mapping.status_code == 201, mapping.text

    assignment = admin.patch(
        f"/api/v1/endpoints/{endpoint.json()['id']}/tenant",
        json={"tenant_id": tenant_id},
    )
    assert assignment.status_code == 409
    assert "existing mappings" in assignment.json()["detail"]


def test_device_channel_mapping_for_multi_gang_switch():
    client = _super_admin_client()

    device_response = client.post(
        "/api/v1/devices",
        json={
            "name": "4-Gang Switch",
            "device_id": "tuya-4gang-001",
            "ip_address": "192.168.0.60",
            "device_type": "switch",
            "protocol_version": "3.1",
            "enabled": True,
            "encrypted_local_key": "encrypted-key-4gang",
        },
    )
    assert device_response.status_code == 201, device_response.text
    device = device_response.json()

    channel_response = client.post(
        f"/api/v1/devices/{device['id']}/channels",
        json={
            "channel_index": 2,
            "name": "Gang 2",
            "dp_id": "2",
            "enabled": True,
        },
    )
    assert channel_response.status_code == 201, channel_response.text
    channel = channel_response.json()
    assert channel["channel_index"] == 2

    endpoint_id = _create_endpoint(client, "four-gang-endpoint")
    mapping_response = client.post(
        "/api/v1/mappings",
        json={
            "endpoint_id": endpoint_id,
            "device_id": device["id"],
            "channel_id": channel["id"],
            "enabled": True,
            "on_threshold": 30,
            "off_threshold": 80,
            "minimum_state_change_interval": 180,
        },
    )

    assert mapping_response.status_code == 201, mapping_response.text
    mapping = mapping_response.json()
    assert mapping["channel_id"] == channel["id"]
    assert mapping["device_id"] == device["id"]


def test_unique_mapping_per_endpoint_and_device():
    client = _super_admin_client()

    device_response = client.post(
        "/api/v1/devices",
        json={
            "name": "Unique Mapping Switch",
            "device_id": "tuya-unique-map",
            "ip_address": "192.168.0.101",
            "device_type": "switch",
            "protocol_version": "3.1",
            "enabled": True,
            "encrypted_local_key": "unique-key",
        },
    )
    assert device_response.status_code == 201, device_response.text
    device = device_response.json()

    endpoint_id = _create_endpoint(client, "unique-mapping-endpoint")
    first_mapping = client.post(
        "/api/v1/mappings",
        json={
            "endpoint_id": endpoint_id,
            "device_id": device["id"],
            "channel_id": None,
            "enabled": True,
            "on_threshold": 20,
            "off_threshold": 99,
            "minimum_state_change_interval": 300,
        },
    )
    assert first_mapping.status_code == 201, first_mapping.text

    duplicate_mapping = client.post(
        "/api/v1/mappings",
        json={
            "endpoint_id": endpoint_id,
            "device_id": device["id"],
            "channel_id": None,
            "enabled": True,
            "on_threshold": 30,
            "off_threshold": 80,
            "minimum_state_change_interval": 180,
        },
    )
    assert duplicate_mapping.status_code == 409, duplicate_mapping.text

    mappings = client.get("/api/v1/mappings")
    assert mappings.status_code == 200
    assert len(mappings.json()) == 1


def test_mappings_page_exposes_editable_threshold_controls():
    client = TestClient(app)
    register_tenant_admin(client, "threshold_admin", "threshold-admin-password")

    device = client.post(
        "/api/v1/devices",
        json={
            "name": "Threshold Device",
            "device_id": "threshold-device-001",
            "ip_address": "192.168.0.155",
            "device_type": "switch",
            "protocol_version": "3.1",
            "enabled": True,
            "encrypted_local_key": "threshold-key",
        },
    ).json()
    channel = client.post(
        f"/api/v1/devices/{device['id']}/channels",
        json={"channel_index": 1, "name": "Output 1"},
    ).json()
    endpoint = client.post(
        "/api/v1/endpoints",
        json={
            "hostname": "threshold-endpoint",
            "ip_address": "10.0.0.42",
            "battery_percentage": 70,
            "charging": False,
            "ac_connected": True,
            "enabled": True,
        },
    ).json()
    mapping_response = client.post(
        "/api/v1/mappings",
        json={
            "endpoint_id": endpoint["id"],
            "device_id": device["id"],
            "channel_id": channel["id"],
            "enabled": True,
            "turn_on_enabled": False,
            "on_threshold": 35,
            "off_threshold": 90,
            "turn_off_when_charging_enabled": True,
            "charging_off_threshold": 85,
            "minimum_state_change_interval": 300,
        },
    )
    assert mapping_response.status_code == 201, mapping_response.text
    mapping = mapping_response.json()
    assert mapping["tenant_name"] == "threshold_admin tenant"
    assert mapping["turn_on_enabled"] is False
    assert mapping["turn_off_when_charging_enabled"] is True
    assert mapping["charging_off_threshold"] == 85

    updated = client.put(
        f"/api/v1/mappings/{mapping['id']}",
        json={
            "turn_on_enabled": True,
            "turn_off_when_charging_enabled": False,
            "charging_off_threshold": 88,
            "on_threshold": 40,
            "off_threshold": 85,
            "minimum_state_change_interval": 420,
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["turn_on_enabled"] is True
    assert updated.json()["turn_off_when_charging_enabled"] is False
    assert updated.json()["charging_off_threshold"] == 88
    assert updated.json()["on_threshold"] == 40
    assert updated.json()["off_threshold"] == 85
    assert updated.json()["minimum_state_change_interval"] == 420
    assert client.put(
        f"/api/v1/mappings/{mapping['id']}",
        json={"charging_off_threshold": 101},
    ).status_code == 422
    assert client.put(
        f"/api/v1/mappings/{mapping['id']}",
        json={"on_threshold": None},
    ).status_code == 422
    cleared_channel = client.put(
        f"/api/v1/mappings/{mapping['id']}",
        json={"channel_id": None},
    )
    assert cleared_channel.status_code == 200, cleared_channel.text
    assert cleared_channel.json()["channel_id"] is None
    assert client.get("/mappings", follow_redirects=False).status_code == 307


def test_mappings_page_groups_channel_choices_under_expandable_switches():
    client = TestClient(app)
    register_tenant_admin(client, "channel_picker_user", "channel-picker-password")

    for name, device_id, channel_count in (
        ("Desk Switch", "desk-switch", 2),
        ("Hall Switch", "hall-switch", 1),
    ):
        response = client.post(
            "/api/v1/devices",
            json={
                "name": name,
                "device_id": device_id,
                "ip_address": "192.168.1.20",
                "device_type": "switch",
                "protocol_version": "3.5",
                "encrypted_local_key": "local-key",
            },
        )
        assert response.status_code == 201, response.text
        device = response.json()
        for channel_index in range(1, channel_count + 1):
            channel = client.post(
                f"/api/v1/devices/{device['id']}/channels",
                json={"channel_index": channel_index, "name": f"Channel {channel_index}"},
            )
            assert channel.status_code == 201, channel.text

    devices = client.get("/api/v1/devices").json()
    assert {device["name"] for device in devices} == {"Desk Switch", "Hall Switch"}
    assert sorted(len(client.get(f"/api/v1/devices/{device['id']}/channels").json()) for device in devices) == [1, 2]


def test_endpoint_agent_config_returns_live_threshold_settings():
    client = _super_admin_client()

    device = client.post(
        "/api/v1/devices",
        json={
            "name": "Agent Config Device",
            "device_id": "agent-config-device",
            "ip_address": "192.168.0.160",
            "device_type": "switch",
            "protocol_version": "3.1",
            "enabled": True,
            "encrypted_local_key": "agent-config-key",
        },
    ).json()
    endpoint = client.post(
        "/api/v1/endpoints",
        json={
            "hostname": "agent-config-endpoint",
            "ip_address": "10.0.0.43",
            "battery_percentage": 67,
            "charging": False,
            "ac_connected": True,
            "enabled": True,
        },
    ).json()
    mapping = client.post(
        "/api/v1/mappings",
        json={
            "endpoint_id": endpoint["id"],
            "device_id": device["id"],
            "channel_id": None,
            "enabled": True,
            "on_threshold": 25,
            "off_threshold": 88,
            "minimum_state_change_interval": 240,
        },
    ).json()

    response = client.get(f"/api/v1/endpoints/{endpoint['id']}/agent-config")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["endpoint_id"] == endpoint["id"]
    assert payload["mappings"]
    assert any(item["id"] == mapping["id"] for item in payload["mappings"])
    assert payload["mappings"][0]["on_threshold"] == 25
    assert payload["mappings"][0]["off_threshold"] == 88
    assert payload["mappings"][0]["turn_on_enabled"] is True
    assert payload["mappings"][0]["turn_off_when_charging_enabled"] is False
    assert payload["mappings"][0]["charging_off_threshold"] == 99


def test_agent_config_lookup_by_hostname_and_token():
    client = _super_admin_client()

    device = client.post(
        "/api/v1/devices",
        json={
            "name": "Agent Lookup Device",
            "device_id": "agent-lookup-device",
            "ip_address": "192.168.0.170",
            "device_type": "switch",
            "protocol_version": "3.1",
            "enabled": True,
            "encrypted_local_key": "agent-lookup-key",
        },
    ).json()
    endpoint = client.post(
        "/api/v1/endpoints",
        json={
            "hostname": "agent-lookup-endpoint",
            "ip_address": "10.0.0.44",
            "battery_percentage": 61,
            "charging": False,
            "ac_connected": True,
            "enabled": True,
        },
    ).json()
    mapping = client.post(
        "/api/v1/mappings",
        json={
            "endpoint_id": endpoint["id"],
            "device_id": device["id"],
            "channel_id": None,
            "enabled": True,
            "on_threshold": 42,
            "off_threshold": 86,
            "minimum_state_change_interval": 180,
        },
    ).json()

    from app.core.database import SessionLocal
    from app.models.system_setting import SystemSetting

    with SessionLocal() as db:
        token = db.query(SystemSetting.value).filter(SystemSetting.key == "global_agent_token").scalar()

    response = client.get(
        "/api/v1/endpoints/agent-config",
        params={"hostname": "agent-lookup-endpoint"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["hostname"] == "agent-lookup-endpoint"
    assert any(item["id"] == mapping["id"] for item in payload["mappings"])
    assert payload["mappings"][0]["on_threshold"] == 42
    assert payload["mappings"][0]["off_threshold"] == 86


def test_devices_page_has_delete_action_and_channel_expander():
    client = _super_admin_client()
    created_response = client.post(
        "/api/v1/devices",
        json={
            "name": "Expandable Device",
            "device_id": "tuya-expandable-device",
            "ip_address": "192.168.0.100",
            "device_type": "switch",
            "protocol_version": "3.1",
            "encrypted_local_key": "expandable-key",
        },
    )
    assert created_response.status_code == 201, created_response.text
    device = created_response.json()
    for index in (1, 2):
        assert client.post(
            f"/api/v1/devices/{device['id']}/channels",
            json={"channel_index": index, "name": f"Channel {index}"},
        ).status_code == 201
    assert len(client.get(f"/api/v1/devices/{device['id']}/channels").json()) == 2
    assert client.get("/devices", follow_redirects=False).status_code == 307


def test_device_state_is_changed_through_json_api(monkeypatch):
    _mock_tuya_service(monkeypatch)
    client = _super_admin_client()

    create = client.post(
        "/api/v1/devices",
        json={
            "name": "Toggle Device",
            "device_id": "tuya-toggle-device",
            "ip_address": "192.168.0.154",
            "device_type": "switch",
            "protocol_version": "3.1",
            "encrypted_local_key": "toggle-key",
        },
    )
    assert create.status_code == 201, create.text
    device_id = create.json()["id"]
    toggled = client.post(f"/api/v1/devices/{device_id}/state", json={"desired_state": True})
    assert toggled.status_code == 200, toggled.text
    assert client.get(f"/api/v1/devices/{device_id}").json()["current_state"] is True
    assert client.get("/devices", follow_redirects=False).status_code == 307


def test_ui_delete_routes_for_device_and_mapping():
    client = _super_admin_client()

    device_response = client.post(
        "/api/v1/devices",
        json={
            "name": "Delete Me",
            "device_id": "tuya-delete-device",
            "ip_address": "192.168.0.99",
            "device_type": "switch",
            "protocol_version": "3.1",
            "enabled": True,
            "encrypted_local_key": "delete-me-key",
        },
    )
    assert device_response.status_code == 201, device_response.text
    device = device_response.json()

    mapping_response = client.post(
        "/api/v1/mappings",
        json={
            "endpoint_id": _create_endpoint(client, "delete-me-endpoint"),
            "device_id": device["id"],
            "channel_id": None,
            "enabled": True,
            "on_threshold": 25,
            "off_threshold": 75,
            "minimum_state_change_interval": 120,
        },
    )
    assert mapping_response.status_code == 201, mapping_response.text
    mapping = mapping_response.json()

    delete_mapping_response = client.delete(f"/api/v1/mappings/{mapping['id']}")
    assert delete_mapping_response.status_code == 204

    delete_device_response = client.delete(f"/api/v1/devices/{device['id']}")
    assert delete_device_response.status_code == 204

    remaining_devices = client.get("/api/v1/devices")
    remaining_mappings = client.get("/api/v1/mappings")
    assert all(item["id"] != device["id"] for item in remaining_devices.json())
    assert all(item["id"] != mapping["id"] for item in remaining_mappings.json())


def test_manual_device_controls_can_force_on_and_off(monkeypatch):
    _mock_tuya_service(monkeypatch)
    client = _super_admin_client()

    device_response = client.post(
        "/api/v1/devices",
        json={
            "name": "Manual Switch",
            "device_id": "tuya-manual-switch",
            "ip_address": "192.168.0.90",
            "device_type": "switch",
            "protocol_version": "3.1",
            "enabled": True,
            "encrypted_local_key": "manual-key",
        },
    )
    assert device_response.status_code == 201, device_response.text
    device = device_response.json()

    on_response = client.post(
        f"/api/v1/devices/{device['id']}/state",
        json={"desired_state": True},
    )
    assert on_response.status_code == 200, on_response.text

    device_after_on = client.get(f"/api/v1/devices/{device['id']}")
    assert device_after_on.status_code == 200
    assert device_after_on.json()["current_state"] is True

    off_response = client.post(
        f"/api/v1/devices/{device['id']}/state",
        json={"desired_state": False},
    )
    assert off_response.status_code == 200, off_response.text

    device_after_off = client.get(f"/api/v1/devices/{device['id']}")
    assert device_after_off.status_code == 200
    assert device_after_off.json()["current_state"] is False


def test_tuya_service_uses_local_outlet_device_for_state_changes(monkeypatch):
    calls = []

    class FakeOutletDevice:
        def __init__(self, dev_id, address=None, local_key="", dev_type="default", connection_timeout=5, version=3.1, **kwargs):
            self.dev_id = dev_id
            self.address = address
            self.local_key = local_key
            self.dev_type = dev_type
            self.version = version
            self.state = True

        def turn_on(self, switch=1, nowait=False):
            calls.append(("turn_on", switch))
            self.state = True
            return {"success": True, "state": "ON"}

        def turn_off(self, switch=1, nowait=False):
            calls.append(("turn_off", switch))
            self.state = False
            return {"success": True, "state": "OFF"}

    monkeypatch.setattr("app.services.tuya_service.OutletDevice", FakeOutletDevice)

    service = __import__("app.services.tuya_service", fromlist=["TuyaService"]).TuyaService(
        device_id="tuya-real-device",
        ip_address="192.168.1.42",
        local_key="abc123",
        device_type="default",
        protocol_version="3.1",
    )

    result = __import__("asyncio").run(service.set_state("tuya-real-device", on=False, channel=1))
    assert result["success"] is True
    assert result["state"] == "OFF"
    assert calls == [("turn_off", 1)]


def test_tuya_service_discovers_local_tuya_devices(monkeypatch):
    discovered = {
        "192.168.0.44": {
            "gwId": "device-123",
            "productKey": "product-key",
            "version": "3.5",
            "name": "Desk Plug",
            "ip": "192.168.0.44",
            "localKey": "local-key-123",
        },
        "192.168.0.73": {
            "gwId": "device-456",
            "productKey": "product-key-2",
            "version": 3.3,
            "name": "Hall Lamp",
            "address": "192.168.0.73",
            "key": "local-key-456",
        },
    }

    monkeypatch.setattr("app.services.tuya_service.deviceScan", lambda **kwargs: discovered)

    response = __import__("asyncio").run(__import__("app.services.tuya_service", fromlist=["TuyaService"]).TuyaService().discover())

    assert len(response) == 2
    assert response[0]["device_id"] in {"device-123", "device-456"}
    assert response[0]["ip_address"]
    assert response[0]["protocol_version"] in {"3.5", "3.3"}
    assert any(item["local_key"] == "local-key-123" for item in response)


def test_tuya_service_defaults_to_supported_protocol_3_5():
    service = __import__("app.services.tuya_service", fromlist=["TuyaService"]).TuyaService(
        device_id="tuya-real-device-35",
        ip_address="192.168.1.43",
        local_key="abc123",
        device_type="default",
    )

    assert service.protocol_version == "3.5"


def test_tuya_service_normalizes_switch_device_type_to_default():
    service = __import__("app.services.tuya_service", fromlist=["TuyaService"]).TuyaService(
        device_id="tuya-real-device-type",
        ip_address="192.168.1.44",
        local_key="abc123",
        device_type="switch",
        protocol_version="3.5",
    )

    assert service.device_type == "default"


def test_tuya_service_reads_status_without_channel_argument(monkeypatch):
    status_calls = []

    class FakeOutletDevice:
        def __init__(self, *args, **kwargs):
            pass

        def status(self):
            status_calls.append("status")
            return {"dps": {"1": False, "2": True}}

    monkeypatch.setattr("app.services.tuya_service.OutletDevice", FakeOutletDevice)
    service = __import__("app.services.tuya_service", fromlist=["TuyaService"]).TuyaService(
        device_id="tuya-multichannel",
        ip_address="192.168.1.45",
        local_key="abc123",
        device_type="switch",
    )

    result = asyncio.run(service.get_status("tuya-multichannel", channel=2))

    assert status_calls == ["status"]
    assert result == {"device_id": "tuya-multichannel", "channel": 2, "online": True, "state": True}


def test_battery_hysteresis_turns_off_above_99_and_on_at_20_percent_below():
    from app.services.rule_engine import evaluate_battery_action

    assert evaluate_battery_action(battery=99, current_state=True, on_threshold=79, off_threshold=99) == "TURN_OFF"
    assert evaluate_battery_action(battery=78, current_state=False, on_threshold=79, off_threshold=99) == "TURN_ON"


def test_mapping_defaults_follow_20_percent_hysteresis_gap():
    from app.schemas.mapping import MappingBase

    mapping = MappingBase(endpoint_id="ep-1", device_id="dev-1")
    assert mapping.off_threshold == 99
    assert mapping.on_threshold == 79
    assert mapping.turn_on_enabled is True
    assert mapping.turn_off_when_charging_enabled is False
    assert mapping.charging_off_threshold == 99


def test_individual_channel_controls_for_multi_gang_switch(monkeypatch):
    _mock_tuya_service(monkeypatch)
    client = _super_admin_client()

    device_response = client.post(
        "/api/v1/devices",
        json={
            "name": "4-Gang Manual Test",
            "device_id": "tuya-4gang-manual",
            "ip_address": "192.168.0.70",
            "device_type": "switch",
            "protocol_version": "3.1",
            "enabled": True,
            "encrypted_local_key": "manual-4gang-key",
        },
    )
    assert device_response.status_code == 201, device_response.text
    device = device_response.json()

    channel_response = client.post(
        f"/api/v1/devices/{device['id']}/channels",
        json={
            "channel_index": 3,
            "name": "Gang 3",
            "dp_id": "3",
            "enabled": True,
        },
    )
    assert channel_response.status_code == 201, channel_response.text
    channel = channel_response.json()

    on_response = client.post(
        f"/api/v1/devices/{device['id']}/state",
        json={"desired_state": True, "channel_id": channel["id"]},
    )
    assert on_response.status_code == 200, on_response.text
    channel_after_on = client.get(f"/api/v1/devices/{device['id']}/channels/{channel['id']}")
    assert channel_after_on.status_code == 200
    assert channel_after_on.json()["current_state"] is True

    off_response = client.post(
        f"/api/v1/devices/{device['id']}/state",
        json={"desired_state": False, "channel_id": channel["id"]},
    )
    assert off_response.status_code == 200, off_response.text
    channel_after_off = client.get(f"/api/v1/devices/{device['id']}/channels/{channel['id']}")
    assert channel_after_off.status_code == 200
    assert channel_after_off.json()["current_state"] is False


def test_endpoint_api_shows_live_telemetry_and_dashboard_redirects_to_react():
    client = _super_admin_client()

    telemetry_response = client.post(
        "/api/v1/telemetry",
        headers={"Authorization": "Bearer test-endpoint-token"},
        json={
            "hostname": "LIVE-LAPTOP",
            "hardware_uuid": "c19f1d84-0a2c-4a34-bf95-a61ff3231c46",
            "ip_address": "192.168.0.77",
            "battery_percentage": 42,
            "charging": True,
            "ac_connected": True,
            "timestamp": _recent_timestamp(),
            "agent_version": "1.0.0",
        },
    )

    assert telemetry_response.status_code == 200, telemetry_response.text

    endpoints = client.get("/api/v1/endpoints")
    assert endpoints.status_code == 200
    assert any(
        endpoint["hostname"] == "LIVE-LAPTOP" and endpoint["battery"] == 42
        for endpoint in endpoints.json()
    )
    assert client.get("/", follow_redirects=False).status_code == 307


def test_telemetry_does_not_override_mapping_thresholds_with_agent_switch_state(monkeypatch):
    client = _super_admin_client()

    device_response = client.post(
        "/api/v1/devices",
        json={
            "name": "Agent Controlled Plug",
            "device_id": "tuya-agent-controlled-001",
            "ip_address": "192.168.0.93",
            "device_type": "switch",
            "protocol_version": "3.1",
            "enabled": True,
            "encrypted_local_key": "agent-controlled-key",
        },
    )
    assert device_response.status_code == 201, device_response.text
    device = device_response.json()

    from app.core.database import SessionLocal
    from app.models.device import Device as DeviceModel
    from app.models.endpoint import Endpoint
    from app.models.mapping import Mapping
    from app.models.event import AutomationEvent

    session = SessionLocal()
    created_device = session.query(DeviceModel).filter(DeviceModel.id == device["id"]).one()
    created_device.current_state = True
    created_device.last_state_change_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    session.commit()

    class FakeTuyaService:
        @staticmethod
        def from_device(device_obj):
            return FakeTuyaService()

        async def get_status(self, device_id, channel=1):
            return {"device_id": device_id, "channel": channel, "online": True, "state": True}

        async def set_state(self, device_id, on, channel=1):
            raise AssertionError("Battery below off threshold must not change the switch state.")

    monkeypatch.setattr("app.services.automation_processor.TuyaService", FakeTuyaService)

    endpoint_response = client.post(
        "/api/v1/telemetry",
        headers={"Authorization": "Bearer test-endpoint-token"},
        json={
            "hostname": "AGENT-CONTROLLED-ENDPOINT",
            "hardware_uuid": "c19f1d84-0a2c-4a34-bf95-a61ff3231c47",
            "ip_address": "192.168.0.94",
            "battery_percentage": 64,
            "charging": False,
            "ac_connected": False,
            "switch_state": False,
            "timestamp": _recent_timestamp(60),
            "agent_version": "1.0.0",
        },
    )
    assert endpoint_response.status_code == 200, endpoint_response.text

    endpoint = session.query(Endpoint).filter(Endpoint.hostname == "AGENT-CONTROLLED-ENDPOINT").one()
    session.add(
        Mapping(
            endpoint_id=endpoint.id,
            device_id=device["id"],
            channel_id=None,
            enabled=True,
            on_threshold=30,
            off_threshold=90,
            minimum_state_change_interval=30,
        )
    )
    session.commit()

    response = client.post(
        "/api/v1/telemetry",
        headers={"Authorization": "Bearer test-endpoint-token"},
        json={
            "hostname": "AGENT-CONTROLLED-ENDPOINT",
            "ip_address": "192.168.0.94",
            "battery_percentage": 64,
            "charging": False,
            "ac_connected": False,
            "switch_state": False,
            "timestamp": _recent_timestamp(),
            "agent_version": "1.0.0",
        },
    )
    assert response.status_code == 200, response.text
    _process_telemetry_outbox(session, "AGENT-CONTROLLED-ENDPOINT")

    updated_device = session.query(DeviceModel).filter(DeviceModel.id == device["id"]).one()
    assert updated_device.current_state is True
    assert (
        session.query(AutomationEvent)
        .filter(
            AutomationEvent.event_type == "TURN_OFF",
            AutomationEvent.endpoint_id == endpoint.id,
        )
        .count()
        == 0
    )
    session.close()


def test_endpoints_and_events_apis_do_not_return_scaffold_data():
    client = _super_admin_client()

    telemetry_response = client.post(
        "/api/v1/telemetry",
        headers={"Authorization": "Bearer test-endpoint-token"},
        json={
            "hostname": "REAL-ENDPOINT",
            "hardware_uuid": "c19f1d84-0a2c-4a34-bf95-a61ff3231c48",
            "ip_address": "192.168.0.88",
            "battery_percentage": 77,
            "charging": False,
            "ac_connected": True,
            "timestamp": _recent_timestamp(),
            "agent_version": "1.0.0",
        },
    )
    assert telemetry_response.status_code == 200, telemetry_response.text

    endpoints_response = client.get("/api/v1/endpoints")
    assert endpoints_response.status_code == 200
    endpoint_payloads = endpoints_response.json()
    assert any(
        item["hostname"] == "REAL-ENDPOINT"
        and item["hardware_uuid"] == "c19f1d84-0a2c-4a34-bf95-a61ff3231c48"
        for item in endpoint_payloads
    )
    assert all(item["hostname"] != "LAPTOP-001" for item in endpoint_payloads)

    events_response = client.get("/api/v1/events")
    assert events_response.status_code == 200
    assert all(event.get("hostname") != "LAPTOP-001" for event in events_response.json())
    assert client.get("/endpoints", follow_redirects=False).status_code == 307
    assert client.get("/events", follow_redirects=False).status_code == 307


def test_telemetry_turns_off_mapped_device_when_battery_exceeds_off_threshold(monkeypatch):
    _mock_tuya_service(monkeypatch)
    client = _super_admin_client()

    device_response = client.post(
        "/api/v1/devices",
        json={
            "name": "Auto Off Plug",
            "device_id": "tuya-auto-off-001",
            "ip_address": "192.168.0.80",
            "device_type": "switch",
            "protocol_version": "3.1",
            "enabled": True,
            "encrypted_local_key": "auto-off-key",
        },
    )
    assert device_response.status_code == 201, device_response.text
    device = device_response.json()

    from app.core.database import SessionLocal
    from app.models.device import Device
    from app.models.endpoint import Endpoint
    from app.models.mapping import Mapping
    from app.models.event import AutomationEvent

    session = SessionLocal()
    created_device = session.query(Device).filter(Device.id == device["id"]).one()
    created_device.current_state = True
    created_device.last_state_change_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    session.commit()

    telemetry_response = client.post(
        "/api/v1/telemetry",
        headers={"Authorization": "Bearer test-endpoint-token"},
        json={
            "hostname": "AUTO-OFF-ENDPOINT",
            "hardware_uuid": "c19f1d84-0a2c-4a34-bf95-a61ff3231c49",
            "ip_address": "192.168.0.81",
            "battery_percentage": 99,
            "charging": True,
            "ac_connected": True,
            "timestamp": _recent_timestamp(60),
            "agent_version": "1.0.0",
        },
    )
    assert telemetry_response.status_code == 200, telemetry_response.text

    endpoint = session.query(Endpoint).filter(Endpoint.hostname == "AUTO-OFF-ENDPOINT").one()
    session.add(
        Mapping(
            endpoint_id=endpoint.id,
            device_id=device["id"],
            channel_id=None,
            enabled=True,
            on_threshold=20,
            off_threshold=99,
            minimum_state_change_interval=30,
        )
    )
    session.commit()

    off_response = client.post(
        "/api/v1/telemetry",
        headers={"Authorization": "Bearer test-endpoint-token"},
        json={
            "hostname": "AUTO-OFF-ENDPOINT",
            "ip_address": "192.168.0.81",
            "battery_percentage": 99,
            "charging": True,
            "ac_connected": True,
            "timestamp": _recent_timestamp(),
            "agent_version": "1.0.0",
        },
    )
    assert off_response.status_code == 200, off_response.text
    _process_telemetry_outbox(session, "AUTO-OFF-ENDPOINT")

    updated_device = session.query(Device).filter(Device.id == device["id"]).one()
    assert updated_device.current_state is False
    off_event = (
        session.query(AutomationEvent)
        .filter(
            AutomationEvent.event_type == "TURN_OFF",
            AutomationEvent.endpoint_id == endpoint.id,
        )
        .one()
    )
    assert off_event.reason == "Battery 99% is at or above the turn-off threshold of 99%."

    session.close()


def test_telemetry_supports_turn_off_only_and_charging_completion(monkeypatch):
    _mock_tuya_service(monkeypatch)
    client = _super_admin_client()
    device_response = client.post(
        "/api/v1/devices",
        json={
            "name": "Charge Completion Plug",
            "device_id": "tuya-charge-completion",
            "ip_address": "192.168.0.82",
            "device_type": "switch",
            "protocol_version": "3.1",
            "enabled": True,
            "encrypted_local_key": "charge-completion-key",
        },
    )
    assert device_response.status_code == 201, device_response.text
    device = device_response.json()

    from app.core.database import SessionLocal
    from app.models.device import Device
    from app.models.endpoint import Endpoint
    from app.models.event import AutomationEvent
    from app.models.mapping import Mapping

    session = SessionLocal()
    first_telemetry = client.post(
        "/api/v1/telemetry",
        headers={"Authorization": f"Bearer {TEST_GLOBAL_AGENT_TOKEN}"},
        json={
            "hostname": "CHARGE-COMPLETION-ENDPOINT",
            "hardware_uuid": "c19f1d84-0a2c-4a34-bf95-a61ff3231c4d",
            "ip_address": "192.168.0.83",
            "battery_percentage": 15,
            "charging": False,
            "ac_connected": False,
            "timestamp": _recent_timestamp(60),
            "agent_version": "1.0.0",
        },
    )
    assert first_telemetry.status_code == 200, first_telemetry.text
    endpoint = session.query(Endpoint).filter(
        Endpoint.hostname == "CHARGE-COMPLETION-ENDPOINT"
    ).one()
    session.add(
        Mapping(
            endpoint_id=endpoint.id,
            device_id=device["id"],
            enabled=True,
            turn_on_enabled=False,
            on_threshold=20,
            off_threshold=99,
            turn_off_when_charging_enabled=True,
            charging_off_threshold=85,
            minimum_state_change_interval=30,
        )
    )
    session.commit()

    low_battery = client.post(
        "/api/v1/telemetry",
        headers={"Authorization": f"Bearer {TEST_GLOBAL_AGENT_TOKEN}"},
        json={
            "hostname": "CHARGE-COMPLETION-ENDPOINT",
            "ip_address": "192.168.0.83",
            "battery_percentage": 15,
            "charging": False,
            "ac_connected": False,
            "timestamp": _recent_timestamp(),
            "agent_version": "1.0.0",
        },
    )
    assert low_battery.status_code == 200, low_battery.text
    _process_telemetry_outbox(session, "CHARGE-COMPLETION-ENDPOINT")
    assert session.query(Device).filter(Device.id == device["id"]).one().current_state is False
    assert session.query(AutomationEvent).filter(
        AutomationEvent.event_type == "TURN_ON",
        AutomationEvent.endpoint_id == endpoint.id,
    ).count() == 0

    switched_device = session.query(Device).filter(Device.id == device["id"]).one()
    switched_device.current_state = True
    switched_device.last_state_change_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    session.commit()
    not_charging_telemetry = client.post(
        "/api/v1/telemetry",
        headers={"Authorization": f"Bearer {TEST_GLOBAL_AGENT_TOKEN}"},
        json={
            "hostname": "CHARGE-COMPLETION-ENDPOINT",
            "ip_address": "192.168.0.83",
            "battery_percentage": 85,
            "charging": False,
            "ac_connected": True,
            "timestamp": _recent_timestamp(),
            "agent_version": "1.0.0",
        },
    )
    assert not_charging_telemetry.status_code == 200, not_charging_telemetry.text
    _process_telemetry_outbox(session, "CHARGE-COMPLETION-ENDPOINT")
    assert session.query(Device).filter(Device.id == device["id"]).one().current_state is True
    assert session.query(AutomationEvent).filter(
        AutomationEvent.event_type == "TURN_OFF",
        AutomationEvent.endpoint_id == endpoint.id,
    ).count() == 0

    charging_telemetry = client.post(
        "/api/v1/telemetry",
        headers={"Authorization": f"Bearer {TEST_GLOBAL_AGENT_TOKEN}"},
        json={
            "hostname": "CHARGE-COMPLETION-ENDPOINT",
            "ip_address": "192.168.0.83",
            "battery_percentage": 85,
            "charging": True,
            "ac_connected": True,
            "timestamp": _recent_timestamp(),
            "agent_version": "1.0.0",
        },
    )
    assert charging_telemetry.status_code == 200, charging_telemetry.text
    _process_telemetry_outbox(session, "CHARGE-COMPLETION-ENDPOINT")

    updated_device = session.query(Device).filter(Device.id == device["id"]).one()
    assert updated_device.current_state is False
    event = session.query(AutomationEvent).filter(
        AutomationEvent.event_type == "TURN_OFF",
        AutomationEvent.endpoint_id == endpoint.id,
    ).one()
    assert event.reason == (
        "Battery 85% is charging and at or above the charging turn-off threshold of 85%."
    )
    session.close()


def test_telemetry_uses_live_device_status_when_db_state_is_stale(monkeypatch):
    client = _super_admin_client()

    device_response = client.post(
        "/api/v1/devices",
        json={
            "name": "Live State Plug",
            "device_id": "tuya-live-state-001",
            "ip_address": "192.168.0.90",
            "device_type": "switch",
            "protocol_version": "3.1",
            "enabled": True,
            "encrypted_local_key": "live-state-key",
        },
    )
    assert device_response.status_code == 201, device_response.text
    device = device_response.json()

    from app.core.database import SessionLocal
    from app.models.device import Device as DeviceModel
    from app.models.endpoint import Endpoint
    from app.models.mapping import Mapping
    from app.models.event import AutomationEvent

    session = SessionLocal()
    created_device = session.query(DeviceModel).filter(DeviceModel.id == device["id"]).one()
    created_device.current_state = False
    created_device.last_state_change_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    session.commit()

    class FakeTuyaService:
        @staticmethod
        def from_device(device_obj):
            return FakeTuyaService()

        async def get_status(self, device_id, channel=1):
            return {"device_id": device_id, "channel": channel, "online": True, "state": True}

        async def set_state(self, device_id, on, channel=1):
            return {"device_id": device_id, "channel": channel, "success": True, "state": "OFF" if not on else "ON"}

    monkeypatch.setattr("app.services.automation_processor.TuyaService", FakeTuyaService)

    telemetry_response = client.post(
        "/api/v1/telemetry",
        headers={"Authorization": "Bearer test-endpoint-token"},
        json={
            "hostname": "LIVE-STATE-ENDPOINT",
            "hardware_uuid": "c19f1d84-0a2c-4a34-bf95-a61ff3231c4b",
            "ip_address": "192.168.0.91",
            "battery_percentage": 99,
            "charging": True,
            "ac_connected": True,
            "timestamp": _recent_timestamp(60),
            "agent_version": "1.0.0",
        },
    )
    assert telemetry_response.status_code == 200, telemetry_response.text

    endpoint = session.query(Endpoint).filter(Endpoint.hostname == "LIVE-STATE-ENDPOINT").one()
    session.add(
        Mapping(
            endpoint_id=endpoint.id,
            device_id=device["id"],
            channel_id=None,
            enabled=True,
            on_threshold=79,
            off_threshold=99,
            minimum_state_change_interval=30,
        )
    )
    session.commit()

    second_response = client.post(
        "/api/v1/telemetry",
        headers={"Authorization": "Bearer test-endpoint-token"},
        json={
            "hostname": "LIVE-STATE-ENDPOINT",
            "ip_address": "192.168.0.91",
            "battery_percentage": 99,
            "charging": True,
            "ac_connected": True,
            "timestamp": _recent_timestamp(),
            "agent_version": "1.0.0",
        },
    )
    assert second_response.status_code == 200, second_response.text
    _process_telemetry_outbox(session, "LIVE-STATE-ENDPOINT")

    updated_device = session.query(DeviceModel).filter(DeviceModel.id == device["id"]).one()
    assert updated_device.current_state is False
    assert session.query(AutomationEvent).filter(AutomationEvent.event_type == "TURN_OFF").count() >= 1
    session.close()
