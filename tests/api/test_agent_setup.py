from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import settings
from app.core.database import SessionLocal
from app.main import app
from app.models.system_setting import SystemSetting
from app.models.tenant import Tenant
from app.models.user import User
from app.services.endpoint_service import validate_endpoint_auth
from conftest import api_login, register_standard_user, register_tenant_admin


def test_docker_image_does_not_bundle_agent_sources():
    dockerfile = Path(__file__).resolve().parents[2] / "docker" / "Dockerfile"
    assert "COPY agent ./agent" not in dockerfile.read_text(encoding="utf-8")


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

    download = client.get("/agent/download", follow_redirects=False)
    assert download.status_code == 410
    assert "iex" in payload["install_command"]
    assert "$(irm" in payload["install_command"]


def test_agent_setup_uses_configured_public_api_origin(monkeypatch):
    monkeypatch.setattr(settings, "api_url", "https://api.example.test")
    client = TestClient(app)
    register_tenant_admin(client, "agent_public_origin", "tenant-agent-password")

    setup = client.get("/api/v1/agent/setup")

    assert setup.status_code == 200
    install_command = setup.json()["install_command"]
    assert "$(irm 'https://api.example.test/agent/install.ps1')" in install_command
    assert "-ServerUrl 'https://api.example.test'" in install_command
    assert "-EndpointToken " not in install_command


def test_latest_agent_release_assets_are_proxied_by_the_public_api(monkeypatch):
    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {
                "tag_name": "agents-v0.1.6",
                "assets": [
                    {
                        "name": "ChargePilotAgent-0.1.6.dmg",
                        "url": "https://api.github.com/repos/jsramitgupta/ChargePilot/releases/assets/1",
                    },
                    {
                        "name": "chargepilot-macos-agent-source.zip",
                        "url": "https://api.github.com/repos/jsramitgupta/ChargePilot/releases/assets/2",
                    },
                    {
                        "name": "unexpected.apk",
                        "url": "https://api.github.com/repos/jsramitgupta/ChargePilot/releases/assets/3",
                    },
                ],
            }

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def get(self, url, headers):
            assert url == (
                "https://api.github.com/repos/jsramitgupta/ChargePilot/releases/latest"
            )
            assert headers["User-Agent"] == "ChargePilotAgentSetup"
            assert headers["Authorization"] == "Bearer read-only-token"
            return FakeResponse()

    monkeypatch.setattr(
        settings,
        "agent_release_github_token",
        SecretStr("read-only-token"),
    )
    monkeypatch.setattr("app.main.httpx.AsyncClient", lambda timeout: FakeClient())
    client = TestClient(app)
    response = client.get("/api/v1/agent/releases/latest")

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "public, max-age=300"
    assert response.json() == {
        "tag": "agents-v0.1.6",
        "assets": [{
            "name": "ChargePilotAgent-0.1.6.dmg",
            "url": (
                "https://app.example.test/agent/releases/latest/download/"
                "ChargePilotAgent-0.1.6.dmg"
            ),
        }],
    }


def test_latest_agent_release_api_reports_github_errors(monkeypatch):
    class FakeResponse:
        status_code = 403

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def get(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr("app.main.httpx.AsyncClient", lambda timeout: FakeClient())
    response = TestClient(app).get("/api/v1/agent/releases/latest")

    assert response.status_code == 502
    assert "agent package service" in response.json()["detail"]


def test_agent_release_asset_is_streamed_through_the_api(monkeypatch):
    class FakeResponse:
        status_code = 200

        async def aiter_bytes(self):
            yield b"release-binary"

        async def aclose(self):
            return None

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        @staticmethod
        def build_request(method, url, headers):
            return method, url, headers

        async def send(self, request, stream):
            assert stream is True
            method, url, headers = request
            assert method == "GET"
            assert url == (
                "https://api.github.com/repos/jsramitgupta/ChargePilot/releases/assets/7"
            )
            assert headers["Accept"] == "application/octet-stream"
            assert headers["Authorization"] == "Bearer read-only-token"
            return FakeResponse()

        async def aclose(self):
            return None

    async def fake_release():
        return {
            "tag_name": "agents-v0.1.6",
            "assets": [{
                "name": "ChargePilotAgent-0.1.6.dmg",
                "url": "https://api.github.com/repos/jsramitgupta/ChargePilot/releases/assets/7",
            }],
        }

    monkeypatch.setattr(settings, "agent_release_github_token", SecretStr("read-only-token"))
    monkeypatch.setattr("app.main._get_latest_agent_release", fake_release)
    monkeypatch.setattr("app.main.httpx.AsyncClient", FakeClient)

    response = TestClient(app).get(
        "/agent/releases/latest/download/ChargePilotAgent-0.1.6.dmg"
    )

    assert response.status_code == 200
    assert response.content == b"release-binary"
    assert response.headers["content-disposition"] == (
        'attachment; filename="ChargePilotAgent-0.1.6.dmg"'
    )
    assert response.headers["cache-control"] == "public, max-age=300"


def test_windows_installer_passes_configured_server_to_executable():
    installer = (
        Path(__file__).resolve().parents[2] / "agent" / "windows" / "install.ps1"
    ).read_text(encoding="utf-8")

    assert '[string]$ServerUrl = "https://api-chargepilot.endusercompute.in"' in installer
    assert '$($ServerUrl.TrimEnd' in installer
    assert '--server-url "{1}"' in installer


def test_public_agent_installer_is_served_from_the_deployed_source_file():
    response = TestClient(app).get("/agent/install.ps1")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=300"
    assert "$($ServerUrl.TrimEnd('/'))/agent/ChargePilotAgent.exe" in response.text


def test_agent_source_archives_are_no_longer_public():
    client = TestClient(app)
    assert client.get("/api/v1/agent/setup").status_code == 401
    for route in (
        "/agent/download",
        "/agent/BatteryAgent.ps1",
        "/agent/macos/download",
        "/agent/android/download",
        "/agent/ios/download",
    ):
        assert client.get(route).status_code == 410, route


def test_standard_user_can_download_but_cannot_rotate_tenant_token():
    client = TestClient(app)
    register_standard_user(client, "agent_standard_user", "standard-agent-password")

    assert client.get("/api/v1/agent/setup").status_code == 200
    assert client.get("/agent/download").status_code == 410
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
