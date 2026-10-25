from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import SessionLocal
from app.main import app
from app.models.connector import DeviceCommand, SiteConnector
from app.models.device import Device
from app.models.endpoint import Endpoint
from app.models.event import AutomationEvent
from app.models.mapping import Mapping
from app.services.local_key_service import decrypt_local_key
from conftest import api_login, register_standard_user, register_tenant_admin


def _tenant_admin_client(username: str) -> TestClient:
    client = TestClient(app)
    register_tenant_admin(client, username, "secret12345678", f"{username} site")
    return client


def _enroll_connector(client: TestClient, name: str = "Office LAN") -> tuple[str, str]:
    created = client.post("/api/v1/connectors/enrollment-codes", json={"name": name})
    assert created.status_code == 201, created.text
    assert created.headers["cache-control"] == "private, no-store"
    enrollment_code = created.json()["enrollment_code"]
    response = client.post(
        "/api/v1/connectors/enroll",
        headers={"Authorization": f"Bearer {enrollment_code}"},
        json={"version": "test"},
    )
    assert response.status_code == 200, response.text
    return response.json()["connector_id"], response.json()["token"]


@pytest.mark.parametrize(
    ("battery", "physical_state", "cached_state", "desired_state"),
    [
        (50, False, True, True),
        (95, True, False, False),
    ],
)
def test_live_connector_status_reconciles_manual_switch_changes(
    battery: int,
    physical_state: bool,
    cached_state: bool,
    desired_state: bool,
):
    owner = _tenant_admin_client(f"connector_reconcile_{battery}")
    connector_id, token = _enroll_connector(owner, "Reconciliation LAN")
    device_response = owner.post(
        "/api/v1/devices",
        json={
            "name": "Reconciliation switch",
            "device_id": f"reconcile-device-{battery}-{physical_state}",
            "ip_address": "192.168.1.44",
            "device_type": "switch",
            "protocol_version": "3.5",
            "encrypted_local_key": "reconcile-local-key",
        },
    )
    assert device_response.status_code == 201, device_response.text
    device_id = device_response.json()["id"]
    assigned = owner.put(
        f"/api/v1/devices/{device_id}/connector",
        json={"connector_id": connector_id},
    )
    assert assigned.status_code == 200, assigned.text

    with SessionLocal() as db:
        connector = db.query(SiteConnector).filter(SiteConnector.id == connector_id).one()
        device = db.query(Device).filter(Device.id == device_id).one()
        device.current_state = cached_state
        endpoint = Endpoint(
            tenant_id=connector.tenant_id,
            hostname=f"reconcile-endpoint-{battery}-{physical_state}",
            platform="windows",
            battery_percentage=battery,
            charging=False,
            last_seen_at=datetime.now(UTC),
            enabled=True,
            automation_enabled=True,
        )
        db.add(endpoint)
        db.flush()
        db.add(
            Mapping(
                tenant_id=connector.tenant_id,
                endpoint_id=endpoint.id,
                device_id=device.id,
                enabled=True,
                on_threshold=80,
                off_threshold=90,
                minimum_state_change_interval=300,
            )
        )
        db.commit()

    headers = {"Authorization": f"Bearer {token}"}
    claim = owner.post("/api/v1/connectors/commands/claim", headers=headers, json={})
    assert claim.status_code == 200, claim.text
    status_command = claim.json()["command"]
    assert status_command["operation"] == "get_status"

    result = owner.post(
        f"/api/v1/connectors/commands/{status_command['id']}/result",
        headers=headers,
        json={"success": True, "result": {"state": physical_state}},
    )
    assert result.status_code == 200, result.text

    with SessionLocal() as db:
        correction = (
            db.query(DeviceCommand)
            .filter(
                DeviceCommand.device_id == device_id,
                DeviceCommand.operation == "set_state",
            )
            .one()
        )
        assert correction.status == "queued"
        assert correction.desired_state is desired_state
        assert correction.context_json
        device = db.query(Device).filter(Device.id == device_id).one()
        assert device.current_state is physical_state


