import io
import zipfile
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import SessionLocal
from app.main import app
from app.models.system_setting import SystemSetting
from app.models.tenant import Tenant
from app.models.user import User
from app.services.endpoint_service import validate_endpoint_auth
from conftest import api_login, register_standard_user, register_tenant_admin


def test_docker_image_includes_scripts_required_by_agent_download():
    dockerfile = Path(__file__).resolve().parents[2] / "docker" / "Dockerfile"
    assert "COPY agent ./agent" in dockerfile.read_text(encoding="utf-8")


def test_agent_setup_api_returns_credential_free_install_command_and_enrollment_agent(monkeypatch):
    client = TestClient(app)
    username = f"agent_setup_{uuid4().hex[:8]}"
    register_tenant_admin(client, username, "tenant-agent-password")
    with SessionLocal() as db:
        tenant = db.query(Tenant).filter(Tenant.name == f"{username} tenant").one()
        tenant.agent_token = ""
        db.commit()

    setup = client.get("/api/v1/agent/setup")
    assert setup.status_code == 200, setup.text
    assert setup.headers["cache-control"] == "private, no-store"
    payload = setup.json()
    assert set(payload) == {"install_command", "is_super_admin"}
    assert "-ServerUrl " in payload["install_command"]
    assert "-EndpointToken " not in payload["install_command"]
    with SessionLocal() as db:
        tenant = db.query(Tenant).filter(Tenant.name == f"{username} tenant").one()
        assert tenant.agent_token == ""
    monkeypatch.setattr(settings, "frontend_url", "")
    assert client.get("/agent", follow_redirects=False).headers["location"] == "/agent"

    download = client.get("/agent/download")
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("application/zip")
    assert download.headers["cache-control"] == "public, max-age=300"
    with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
        assert set(archive.namelist()) == {"BatteryAgent.ps1", "CreateAgentScheduledTask.ps1"}
        battery_agent = archive.read("BatteryAgent.ps1")
        installer = archive.read("CreateAgentScheduledTask.ps1")
        assert b"installation_id = $InstallationId" in battery_agent
        assert b"protectedEndpointToken" in installer
        assert b"-EndpointToken " not in installer
    assert "iex" in payload["install_command"]
    assert "$(irm" in payload["install_command"]


def test_agent_setup_uses_configured_public_api_origin(monkeypatch):
    monkeypatch.setattr(settings, "api_url", "https://api.example.test")
    client = TestClient(app)
    register_tenant_admin(client, "agent_public_origin", "tenant-agent-password")

    setup = client.get("/api/v1/agent/setup")

    assert setup.status_code == 200
    assert "-ServerUrl 'https://api.example.test'" in setup.json()["install_command"]
    assert "-EndpointToken " not in setup.json()["install_command"]


def test_agent_setup_requires_authentication_but_agent_sources_are_public():
    client = TestClient(app)
    assert client.get("/api/v1/agent/setup").status_code == 401
    assert client.get("/agent/download", follow_redirects=False).status_code == 200
    installer = client.get("/agent/install.ps1")
    battery_script = client.get("/agent/BatteryAgent.ps1")
    assert installer.status_code == 200
    assert battery_script.status_code == 200
    assert "public" in installer.headers["cache-control"]
    assert "Invoke-WebRequest" in installer.text
    assert "Invoke-WebRequest" in battery_script.text or "Get-BatteryStatus" in battery_script.text


def test_standard_user_can_download_but_cannot_rotate_tenant_token():
    client = TestClient(app)
    register_standard_user(client, "agent_standard_user", "standard-agent-password")

    assert client.get("/api/v1/agent/setup").status_code == 200
    assert client.get("/agent/download").status_code == 200
    assert client.put("/api/v1/admin/tenant-agent-token").status_code == 403
    assert client.put(
        "/api/v1/admin/global-agent-token",
        json={"action": "save", "token": f"not-admin-{uuid4().hex}"},
    ).status_code == 403


def test_tenant_and_super_admin_token_rotation_use_json_apis():
    tenant_client = TestClient(app)
    register_tenant_admin(tenant_client, "agent_rotate_owner", "tenant-agent-password")
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == "agent_rotate_owner").one()
        tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).one()
        original_tenant_token = tenant.agent_token

    rotated_tenant = tenant_client.put("/api/v1/admin/tenant-agent-token")
    assert rotated_tenant.status_code == 200, rotated_tenant.text
    assert rotated_tenant.headers["cache-control"] == "private, no-store"
    assert rotated_tenant.json()["agent_token"] != original_tenant_token

    admin = TestClient(app)
    api_login(admin, settings.admin_username, settings.admin_password)
    with SessionLocal() as db:
        setting = db.query(SystemSetting).filter(SystemSetting.key == "global_agent_token").one()
        original_global_token = setting.value
        setting.value = "test-global-token-for-agent"
        db.commit()

    updated_token = f"global-agent-{uuid4().hex}"
    updated = admin.put(
        "/api/v1/admin/global-agent-token",
        json={"action": "save", "token": updated_token},
    )
    assert updated.status_code == 200, updated.text
    assert updated.headers["cache-control"] == "private, no-store"
    assert updated.json()["global_token"] == updated_token
    with SessionLocal() as db:
        setting = db.query(SystemSetting).filter(SystemSetting.key == "global_agent_token").one()
        assert setting.value == updated_token
        assert not validate_endpoint_auth(f"Bearer {original_global_token}", db)
        assert validate_endpoint_auth(f"Bearer {updated_token}", db)
        setting.value = original_global_token
        db.commit()
