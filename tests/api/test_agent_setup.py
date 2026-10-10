import html
import io
import os
import zipfile
from pathlib import Path
from uuid import uuid4

os.environ["CHARGEPILOT_DATABASE_URL"] = "sqlite://"

from fastapi.testclient import TestClient

from app.core.database import SessionLocal, create_db_and_tables
from app.main import app
from app.models.system_setting import SystemSetting
from app.models.tenant import Tenant
from app.models.user import User
from app.services.endpoint_service import validate_endpoint_auth


create_db_and_tables()


def test_docker_image_includes_scripts_required_by_agent_download():
    dockerfile = Path(__file__).resolve().parents[2] / "docker" / "Dockerfile"

    assert "COPY agent ./agent" in dockerfile.read_text(encoding="utf-8")


def _register_tenant_admin(client: TestClient, username: str) -> None:
    response = client.post(
        "/register",
        data={
            "username": username,
            "password": "secret123",
            "account_type": "tenant",
            "tenant_name": f"{username} tenant",
        },
        follow_redirects=False,
    )
    assert response.status_code in {200, 302, 303}, response.text


def test_authenticated_agent_setup_page_shows_tenant_token_command_and_download():
    client = TestClient(app)
    username = f"agent_setup_{uuid4().hex[:8]}"
    _register_tenant_admin(client, username)
    with SessionLocal() as db:
        tenant = db.query(Tenant).filter(Tenant.name == f"{username} tenant").one()
        tenant.agent_token = ""
        db.commit()

    page = client.get("/agent")
    assert page.status_code == 200, page.text
    assert "Download agent scripts" in page.text
    assert "CreateAgentScheduledTask.ps1" in page.text
    assert "BatteryAgent.ps1" not in page.text
    rendered_command = html.unescape(page.text)
    assert "-ServerUrl 'http://testserver'" in rendered_command

    with SessionLocal() as db:
        tenant = db.query(Tenant).filter(Tenant.name == f"{username} tenant").one()
        token = tenant.agent_token
        assert len(token) == 32
        assert token.isalpha()
    assert f"-EndpointToken '{token}'" in rendered_command
    assert token in page.text
    assert 'id="open-agent-guide"' in page.text
    assert ">Download Agent</button>" in page.text
    assert 'id="agent-guide-modal"' in page.text

    guide = client.get("/agent/guide")
    assert guide.status_code == 200, guide.text
    assert "Extract and open PowerShell" in guide.text
    assert "Run the install command" in guide.text
    assert "Confirm the laptop is connected" in guide.text
    assert f"-EndpointToken &#39;{token}&#39;" in guide.text

    download = client.get("/agent/download")
    assert download.status_code == 200, download.text
    assert download.headers["content-type"].startswith("application/zip")
    assert "no-store" in download.headers["cache-control"]
    with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
        assert set(archive.namelist()) == {"BatteryAgent.ps1", "CreateAgentScheduledTask.ps1"}
        assert token.encode() not in archive.read("CreateAgentScheduledTask.ps1")


def test_agent_download_requires_authenticated_tenant():
    client = TestClient(app)

    response = client.get("/agent/download", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    assert client.get("/agent/guide").status_code == 401


def test_authenticated_non_admin_can_download_but_cannot_regenerate_token():
    client = TestClient(app)
    username = f"agent_member_{uuid4().hex[:8]}"
    response = client.post(
        "/register",
        data={"username": username, "password": "secret123"},
        follow_redirects=False,
    )
    assert response.status_code in {200, 302, 303}, response.text

    page = client.get("/agent")
    assert page.status_code == 200, page.text
    assert "Download agent scripts" in page.text
    assert "Regenerate token" not in page.text
    assert client.get("/agent/download").status_code == 200

    rotate = client.post("/tenant/rotate-agent-token", follow_redirects=False)
    assert rotate.status_code == 303
    assert "Only+tenant+admins" in rotate.headers["location"]


def test_agent_setup_regenerates_token_without_putting_it_in_redirect_url():
    client = TestClient(app)
    username = f"agent_rotate_{uuid4().hex[:8]}"
    _register_tenant_admin(client, username)
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == username).one()
        tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).one()
        original_token = tenant.agent_token

    response = client.post("/tenant/rotate-agent-token", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/agent?message=Agent+token+regenerated+successfully"
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == username).one()
        tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).one()
        assert tenant.agent_token != original_token


def test_super_admin_can_change_legacy_global_token_and_use_it_for_agent_auth():
    client = TestClient(app)
    with SessionLocal() as db:
        setting = db.query(SystemSetting).filter(SystemSetting.key == "global_agent_token").one()
        original_token = setting.value
        setting.value = "test-endpoint-token"
        db.commit()

    login = client.post(
        "/login",
        data={"username": "admin", "password": "change-me"},
        follow_redirects=False,
    )
    assert login.status_code in {200, 302, 303}, login.text

    page = client.get("/agent")
    assert page.status_code == 200, page.text
    assert "Super Admin · System-wide" in page.text
    assert "test-endpoint-token" in page.text
    assert "/agent/download" in page.text

    updated_token = f"global-agent-{uuid4().hex}"
    update = client.post(
        "/agent/global-token",
        data={"action": "save", "token": updated_token},
        follow_redirects=False,
    )
    assert update.status_code == 303
    assert update.headers["location"] == "/agent?message=System-wide+agent+token+updated+successfully"

    with SessionLocal() as db:
        setting = db.query(SystemSetting).filter(SystemSetting.key == "global_agent_token").one()
        assert setting.value == updated_token
        assert not validate_endpoint_auth("Bearer test-endpoint-token", db)
        assert validate_endpoint_auth(f"Bearer {updated_token}", db)

    updated_page = client.get("/agent")
    assert updated_token in updated_page.text
    assert f"-EndpointToken &#39;{updated_token}&#39;" in updated_page.text
    guide = client.get("/agent/guide")
    assert guide.status_code == 200
    assert "Super Admin · Global token" in guide.text
    assert f"-EndpointToken &#39;{updated_token}&#39;" in guide.text
    assert "Regenerate" in guide.text
    download = client.get("/agent/download")
    assert download.status_code == 200
    with SessionLocal() as db:
        setting = db.query(SystemSetting).filter(SystemSetting.key == "global_agent_token").one()
        setting.value = original_token
        db.commit()


def test_global_token_change_is_restricted_to_super_admin():
    client = TestClient(app)
    username = f"agent_member_{uuid4().hex[:8]}"
    response = client.post(
        "/register",
        data={"username": username, "password": "secret123"},
        follow_redirects=False,
    )
    assert response.status_code in {200, 302, 303}, response.text

    update = client.post(
        "/agent/global-token",
        data={"action": "save", "token": f"not-admin-{uuid4().hex}"},
        follow_redirects=False,
    )
    assert update.status_code == 303
    assert "Only+the+Super+Admin" in update.headers["location"]
