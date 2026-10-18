import os
from urllib.parse import parse_qs, urlsplit

os.environ["CHARGEPILOT_DATABASE_URL"] = "sqlite://"
os.environ["CHARGEPILOT_ENVIRONMENT"] = "test"

import pytest
from pydantic import SecretStr

from app.api import admin as admin_api
from app.api import auth as auth_api
from app.core.database import Base, SessionLocal, engine, ensure_default_admin_user, ensure_default_system_settings
from app.core.config import settings
from app.models.system_setting import SystemSetting
from app.models.device import Device, DeviceChannel
from app.models.endpoint import Endpoint
from app.models.event import AutomationEvent
from app.models.mapping import Mapping

TEST_GLOBAL_AGENT_TOKEN = "test-endpoint-token"
TEST_EMAIL_VERIFICATION_TOKENS: dict[str, str] = {}
TEST_ACCOUNT_INVITATION_TOKENS: dict[str, str] = {}


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


def verify_registered_email(client, response, email: str):
    assert response.status_code == 202, response.text
    token = TEST_EMAIL_VERIFICATION_TOKENS[email]
    verified = client.post("/api/v1/auth/verify-email", json={"token": token})
    assert verified.status_code == 200, verified.text
    return verified


def register_tenant_admin(client, username: str, password: str, tenant_name: str | None = None):
    email = f"{username}@example.test"
    response = client.post(
        "/api/v1/auth/register",
        json={
            "account_type": "tenant",
            "username": username,
            "password": password,
            "email": email,
            "turnstile_token": "test-turnstile-token",
            "tenant_name": tenant_name or f"{username} tenant",
        },
    )
    return verify_registered_email(client, response, email)


def register_standard_user(client, username: str, password: str):
    from fastapi.testclient import TestClient

    from app.main import app

    owner = TestClient(app)
    owner_name = f"{username[:55]}-invite-owner"
    register_tenant_admin(owner, owner_name, "invite-owner-password", f"{username} tenant")
    invite = owner.post("/api/v1/admin/invites", json={})
    assert invite.status_code == 201, invite.text
    email = f"{username}@example.test"
    response = client.post(
        "/api/v1/auth/register",
        json={
            "account_type": "standard",
            "username": username,
            "password": password,
            "email": email,
            "turnstile_token": "test-turnstile-token",
            "invite_code": invite.json()["code"],
        },
    )
    return verify_registered_email(client, response, email)


@pytest.fixture(autouse=True)
def reset_database(monkeypatch):
    async def accept_test_challenge(_token, _request=None):
        return None

    def capture_verification_email(*, recipient: str, username: str, verification_url: str):
        token = parse_qs(urlsplit(verification_url).query)["token"][0]
        TEST_EMAIL_VERIFICATION_TOKENS[recipient] = token

    def capture_account_invitation_email(
        *,
        recipient: str,
        username: str,
        role: str,
        tenant_name: str,
        setup_code: str,
        invitation_url: str,
        expires_at: str,
    ):
        code = parse_qs(urlsplit(invitation_url).query)["code"][0]
        assert code == setup_code
        TEST_ACCOUNT_INVITATION_TOKENS[recipient] = code

    monkeypatch.setattr(auth_api, "verify_registration_challenge", accept_test_challenge)
    monkeypatch.setattr(auth_api, "send_verification_email", capture_verification_email)
    monkeypatch.setattr(admin_api, "send_account_invitation_email", capture_account_invitation_email)
    monkeypatch.setattr(settings, "frontend_url", "https://app.example.test")
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.test")
    monkeypatch.setattr(settings, "smtp_username", "test-user")
    monkeypatch.setattr(settings, "smtp_password", SecretStr("test-password"))
    monkeypatch.setattr(settings, "smtp_from_email", "no-reply@example.test")
    TEST_EMAIL_VERIFICATION_TOKENS.clear()
    TEST_ACCOUNT_INVITATION_TOKENS.clear()
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
