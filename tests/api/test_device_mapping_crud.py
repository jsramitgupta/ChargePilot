import os
from datetime import timedelta
from uuid import uuid4

from datetime import datetime, timezone

os.environ["CHARGEPILOT_DATABASE_URL"] = "sqlite://"

from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from app.core.database import Base, _ensure_table_columns, engine
from app.main import app


Base.metadata.create_all(bind=engine)


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


def test_device_and_mapping_crud_flow():
    client = TestClient(app)

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

    endpoint_id = str(uuid4())
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


def test_device_channel_mapping_for_multi_gang_switch():
    client = TestClient(app)

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

    endpoint_id = str(uuid4())
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
    client = TestClient(app)

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

    endpoint_id = str(uuid4())
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

    register = client.post(
        "/register",
        data={"username": "threshold_admin", "password": "secret123"},
        follow_redirects=False,
    )
    assert register.status_code in {200, 302, 303}, register.text

    login = client.post(
        "/login",
        data={"username": "threshold_admin", "password": "secret123"},
        follow_redirects=False,
    )
    assert login.status_code in {200, 302, 303}, login.text

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
    mapping = client.post(
        "/api/v1/mappings",
        json={
            "endpoint_id": endpoint["id"],
            "device_id": device["id"],
            "channel_id": None,
            "enabled": True,
            "on_threshold": 35,
            "off_threshold": 90,
            "minimum_state_change_interval": 300,
        },
    ).json()

    page = client.get("/mappings")
    assert page.status_code == 200, page.text
    body = page.text
    assert "on_threshold" in body
    assert "off_threshold" in body
    assert str(mapping["id"]) in body
    assert "Current mappings" in body
    assert "Add mapping" in body
    assert 'id="mapping-modal"' in body
    assert 'data-mapping-wizard-step="4"' in body
    assert "Review before saving" in body
    assert "300 sec" in body


def test_mappings_page_groups_channel_choices_under_expandable_switches():
    client = TestClient(app)
    register = client.post(
        "/register",
        data={"username": "channel_picker_user", "password": "secret123"},
        follow_redirects=False,
    )
    assert register.status_code in {200, 302, 303}, register.text
    login = client.post(
        "/login",
        data={"username": "channel_picker_user", "password": "secret123"},
        follow_redirects=False,
    )
    assert login.status_code in {200, 302, 303}, login.text

    for name, device_id, channel_count in (
        ("Desk Switch", "desk-switch", 2),
        ("Hall Switch", "hall-switch", 1),
    ):
        response = client.post(
            "/devices",
            data={
                "name": name,
                "device_id": device_id,
                "ip_address": "192.168.1.20",
                "device_type": "switch",
                "protocol_version": "3.5",
                "encrypted_local_key": "local-key",
                "channel_count": channel_count,
            },
            follow_redirects=False,
        )
        assert response.status_code == 303, response.text

    page = client.get("/mappings")
    assert page.status_code == 200, page.text
    body = page.text
    assert 'class="channel-picker-group" data-device-group=' in body
    assert 'data-channel-group-toggle=' in body
    assert 'data-picker-channel=' in body
    assert 'data-device-select=' in body
    assert "Desk Switch" in body
    assert "Hall Switch" in body
    assert "Channel 1" in body
    assert "Channel 2" in body
    assert 'id="deviceSelect" type="hidden" name="device_id"' in body
    assert 'id="deviceSelect" name="device_id"' not in body
    assert 'id="channel-picker-selected" class="channel-picker-selection-note"' in body
    assert 'id="channelSelect" name="channel_id"' in body


def test_endpoint_agent_config_returns_live_threshold_settings():
    client = TestClient(app)

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


def test_agent_config_lookup_by_hostname_and_token():
    client = TestClient(app)

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
    client = TestClient(app)

    register = client.post(
        "/register",
        data={"username": "device_admin", "password": "secret123"},
        follow_redirects=False,
    )
    assert register.status_code in {200, 302, 303}, register.text

    login = client.post(
        "/login",
        data={"username": "device_admin", "password": "secret123"},
        follow_redirects=False,
    )
    assert login.status_code in {200, 302, 303}, login.text

    created_response = client.post(
        "/devices",
        data={
            "name": "Expandable Device",
            "device_id": "tuya-expandable-device",
            "ip_address": "192.168.0.100",
            "device_type": "switch",
            "protocol_version": "3.1",
            "encrypted_local_key": "expandable-key",
            "channel_count": "2",
        },
        follow_redirects=False,
    )
    assert created_response.status_code in {200, 302, 303}, created_response.text

    page = client.get("/devices")
    assert page.status_code == 200, page.text
    body = page.text
    assert "Expandable Device" in body
    assert "/delete" in body
    assert "Master" not in body
    assert "switch-button-master" not in body
    assert body.count("state-toggle-form") == 2


