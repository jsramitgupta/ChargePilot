import re
from datetime import UTC, datetime, timedelta
from io import BytesIO
from zipfile import ZipFile

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.connector import DeviceCommand, SiteConnector
from app.models.device import Device
from app.models.event import AutomationEvent
from app.services.local_key_service import decrypt_local_key


def _tenant_admin_client(username: str) -> TestClient:
    client = TestClient(app)
    response = client.post(
        "/register",
        data={
            "username": username,
            "password": "secret123",
            "account_type": "tenant",
            "tenant_name": f"{username} site",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    return client


def _enroll_connector(client: TestClient, name: str = "Office LAN") -> tuple[str, str]:
    created = client.post(
        "/connectors",
        data={"name": name},
        follow_redirects=False,
    )
    assert created.status_code == 303, created.text
    page = client.get("/connectors")
    assert page.status_code == 200, page.text
    assert page.headers["cache-control"] == "private, no-store"
    code_match = re.search(
        r'<output id="connector-enrollment-code"[^>]*>([^<]+)</output>',
        page.text,
    )
    assert code_match, "The one-time enrollment code should be visible."
    assert 'data-copy-target="connector-enrollment-code"' in page.text
    assert 'data-copy-status="Enrollment code copied."' in page.text
    code = code_match.group(1)
    assert code not in client.get("/connectors").text
    response = client.post(
        "/api/v1/connectors/enroll",
        headers={"Authorization": f"Bearer {code}"},
        json={"version": "test"},
    )
    assert response.status_code == 200, response.text
    return response.json()["connector_id"], response.json()["token"]


def test_connector_api_lists_status_for_authenticated_tenant():
    client = _tenant_admin_client("connector_list_owner")
    client.post("/connectors", data={"name": "Office LAN"}, follow_redirects=False)

    response = client.get("/api/v1/connectors")

    assert response.status_code == 200, response.text
    connectors = response.json()
    assert len(connectors) == 1
    assert connectors[0]["name"] == "Office LAN"
    assert connectors[0]["is_enrolled"] is False
    assert connectors[0]["is_online"] is False


def test_connector_download_contains_runtime_and_pinned_requirements():
    client = _tenant_admin_client("connector_package_owner")
    response = client.get("/connectors/download")

    assert response.status_code == 200
    with ZipFile(BytesIO(response.content)) as package:
        assert "connector/chargepilot_connector.py" in package.namelist()
        assert "requirements.txt" in package.namelist()
        assert "README.md" in package.namelist()
        assert "connector/Dockerfile" in package.namelist()
        assert "docker-compose.yml" in package.namelist()
        assert ".env.example" in package.namelist()
        assert "CHARGEPILOT_CONNECTOR_ENROLLMENT_CODE_FILE" in package.read("docker-compose.yml").decode()
        assert "network_mode: host" in package.read("docker-compose.yml").decode()
        assert "httpx==0.27.0" in package.read("requirements.txt").decode()
        readme = package.read("README.md").decode()
        assert "Docker deployment (Linux, amd64 or arm64)" in readme
        assert "docker compose up -d" in readme
        assert "permanent credential" in readme


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
    assigned = client.post(
        f"/devices/{device_id}/connector",
        data={"connector_id": connector_id},
        follow_redirects=False,
    )
    assert assigned.status_code == 303

    manual = client.post(f"/devices/{device_id}/turn-on", follow_redirects=False)
    assert manual.status_code == 303
    assert "queued" in manual.headers["location"]

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
    page = guest.get("/connectors")
    assert page.status_code == 200
    assert "Owner LAN" not in page.text
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
        "/connectors",
        data={"name": "Retired LAN"},
        follow_redirects=False,
    )
    assert created.status_code == 303

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

    active_delete = client.post(f"/connectors/{connector_id}/delete", follow_redirects=False)
    assert active_delete.status_code == 303
    assert "Revoke+the+connector+before+deleting+it" in active_delete.headers["location"]

    revoked = client.post(f"/connectors/{connector_id}/revoke", follow_redirects=False)
    assert revoked.status_code == 303
    page = client.get("/connectors")
    assert f'/connectors/{connector_id}/delete' in page.text

    deleted = client.post(f"/connectors/{connector_id}/delete", follow_redirects=False)
    assert deleted.status_code == 303
    assert "Connector+deleted" in deleted.headers["location"]
    with SessionLocal() as db:
        assert db.query(SiteConnector).filter(SiteConnector.id == connector_id).first() is None
        assert db.query(DeviceCommand).filter(DeviceCommand.connector_id == connector_id).count() == 0
