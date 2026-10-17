import os

os.environ["CHARGEPILOT_DATABASE_URL"] = "sqlite://"
os.environ["CHARGEPILOT_ENVIRONMENT"] = "test"

import pytest

from app.core.database import Base, SessionLocal, engine, ensure_default_admin_user, ensure_default_system_settings
from app.models.system_setting import SystemSetting
from app.models.device import Device, DeviceChannel
from app.models.endpoint import Endpoint
from app.models.event import AutomationEvent
from app.models.mapping import Mapping

TEST_GLOBAL_AGENT_TOKEN = "test-endpoint-token"


def set_test_global_agent_token() -> None:
    with SessionLocal() as db:
        setting = db.query(SystemSetting).filter(SystemSetting.key == "global_agent_token").one()
        setting.value = TEST_GLOBAL_AGENT_TOKEN
        db.commit()


def api_login(client, username: str, password: str):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    return response


def register_tenant_admin(client, username: str, password: str, tenant_name: str | None = None):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "account_type": "tenant",
            "username": username,
            "password": password,
            "tenant_name": tenant_name or f"{username} tenant",
        },
    )
    assert response.status_code == 201, response.text
    return response


def register_standard_user(client, username: str, password: str):
    from fastapi.testclient import TestClient

    from app.main import app

    owner = TestClient(app)
    owner_name = f"{username[:55]}-invite-owner"
    register_tenant_admin(owner, owner_name, "invite-owner-password", f"{username} tenant")
    invite = owner.post("/api/v1/admin/invites", json={})
    assert invite.status_code == 201, invite.text
    response = client.post(
        "/api/v1/auth/register",
        json={
            "account_type": "standard",
            "username": username,
            "password": password,
            "invite_code": invite.json()["code"],
        },
    )
    assert response.status_code == 201, response.text
    return response


@pytest.fixture(autouse=True)
def reset_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    ensure_default_admin_user()
    ensure_default_system_settings()
    set_test_global_agent_token()
    yield
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    ensure_default_admin_user()
    ensure_default_system_settings()
    set_test_global_agent_token()

    with SessionLocal() as db:
        for model in (AutomationEvent, Mapping, DeviceChannel, Endpoint, Device):
            db.query(model).delete()
        db.commit()