def test_device_toggle_actions_are_rendered_on_devices_page():
    client = TestClient(app)

    register = client.post(
        "/register",
        data={"username": "toggle_admin", "password": "secret123"},
        follow_redirects=False,
    )
    assert register.status_code in {200, 302, 303}, register.text

    login = client.post(
        "/login",
        data={"username": "toggle_admin", "password": "secret123"},
        follow_redirects=False,
    )
    assert login.status_code in {200, 302, 303}, login.text

    create = client.post(
        "/devices",
        data={
            "name": "Toggle Device",
            "device_id": "tuya-toggle-device",
            "ip_address": "192.168.0.154",
            "device_type": "switch",
            "protocol_version": "3.1",
            "encrypted_local_key": "toggle-key",
            "channel_count": "1",
        },
        follow_redirects=False,
    )
    assert create.status_code in {200, 302, 303}, create.text

    page = client.get("/devices")
    assert page.status_code == 200, page.text
    body = page.text
    assert "/devices/" in body
    assert "/turn-on" in body or "/turn-off" in body
    assert body.count("state-toggle-form") == 1
    assert "data-channel-id=" in body


def test_ui_delete_routes_for_device_and_mapping():
    client = TestClient(app)

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
            "endpoint_id": str(uuid4()),
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

    delete_mapping_response = client.post(f"/mappings/{mapping['id']}/delete")
    assert delete_mapping_response.status_code in {200, 303}, delete_mapping_response.text

    delete_device_response = client.post(f"/devices/{device['id']}/delete")
    assert delete_device_response.status_code in {200, 303}, delete_device_response.text

    remaining_devices = client.get("/api/v1/devices")
    remaining_mappings = client.get("/api/v1/mappings")
    assert all(item["id"] != device["id"] for item in remaining_devices.json())
    assert all(item["id"] != mapping["id"] for item in remaining_mappings.json())


def test_manual_device_controls_can_force_on_and_off():
    client = TestClient(app)

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

    on_response = client.post(f"/devices/{device['id']}/turn-on")
    assert on_response.status_code in {200, 303}, on_response.text

    device_after_on = client.get(f"/api/v1/devices/{device['id']}")
    assert device_after_on.status_code == 200
    assert device_after_on.json()["current_state"] is True

    off_response = client.post(f"/devices/{device['id']}/turn-off")
    assert off_response.status_code in {200, 303}, off_response.text

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


def test_battery_hysteresis_turns_off_above_99_and_on_at_20_percent_below():
    from app.services.rule_engine import evaluate_battery_action

    assert evaluate_battery_action(battery=99, current_state=True, on_threshold=79, off_threshold=99) == "TURN_OFF"
    assert evaluate_battery_action(battery=78, current_state=False, on_threshold=79, off_threshold=99) == "TURN_ON"


def test_mapping_defaults_follow_20_percent_hysteresis_gap():
    from app.schemas.mapping import MappingBase

    mapping = MappingBase(endpoint_id="ep-1", device_id="dev-1")
    assert mapping.off_threshold == 99
    assert mapping.on_threshold == 79


def test_individual_channel_controls_for_multi_gang_switch():
    client = TestClient(app)

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

    on_response = client.post(f"/devices/{device['id']}/channels/{channel['id']}/turn-on")
    assert on_response.status_code in {200, 303}, on_response.text
    channel_after_on = client.get(f"/api/v1/devices/{device['id']}/channels/{channel['id']}")
    assert channel_after_on.status_code == 200
    assert channel_after_on.json()["current_state"] is True

    off_response = client.post(f"/devices/{device['id']}/channels/{channel['id']}/turn-off")
    assert off_response.status_code in {200, 303}, off_response.text
    channel_after_off = client.get(f"/api/v1/devices/{device['id']}/channels/{channel['id']}")
    assert channel_after_off.status_code == 200
    assert channel_after_off.json()["current_state"] is False