def test_connector_status_poll_is_deduplicated_and_skips_stale_telemetry():
    owner = _tenant_admin_client("connector_status_poll_freshness")
    connector_id, token = _enroll_connector(owner, "Freshness LAN")
    device_response = owner.post(
        "/api/v1/devices",
        json={
            "name": "Freshness switch",
            "device_id": "freshness-poll-device",
            "ip_address": "192.168.1.45",
            "device_type": "switch",
            "protocol_version": "3.5",
            "encrypted_local_key": "freshness-local-key",
        },
    )
    assert device_response.status_code == 201, device_response.text
    device_id = device_response.json()["id"]
    assigned = owner.put(
        f"/api/v1/devices/{device_id}/connector",
        json={"connector_id": connector_id},
    )
    assert assigned.status_code == 200, assigned.text

    with SessionLocal() as db:
        connector = db.query(SiteConnector).filter(SiteConnector.id == connector_id).one()
        device = db.query(Device).filter(Device.id == device_id).one()
        endpoint = Endpoint(
            tenant_id=connector.tenant_id,
            hostname="freshness-poll-endpoint",
            platform="windows",
            battery_percentage=90,
            charging=False,
            last_seen_at=datetime.now(UTC) - timedelta(minutes=20),
            enabled=True,
            automation_enabled=True,
        )
        db.add(endpoint)
        db.flush()
        db.add(
            Mapping(
                tenant_id=connector.tenant_id,
                endpoint_id=endpoint.id,
                device_id=device.id,
                enabled=True,
            )
        )
        db.commit()

    headers = {"Authorization": f"Bearer {token}"}
    stale_claim = owner.post("/api/v1/connectors/commands/claim", headers=headers, json={})
    assert stale_claim.status_code == 200, stale_claim.text
    assert stale_claim.json()["command"] is None

    with SessionLocal() as db:
        endpoint = db.query(Endpoint).filter(Endpoint.hostname == "freshness-poll-endpoint").one()
        endpoint.last_seen_at = datetime.now(UTC)
        endpoint.automation_enabled = False
        db.commit()

    disabled_claim = owner.post("/api/v1/connectors/commands/claim", headers=headers, json={})
    assert disabled_claim.status_code == 200, disabled_claim.text
    assert disabled_claim.json()["command"] is None

    with SessionLocal() as db:
        endpoint = db.query(Endpoint).filter(Endpoint.hostname == "freshness-poll-endpoint").one()
        endpoint.automation_enabled = True
        db.commit()

    fresh_claim = owner.post("/api/v1/connectors/commands/claim", headers=headers, json={})
    assert fresh_claim.status_code == 200, fresh_claim.text
    status_command = fresh_claim.json()["command"]
    assert status_command["operation"] == "get_status"

    repeated_claim = owner.post("/api/v1/connectors/commands/claim", headers=headers, json={})
    assert repeated_claim.status_code == 200, repeated_claim.text
    assert repeated_claim.json()["command"] is None

    result = owner.post(
        f"/api/v1/connectors/commands/{status_command['id']}/result",
        headers=headers,
        json={"success": True, "result": {"state": False}},
    )
    assert result.status_code == 200, result.text
    no_early_repoll = owner.post("/api/v1/connectors/commands/claim", headers=headers, json={})
    assert no_early_repoll.status_code == 200, no_early_repoll.text
    assert no_early_repoll.json()["command"] is None

    with SessionLocal() as db:
        completed_status = db.query(DeviceCommand).filter(DeviceCommand.id == status_command["id"]).one()
        completed_status.completed_at = datetime.now(UTC) - timedelta(seconds=61)
        db.commit()

    due_repoll = owner.post("/api/v1/connectors/commands/claim", headers=headers, json={})
    assert due_repoll.status_code == 200, due_repoll.text
    assert due_repoll.json()["command"]["operation"] == "get_status"


def test_connector_api_lists_status_for_authenticated_tenant():
    client = _tenant_admin_client("connector_list_owner")
    created = client.post("/api/v1/connectors/enrollment-codes", json={"name": "Office LAN"})
    assert created.status_code == 201, created.text

    response = client.get("/api/v1/connectors")

    assert response.status_code == 200, response.text
    connectors = response.json()
    assert len(connectors) == 1
    assert connectors[0]["name"] == "Office LAN"
    assert connectors[0]["tenant_name"] == "connector_list_owner site"
    assert connectors[0]["is_enrolled"] is False
    assert connectors[0]["is_online"] is False


