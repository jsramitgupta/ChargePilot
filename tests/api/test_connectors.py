from datetime import UTC, datetime, timedelta
from io import BytesIO
from zipfile import ZipFile

from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import SessionLocal
from app.main import app
from app.models.connector import DeviceCommand, SiteConnector
from app.models.device import Device
from app.models.event import AutomationEvent
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

    revoked = client.post(f"/api/v1/connectors/{payload['id']}/revoke")
    assert revoked.status_code == 200, revoked.text
    assert revoked.json() == {"status": "revoked"}

    deleted = client.delete(f"/api/v1/connectors/{payload['id']}")
    assert deleted.status_code == 204
    assert client.get("/api/v1/connectors").json() == []


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


def test_agent_setup_api_supplies_tenant_scoped_install_command(monkeypatch):
    monkeypatch.setattr(settings, "api_url", "https://api.example.test")
    client = _tenant_admin_client("react_agent_setup")

    response = client.get("/api/v1/agent/setup")

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "private, no-store"
    payload = response.json()
    assert payload["token"]
    assert payload["token_scope"] == "tenant: react_agent_setup site"
    assert payload["install_command"].startswith('iex "& { $(irm ')
    assert "-ServerUrl 'https://api.example.test'" in payload["install_command"]
    assert "-EndpointToken " in payload["install_command"]
    assert payload["can_rotate_tenant_token"] is True


def test_connector_download_contains_runtime_and_pinned_requirements():
    client = TestClient(app)
    response = client.get("/connectors/download")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=300"
    with ZipFile(BytesIO(response.content)) as package:
        assert "connector/chargepilot_connector.py" in package.namelist()
        assert "requirements.txt" in package.namelist()
        assert "README.md" in package.namelist()
        assert "install.sh" in package.namelist()
        assert "connector/Dockerfile" in package.namelist()
        assert "docker-compose.yml" in package.namelist()
        assert ".env.example" in package.namelist()
        compose = package.read("docker-compose.yml").decode()
        assert "CHARGEPILOT_CONNECTOR_ENROLLMENT_CODE:" in compose
        assert "connector-data:/data" in compose
        assert "ENROLLMENT_CODE_FILE" not in compose
        assert "enrollment-code.txt" not in compose
        assert "network_mode: host" in compose
        assert "endusercompute/chargepilot-connector:sha-1207f34e13246072fe9f4e384ab14e1c95a6760f" in compose
        assert "httpx==0.27.0" in package.read("requirements.txt").decode()
        readme = package.read("README.md").decode()
        assert "Docker Compose (Linux)" in readme
        assert "docker compose up -d" in readme
        assert "permanent credential" in readme
        assert "no host directory" in readme


def test_connector_installer_is_public_and_uses_configured_api_url(monkeypatch):
    monkeypatch.setattr(settings, "api_url", "https://api.example.test")

    response = TestClient(app).get("/connectors/install.sh")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert '"$SERVER_URL/connectors/download"' in response.text
    assert "https://api.example.test" in response.text
    assert "__CHARGEPILOT_SERVER_URL__" not in response.text
    assert "getpass.getpass" in response.text


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