def test_dashboard_shows_live_endpoint_telemetry():
    client = TestClient(app)

    telemetry_response = client.post(
        "/api/v1/telemetry",
        headers={"Authorization": "Bearer test-endpoint-token"},
        json={
            "hostname": "LIVE-LAPTOP",
            "ip_address": "192.168.0.77",
            "battery_percentage": 42,
            "charging": True,
            "ac_connected": True,
            "timestamp": "2026-10-05T18:00:00Z",
            "agent_version": "1.0.0",
        },
    )

    assert telemetry_response.status_code == 200, telemetry_response.text

    dashboard_response = client.get("/")
    assert dashboard_response.status_code == 200
    body = dashboard_response.text
    assert "LIVE-LAPTOP" in body
    assert "42%" in body


def test_telemetry_does_not_override_mapping_thresholds_with_agent_switch_state(monkeypatch):
    client = TestClient(app)

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

    monkeypatch.setattr("app.api.telemetry.TuyaService", FakeTuyaService)

    endpoint_response = client.post(
        "/api/v1/telemetry",
        headers={"Authorization": "Bearer test-endpoint-token"},
        json={
            "hostname": "AGENT-CONTROLLED-ENDPOINT",
            "ip_address": "192.168.0.94",
            "battery_percentage": 64,
            "charging": False,
            "ac_connected": False,
            "switch_state": False,
            "timestamp": "2026-10-05T18:40:00Z",
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
            "timestamp": "2026-10-05T18:41:00Z",
            "agent_version": "1.0.0",
        },
    )
    assert response.status_code == 200, response.text

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


def test_endpoints_and_events_pages_do_not_render_scaffold_data():
    client = TestClient(app)

    telemetry_response = client.post(
        "/api/v1/telemetry",
        headers={"Authorization": "Bearer test-endpoint-token"},
        json={
            "hostname": "REAL-ENDPOINT",
            "ip_address": "192.168.0.88",
            "battery_percentage": 77,
            "charging": False,
            "ac_connected": True,
            "timestamp": "2026-10-05T18:10:00Z",
            "agent_version": "1.0.0",
        },
    )
    assert telemetry_response.status_code == 200, telemetry_response.text

    endpoints_response = client.get("/endpoints")
    assert endpoints_response.status_code == 200
    endpoints_body = endpoints_response.text
    assert "REAL-ENDPOINT" in endpoints_body
    assert "LAPTOP-001" not in endpoints_body

    events_response = client.get("/events")
    assert events_response.status_code == 200
    events_body = events_response.text
    assert "REAL-ENDPOINT" in events_body or "TURN_ON" in events_body or "Automation Events" in events_body
    assert "LAPTOP-001" not in events_body


def test_telemetry_turns_off_mapped_device_when_battery_exceeds_off_threshold():
    client = TestClient(app)

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

    db = next(iter(__import__('app.core.database', fromlist=['SessionLocal']).SessionLocal().session_factory.values())) if False else None
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
            "ip_address": "192.168.0.81",
            "battery_percentage": 99,
            "charging": True,
            "ac_connected": True,
            "timestamp": "2026-10-05T18:20:00Z",
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
            "timestamp": "2026-10-05T18:21:00Z",
            "agent_version": "1.0.0",
        },
    )
    assert off_response.status_code == 200, off_response.text

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


def test_telemetry_uses_live_device_status_when_db_state_is_stale(monkeypatch):
    client = TestClient(app)

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

    monkeypatch.setattr("app.api.telemetry.TuyaService", FakeTuyaService)

    telemetry_response = client.post(
        "/api/v1/telemetry",
        headers={"Authorization": "Bearer test-endpoint-token"},
        json={
            "hostname": "LIVE-STATE-ENDPOINT",
            "ip_address": "192.168.0.91",
            "battery_percentage": 99,
            "charging": True,
            "ac_connected": True,
            "timestamp": "2026-10-05T18:30:00Z",
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
            "timestamp": "2026-10-05T18:31:00Z",
            "agent_version": "1.0.0",
        },
    )
    assert second_response.status_code == 200, second_response.text

    updated_device = session.query(DeviceModel).filter(DeviceModel.id == device["id"]).one()
    assert updated_device.current_state is False
    assert session.query(AutomationEvent).filter(AutomationEvent.event_type == "TURN_OFF").count() >= 1
    session.close()