def test_super_admin_can_create_a_switch_for_the_selected_connector_tenant():
    admin = TestClient(app)
    api_login(admin, "admin", "change-me")
    tenant = admin.post("/api/v1/admin/tenants", json={"name": "Connector setup tenant"})
    assert tenant.status_code == 201, tenant.text

    created = admin.post(
        "/api/v1/connectors/enrollment-codes",
        json={"name": "Remote LAN", "tenant_id": tenant.json()["id"]},
    )
    assert created.status_code == 201, created.text
    enrolled = admin.post(
        "/api/v1/connectors/enroll",
        headers={"Authorization": f"Bearer {created.json()['enrollment_code']}"},
        json={"version": "test"},
    )
    assert enrolled.status_code == 200, enrolled.text

    device = admin.post(
        "/api/v1/devices",
        json={
            "name": "Remote switch",
            "device_id": "super-admin-connector-device",
            "encrypted_local_key": "test-local-key",
            "tenant_id": tenant.json()["id"],
        },
    )
    assert device.status_code == 201, device.text
    assert device.json()["tenant_id"] == tenant.json()["id"]

    assigned = admin.put(
        f"/api/v1/devices/{device.json()['id']}/connector",
        json={"connector_id": enrolled.json()["connector_id"]},
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["connector_id"] == enrolled.json()["connector_id"]


def test_tenant_user_cannot_create_a_device_in_another_tenant():
    admin = TestClient(app)
    api_login(admin, "admin", "change-me")
    other_tenant = admin.post("/api/v1/admin/tenants", json={"name": "Other device tenant"})
    assert other_tenant.status_code == 201, other_tenant.text
    client = _tenant_admin_client("device_tenant_scope_owner")

    device = client.post(
        "/api/v1/devices",
        json={
            "name": "Tenant switch",
            "device_id": "tenant-scope-device",
            "encrypted_local_key": "test-local-key",
            "tenant_id": other_tenant.json()["id"],
        },
    )

    assert device.status_code == 201, device.text
    assert device.json()["tenant_id"] != other_tenant.json()["id"]
    assert device.json()["tenant_id"] is not None


def test_react_connector_api_creates_revokes_and_deletes_connectors():
    client = _tenant_admin_client("connector_react_workflow")
    created = client.post(
        "/api/v1/connectors/enrollment-codes",
        json={"name": "React LAN"},
    )

    assert created.status_code == 201, created.text
    assert created.headers["cache-control"] == "private, no-store"
    payload = created.json()
    assert payload["name"] == "React LAN"
    assert payload["enrollment_code"]

    listed = client.get("/api/v1/connectors")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == payload["id"]
    assert listed.json()[0]["is_enrolled"] is False

    renamed = client.patch(
        f"/api/v1/connectors/{payload['id']}",
        json={"name": "Upper floor LAN"},
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json() == {"id": payload["id"], "name": "Upper floor LAN"}
    assert client.get("/api/v1/connectors").json()[0]["name"] == "Upper floor LAN"
    blank_name = client.patch(
        f"/api/v1/connectors/{payload['id']}",
        json={"name": "   "},
    )
    assert blank_name.status_code == 422

    revoked = client.post(f"/api/v1/connectors/{payload['id']}/revoke")
    assert revoked.status_code == 200, revoked.text
    assert revoked.json() == {"status": "revoked"}

    deleted = client.delete(f"/api/v1/connectors/{payload['id']}")
    assert deleted.status_code == 204
    assert client.get("/api/v1/connectors").json() == []


def test_connector_rename_requires_admin_and_respects_tenant_scope():
    owner = _tenant_admin_client("connector_rename_scope_owner")
    connector = owner.post(
        "/api/v1/connectors/enrollment-codes",
        json={"name": "Private LAN"},
    )
    assert connector.status_code == 201, connector.text
    connector_id = connector.json()["id"]

    viewer = TestClient(app)
    register_standard_user(viewer, "connector_rename_viewer", "standard-user-password")
    denied = viewer.patch(
        f"/api/v1/connectors/{connector_id}",
        json={"name": "Changed by viewer"},
    )
    assert denied.status_code == 403

    other_tenant = _tenant_admin_client("connector_rename_other_owner")
    hidden = other_tenant.patch(
        f"/api/v1/connectors/{connector_id}",
        json={"name": "Changed across tenants"},
    )
    assert hidden.status_code == 404
    assert owner.get("/api/v1/connectors").json()[0]["name"] == "Private LAN"


def test_connector_enrollment_code_creation_requires_admin_and_tenant():
    client = TestClient(app)
    register_standard_user(client, "connector_viewer", "standard-user-password")

    denied = client.post(
        "/api/v1/connectors/enrollment-codes",
        json={"name": "Not allowed"},
    )

    assert denied.status_code == 403
    assert client.get("/api/v1/admin/users").status_code == 403


def test_react_admin_api_limits_user_and_tenant_data_to_authorized_roles():
    client = _tenant_admin_client("react_admin_api_owner")

    users = client.get("/api/v1/admin/users")
    tenants = client.get("/api/v1/admin/tenants")

    assert users.status_code == 200
    assert len(users.json()) == 1
    assert users.json()[0]["username"] == "react_admin_api_owner"
    assert "password_hash" not in users.json()[0]
    assert tenants.status_code == 403


def test_agent_setup_api_supplies_token_free_install_command(monkeypatch):
    monkeypatch.setattr(settings, "api_url", "https://api.example.test")
    client = _tenant_admin_client("react_agent_setup")

    response = client.get("/api/v1/agent/setup")

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "private, no-store"
    payload = response.json()
    assert set(payload) == {"install_command", "is_super_admin"}
    assert payload["install_command"].startswith('iex "& { $(irm ')
    assert "$(irm 'https://api.example.test/agent/install.ps1')" in payload["install_command"]
    assert "-ServerUrl 'https://api.example.test'" in payload["install_command"]
    assert "-EndpointToken " not in payload["install_command"]


def test_connector_source_download_is_disabled_for_private_source():
    client = TestClient(app)
    response = client.get("/connectors/download")

    assert response.status_code == 410
    assert "source archives are no longer distributed" in response.json()["detail"]


def test_python_connector_installer_is_disabled():
    response = TestClient(app).get("/connectors/install.sh")

    assert response.status_code == 410
    assert "Use the published Docker image" in response.json()["detail"]


def test_enrollment_code_is_single_use_and_commands_wait_for_connector_ack():
    client = _tenant_admin_client("connector_owner")
    connector_id, token = _enroll_connector(client)
    reused = client.post(
        "/api/v1/connectors/enroll",
        headers={"Authorization": f"Bearer {token}"},
        json={"version": "test"},
    )
    assert reused.status_code == 401

    device_response = client.post(
        "/api/v1/devices",
        json={
            "name": "Office plug",
            "device_id": "connector-test-device",
            "ip_address": "192.168.1.31",
            "device_type": "switch",
            "protocol_version": "3.5",
            "encrypted_local_key": "connector-local-key",
        },
    )
    assert device_response.status_code == 201, device_response.text
    device_id = device_response.json()["id"]
    assigned = client.put(
        f"/api/v1/devices/{device_id}/connector",
        json={"connector_id": connector_id},
    )
    assert assigned.status_code == 200, assigned.text

    manual = client.post(
        f"/api/v1/devices/{device_id}/state",
        json={"desired_state": True},
    )
    assert manual.status_code == 200, manual.text
    assert manual.json()["status"] == "queued"

    with SessionLocal() as db:
        device = db.query(Device).filter(Device.id == device_id).one()
        command = db.query(DeviceCommand).filter(DeviceCommand.device_id == device_id).one()
        assert device.current_state is False
        assert command.status == "queued"
        assert decrypt_local_key(device.encrypted_local_key) == "connector-local-key"
        command_id = command.id

    heartbeat = client.post(
        "/api/v1/connectors/heartbeat",
        headers={"Authorization": f"Bearer {token}"},
        json={"version": "test"},
    )
    assert heartbeat.status_code == 200
    claim = client.post(
        "/api/v1/connectors/commands/claim",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert claim.status_code == 200, claim.text
    command_payload = claim.json()["command"]
    assert command_payload["id"] == command_id
    assert command_payload["device"]["local_key"] == "connector-local-key"

    result = client.post(
        f"/api/v1/connectors/commands/{command_id}/result",
        headers={"Authorization": f"Bearer {token}"},
        json={"success": True, "result": {"state": True}},
    )
    assert result.status_code == 200
    assert result.json()["status"] == "succeeded"

    with SessionLocal() as db:
        device = db.query(Device).filter(Device.id == device_id).one()
        event = db.query(AutomationEvent).filter(AutomationEvent.device_id == device_id).one()
        assert device.current_state is True
        assert event.success is True
        assert event.new_state == "true"


def test_meter_settings_are_tenant_scoped_and_connectors_collect_readings():
    owner = _tenant_admin_client("connector_meter_owner")
    connector_id, token = _enroll_connector(owner, "Meter LAN")
    device_response = owner.post(
        "/api/v1/devices",
        json={
            "name": "Metered plug",
            "device_id": "connector-meter-device",
            "ip_address": "192.168.1.41",
            "device_type": "switch",
            "protocol_version": "3.5",
            "encrypted_local_key": "meter-local-key",
        },
    )
    assert device_response.status_code == 201, device_response.text
    device_id = device_response.json()["id"]
    assigned = owner.put(
        f"/api/v1/devices/{device_id}/connector",
        json={"connector_id": connector_id},
    )
    assert assigned.status_code == 200, assigned.text

    settings_response = owner.put(
        f"/api/v1/devices/{device_id}/meter-settings",
        json={
            "power_dp_id": " cur_power ",
            "power_multiplier": 0.1,
            "energy_dp_id": " add_ele ",
            "energy_multiplier": 0.001,
            "energy_counter_type": "cumulative",
        },
    )
    assert settings_response.status_code == 200, settings_response.text
    assert settings_response.json()["power_dp_id"] == "cur_power"
    assert settings_response.json()["energy_dp_id"] == "add_ele"

    other_tenant = _tenant_admin_client("connector_meter_guest")
    assert other_tenant.put(
        f"/api/v1/devices/{device_id}/meter-settings",
        json={"power_dp_id": "1"},
    ).status_code == 404

    heartbeat = owner.post(
        "/api/v1/connectors/heartbeat",
        headers={"Authorization": f"Bearer {token}"},
        json={"version": "test"},
    )
    assert heartbeat.status_code == 200, heartbeat.text
    claim = owner.post(
        "/api/v1/connectors/commands/claim",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert claim.status_code == 200, claim.text
    command = claim.json()["command"]
    assert command["operation"] == "get_status"
    assert command["device"]["power_dp_id"] == "cur_power"
    assert command["device"]["power_multiplier"] == 0.1
    assert command["device"]["energy_dp_id"] == "add_ele"
    assert command["device"]["energy_multiplier"] == 0.001

    no_second_poll = owner.post(
        "/api/v1/connectors/commands/claim",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert no_second_poll.json()["command"] is None

    result = owner.post(
        f"/api/v1/connectors/commands/{command['id']}/result",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "success": True,
            "result": {"state": True, "power_watts": 84.5, "energy_total_kwh": 12.5},
        },
    )
    assert result.status_code == 200, result.text

    device = owner.get(f"/api/v1/devices/{device_id}")
    assert device.status_code == 200, device.text
    assert device.json()["meter_power_watts"] == 84.5
    assert device.json()["meter_energy_month_kwh"] == 0
    assert device.json()["meter_month_key"] == datetime.now(UTC).strftime("%Y-%m")
    assert device.json()["meter_power_sample_at"] is not None
    assert device.json()["meter_energy_sample_at"] is not None

    reset_settings = owner.put(
        f"/api/v1/devices/{device_id}/meter-settings",
        json={
            "power_dp_id": "new_power",
            "power_multiplier": 1,
            "energy_dp_id": "new_energy",
            "energy_multiplier": 0.001,
            "energy_counter_type": "monthly",
        },
    )
    assert reset_settings.status_code == 200, reset_settings.text
    assert reset_settings.json()["meter_power_watts"] is None
    assert reset_settings.json()["meter_power_sample_at"] is None
    assert reset_settings.json()["meter_energy_month_kwh"] is None
    assert reset_settings.json()["meter_energy_sample_at"] is None


def test_meter_discovery_uses_assigned_connector_and_is_tenant_scoped():
    owner = _tenant_admin_client("connector_meter_discovery_owner")
    connector_id, token = _enroll_connector(owner, "Meter discovery LAN")
    device_response = owner.post(
        "/api/v1/devices",
        json={
            "name": "Meter discovery plug",
            "device_id": "connector-meter-discovery-device",
            "ip_address": "192.168.1.42",
            "device_type": "switch",
            "protocol_version": "3.5",
            "encrypted_local_key": "meter-discovery-local-key",
        },
    )
    device_id = device_response.json()["id"]
    assigned = owner.put(
        f"/api/v1/devices/{device_id}/connector",
        json={"connector_id": connector_id},
    )
    assert assigned.status_code == 200, assigned.text
    owner.post(
        "/api/v1/connectors/heartbeat",
        headers={"Authorization": f"Bearer {token}"},
        json={"version": "0.1.4"},
    )

    discovery = owner.post(f"/api/v1/devices/{device_id}/meter-discovery")
    assert discovery.status_code == 202, discovery.text
    command_id = discovery.json()["command_id"]

    claim = owner.post(
        "/api/v1/connectors/commands/claim",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    command = claim.json()["command"]
    assert command["id"] == command_id
    assert command["operation"] == "inspect_meter"

    candidates = [
        {"id": "cur_power", "label": "Power reading", "sample": 845, "suggested_role": "power"},
        {"id": "add_ele", "label": "Energy reading", "sample": 12500, "suggested_role": "energy"},
    ]
    completed = owner.post(
        f"/api/v1/connectors/commands/{command_id}/result",
        headers={"Authorization": f"Bearer {token}"},
        json={"success": True, "result": {"candidates": candidates}},
    )
    assert completed.status_code == 200, completed.text
    command_status = owner.get(f"/api/v1/connectors/commands/{command_id}")
    assert command_status.status_code == 200, command_status.text
    assert command_status.json()["result"]["candidates"] == candidates

    other_tenant = _tenant_admin_client("connector_meter_discovery_guest")
    assert other_tenant.get(f"/api/v1/connectors/commands/{command_id}").status_code == 404
    assert other_tenant.post(f"/api/v1/devices/{device_id}/meter-discovery").status_code == 404


def test_meter_discovery_reads_directly_when_no_connector_is_assigned(monkeypatch):
    owner = _tenant_admin_client("meter_discovery_local_owner")
    device = owner.post(
        "/api/v1/devices",
        json={
            "name": "Local meter plug",
            "device_id": "local-meter-discovery-device",
            "ip_address": "192.168.1.43",
            "encrypted_local_key": "local-meter-discovery-key",
        },
    )
    assert device.status_code == 201, device.text

    class FakeTuyaService:
        @staticmethod
        def from_device(_device):
            return FakeTuyaService()

        async def get_meter_candidates(self):
            return [{"id": "cur_power", "label": "Power reading", "sample": 845, "suggested_role": "power"}]

    monkeypatch.setattr("app.api.devices.TuyaService", FakeTuyaService)
    response = owner.post(f"/api/v1/devices/{device.json()['id']}/meter-discovery")

    assert response.status_code == 200, response.text
    assert response.json()["candidates"] == [
        {"id": "cur_power", "label": "Power reading", "sample": 845, "suggested_role": "power"}
    ]


def test_connector_data_is_scoped_to_the_enrolling_tenant():
    owner = _tenant_admin_client("connector_tenant_owner")
    connector_id, token = _enroll_connector(owner, "Owner LAN")
    guest = _tenant_admin_client("connector_other_tenant")
    assert guest.get("/api/v1/connectors").json() == []
    revoked = guest.post(f"/api/v1/connectors/{connector_id}/revoke")
    assert revoked.status_code == 404
    invalid_claim = guest.post(
        "/api/v1/connectors/commands/claim",
        headers={"Authorization": "Bearer invalid"},
        json={},
    )
    assert invalid_claim.status_code == 401
    assert token


def test_revoked_connector_can_be_deleted_with_its_commands():
    client = _tenant_admin_client("connector_delete_owner")
    created = client.post(
        "/api/v1/connectors/enrollment-codes",
        json={"name": "Retired LAN"},
    )
    assert created.status_code == 201

    with SessionLocal() as db:
        connector = db.query(SiteConnector).filter(SiteConnector.name == "Retired LAN").one()
        connector_id = connector.id
        db.add(
            DeviceCommand(
                tenant_id=connector.tenant_id,
                connector_id=connector.id,
                operation="turn_on",
                expires_at=datetime.now(UTC) + timedelta(minutes=5),
            )
        )
        db.commit()

    active_delete = client.delete(f"/api/v1/connectors/{connector_id}")
    assert active_delete.status_code == 409

    revoked = client.post(f"/api/v1/connectors/{connector_id}/revoke")
    assert revoked.status_code == 200

    deleted = client.delete(f"/api/v1/connectors/{connector_id}")
    assert deleted.status_code == 204
    with SessionLocal() as db:
        assert db.query(SiteConnector).filter(SiteConnector.id == connector_id).first() is None
        assert db.query(DeviceCommand).filter(DeviceCommand.connector_id == connector_id).count() == 0
