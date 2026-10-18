import hashlib
import smtplib
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api import auth as auth_api
from app.api.auth import verify_registration_challenge
from app.core.config import settings
from app.core.database import SessionLocal
from app.main import app
from app.models.email_verification import EmailVerification
from app.models.tenant import Tenant
from app.models.tenant_invite import TenantInvite
from app.models.user import User
from conftest import TEST_EMAIL_VERIFICATION_TOKENS, verify_registered_email


def test_legacy_login_and_register_paths_redirect_to_react():
    client = TestClient(app)

    for path in ("/login", "/register"):
        response = client.get(path, follow_redirects=False)

        assert response.status_code == 307
        assert response.headers["location"].endswith(path)
        assert "<form" not in response.text

    assert client.post("/login", data={"username": "x", "password": "x"}).status_code == 405


def test_tenant_signup_creates_tenant_admin_and_establishes_session():
    client = TestClient(app)
    email = "new-tenant-owner@example.test"
    response = client.post(
        "/api/v1/auth/register",
        json={
            "account_type": "tenant",
            "username": "new-tenant-owner",
            "password": "new-tenant-password",
            "email": email,
            "turnstile_token": "test-turnstile-token",
            "tenant_name": "North Site",
        },
    )

    assert response.status_code == 202
    assert "message" in response.json()
    assert client.get("/api/v1/auth/me").status_code == 401
    verified = verify_registered_email(client, response, email)
    user = verified.json()["user"]
    assert user["role"] == "tenant_admin"
    assert user["tenant_name"] == "North Site"
    assert response.headers["Cache-Control"] == "no-store"
    assert verified.headers["Cache-Control"] == "private, no-store"
    assert client.get("/api/v1/auth/me").json()["id"] == user["id"]


def test_unverified_account_cannot_login_and_verification_token_is_single_use():
    client = TestClient(app)
    email = "pending-owner@example.test"
    registration = client.post(
        "/api/v1/auth/register",
        json={
            "account_type": "tenant",
            "username": "pending-owner",
            "password": "pending-owner-password",
            "email": email,
            "turnstile_token": "test-turnstile-token",
            "tenant_name": "Pending Site",
        },
    )
    assert registration.status_code == 202
    token = TEST_EMAIL_VERIFICATION_TOKENS[email]

    login = client.post(
        "/api/v1/auth/login",
        json={"username": "pending-owner", "password": "pending-owner-password"},
    )
    assert login.status_code == 403
    assert client.get("/api/v1/auth/me").status_code == 401

    verified = client.post("/api/v1/auth/verify-email", json={"token": token})
    assert verified.status_code == 200
    replay = client.post("/api/v1/auth/verify-email", json={"token": token})
    assert replay.status_code == 422
    assert client.post(
        "/api/v1/auth/login",
        json={"username": "pending-owner", "password": "pending-owner-password"},
    ).status_code == 200


def test_expired_email_verification_token_is_rejected():
    client = TestClient(app)
    email = "expired-verification@example.test"
    registration = client.post(
        "/api/v1/auth/register",
        json={
            "account_type": "tenant",
            "username": "expired-verification",
            "password": "expired-verification-password",
            "email": email,
            "turnstile_token": "test-turnstile-token",
            "tenant_name": "Expired Verification Site",
        },
    )
    assert registration.status_code == 202
    token = TEST_EMAIL_VERIFICATION_TOKENS[email]
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with SessionLocal() as db:
        verification = db.query(EmailVerification).filter_by(token_hash=token_hash).one()
        verification.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()

    assert client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 422
    assert client.post(
        "/api/v1/auth/login",
        json={"username": "expired-verification", "password": "expired-verification-password"},
    ).status_code == 403


def test_resend_verification_invalidates_previous_link():
    client = TestClient(app)
    email = "resend-verification@example.test"
    registration = client.post(
        "/api/v1/auth/register",
        json={
            "account_type": "tenant",
            "username": "resend-verification",
            "password": "resend-verification-password",
            "email": email,
            "turnstile_token": "test-turnstile-token",
            "tenant_name": "Resend Verification Site",
        },
    )
    assert registration.status_code == 202
    previous_token = TEST_EMAIL_VERIFICATION_TOKENS[email]

    resend = client.post(
        "/api/v1/auth/resend-verification",
        json={"email": email, "turnstile_token": "test-turnstile-token"},
    )
    assert resend.status_code == 202
    current_token = TEST_EMAIL_VERIFICATION_TOKENS[email]
    assert current_token != previous_token
    assert client.post(
        "/api/v1/auth/verify-email",
        json={"token": previous_token},
    ).status_code == 422
    assert client.post(
        "/api/v1/auth/verify-email",
        json={"token": current_token},
    ).status_code == 200


@pytest.mark.parametrize("missing_setting", ["smtp_host", "frontend_url"])
def test_registration_fails_closed_without_email_delivery_configuration(monkeypatch, missing_setting):
    monkeypatch.setattr(settings, missing_setting, "")
    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/register",
        json={
            "account_type": "tenant",
            "username": f"email-not-configured-{missing_setting}",
            "password": "email-not-configured-password",
            "email": f"email-not-configured-{missing_setting}@example.test",
            "turnstile_token": "test-turnstile-token",
            "tenant_name": "Email Not Configured",
        },
    )
    assert response.status_code == 503
    with SessionLocal() as db:
        assert db.query(User).filter_by(username=f"email-not-configured-{missing_setting}").first() is None


def test_smtp_delivery_failure_returns_unavailable_and_keeps_account_pending(monkeypatch):
    def fail_delivery(**_kwargs):
        raise smtplib.SMTPAuthenticationError(535, b"Authentication failed")

    monkeypatch.setattr(auth_api, "send_verification_email", fail_delivery)
    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/register",
        json={
            "account_type": "tenant",
            "username": "smtp-failure-owner",
            "password": "smtp-failure-owner-password",
            "email": "smtp-failure-owner@example.test",
            "turnstile_token": "test-turnstile-token",
            "tenant_name": "SMTP Failure Site",
        },
    )

    assert response.status_code == 503
    assert "could not be sent" in response.json()["detail"]
    assert client.post(
        "/api/v1/auth/login",
        json={"username": "smtp-failure-owner", "password": "smtp-failure-owner-password"},
    ).status_code == 403


def test_production_registration_fails_closed_without_turnstile_configuration(monkeypatch):
    monkeypatch.setattr(auth_api, "verify_registration_challenge", verify_registration_challenge)
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "turnstile_site_key", "")
    monkeypatch.setattr(settings, "turnstile_secret_key", SecretStr(""))

    response = TestClient(app).post(
        "/api/v1/auth/register",
        json={
            "account_type": "tenant",
            "username": "unverified-tenant",
            "password": "new-tenant-password",
            "email": "unverified-tenant@example.test",
            "turnstile_token": "provider-token",
            "tenant_name": "Unverified Site",
        },
    )

    assert response.status_code == 503
    assert "temporarily unavailable" in response.json()["detail"]


def test_registration_requires_a_turnstile_token():
    response = TestClient(app).post(
        "/api/v1/auth/register",
        json={
            "account_type": "tenant",
            "username": "missing-challenge-tenant",
            "password": "new-tenant-password",
            "email": "missing-challenge@example.test",
            "tenant_name": "Missing Challenge",
        },
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("verification_result", "expected_status"),
    [
        ({"success": False}, 400),
        ({"success": True, "hostname": "other.example.com", "action": "registration"}, 400),
        ({"success": True, "hostname": "app.example.com", "action": "login"}, 400),
        ({"success": True, "hostname": "app.example.com", "action": "registration"}, 202),
    ],
)
def test_production_registration_requires_valid_turnstile_result(
    monkeypatch,
    verification_result,
    expected_status,
):
    monkeypatch.setattr(auth_api, "verify_registration_challenge", verify_registration_challenge)
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "frontend_url", "https://app.example.com")
    monkeypatch.setattr(settings, "turnstile_site_key", "public-site-key")
    monkeypatch.setattr(settings, "turnstile_secret_key", SecretStr("private-secret-key"))

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return verification_result

    class FakeAsyncClient:
        def __init__(self, timeout):
            assert timeout == 5.0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, data):
            assert url == auth_api.TURNSTILE_SITEVERIFY_URL
            assert data == {"secret": "private-secret-key", "response": "provider-token"}
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    response = TestClient(app).post(
        "/api/v1/auth/register",
        json={
            "account_type": "tenant",
            "username": f"verified-tenant-{expected_status}",
            "password": "new-tenant-password",
            "email": f"verified-tenant-{expected_status}@example.test",
            "turnstile_token": "provider-token",
            "tenant_name": "Verified Site",
        },
    )

    assert response.status_code == expected_status


def test_browser_mutations_reject_foreign_origins_and_include_security_headers(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "frontend_url", "https://console.example.com")

    response = TestClient(app).post(
        "/api/v1/auth/logout",
        headers={"Origin": "https://attacker.example.com"},
    )

    assert response.status_code == 403
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert response.headers["Strict-Transport-Security"].startswith("max-age=31536000")


def test_standard_signup_requires_single_use_tenant_invite():
    tenant_admin = TestClient(app)
    tenant_email = "invite-tenant-admin@example.test"
    create_tenant = tenant_admin.post(
        "/api/v1/auth/register",
        json={
            "account_type": "tenant",
            "username": "invite-tenant-admin",
            "password": "invite-admin-password",
            "email": tenant_email,
            "turnstile_token": "test-turnstile-token",
            "tenant_name": "Invite Site",
        },
    )
    verify_registered_email(tenant_admin, create_tenant, tenant_email)

    create_invite = tenant_admin.post("/api/v1/admin/invites", json={})
    assert create_invite.status_code == 201
    invite = create_invite.json()
    listed_invites = tenant_admin.get("/api/v1/admin/invites")
    assert listed_invites.status_code == 200
    assert "code" not in listed_invites.text
    assert listed_invites.json()[0]["is_active"] is True

    standard_user = TestClient(app)
    standard_email = "invite-standard-user@example.test"
    signup = standard_user.post(
        "/api/v1/auth/register",
        json={
            "account_type": "standard",
            "username": "invite-standard-user",
            "password": "standard-user-password",
            "email": standard_email,
            "turnstile_token": "test-turnstile-token",
            "invite_code": invite["code"],
        },
    )
    verified_signup = verify_registered_email(standard_user, signup, standard_email)
    assert verified_signup.json()["user"]["tenant_id"] == invite["tenant_id"]
    assert verified_signup.json()["user"]["role"] == "standard_user"

    replay = TestClient(app).post(
        "/api/v1/auth/register",
        json={
            "account_type": "standard",
            "username": "invite-replay-user",
            "password": "standard-user-password",
            "email": "invite-replay-user@example.test",
            "turnstile_token": "test-turnstile-token",
            "invite_code": invite["code"],
        },
    )
    assert replay.status_code == 422
    assert "invalid, expired, or already used" in replay.json()["detail"]
    assert tenant_admin.get("/api/v1/admin/invites").json()[0]["used_at"] is not None


def test_standard_signup_rejects_missing_and_expired_invites():
    missing = TestClient(app).post(
        "/api/v1/auth/register",
        json={
            "account_type": "standard",
            "username": "missing-invite-user",
            "password": "standard-user-password",
            "email": "missing-invite-user@example.test",
            "turnstile_token": "test-turnstile-token",
        },
    )
    assert missing.status_code == 422

    with SessionLocal() as db:
        tenant = Tenant(name="Expired Invite Site", slug="expired-invite-site", agent_token="expired-invite-token")
        db.add(tenant)
        db.flush()
        code = "expired-invite-code-1234567890"
        db.add(
            TenantInvite(
                tenant_id=tenant.id,
                code_hash=hashlib.sha256(code.encode()).hexdigest(),
                created_by_user_id="test",
                created_at=datetime.now(UTC) - timedelta(days=8),
                expires_at=datetime.now(UTC) - timedelta(days=1),
            )
        )
        db.commit()

    expired = TestClient(app).post(
        "/api/v1/auth/register",
        json={
            "account_type": "standard",
            "username": "expired-invite-user",
            "password": "standard-user-password",
            "email": "expired-invite-user@example.test",
            "turnstile_token": "test-turnstile-token",
            "invite_code": code,
        },
    )
    assert expired.status_code == 422
    assert "expired" in expired.json()["detail"]


def test_json_login_establishes_session_and_rejects_invalid_credentials():
    client = TestClient(app)

    invalid = client.post("/api/v1/auth/login", json={"username": "missing", "password": "incorrect"})
    assert invalid.status_code == 401
    oversized = client.post(
        "/api/v1/auth/login",
        json={"username": "missing", "password": "é" * 37},
    )
    assert oversized.status_code == 422

    login = client.post(
        "/api/v1/auth/login",
        json={"username": settings.admin_username, "password": settings.admin_password},
    )
    assert login.status_code == 200
    assert login.json()["user"]["role"] == "super_admin"
    assert client.get("/api/v1/auth/me").status_code == 200


def test_super_admin_can_change_password_after_reauthenticating():
    client = TestClient(app)
    login = client.post(
        "/api/v1/auth/login",
        json={"username": settings.admin_username, "password": settings.admin_password},
    )
    assert login.status_code == 200

    incorrect_password = client.put(
        "/api/v1/auth/password",
        json={
            "current_password": "incorrect-password",
            "new_password": "new-super-admin-password",
        },
    )
    assert incorrect_password.status_code == 400

    changed_password = client.put(
        "/api/v1/auth/password",
        json={
            "current_password": settings.admin_password,
            "new_password": "new-super-admin-password",
        },
    )
    assert changed_password.status_code == 200
    assert changed_password.json() == {"message": "Password changed."}
    assert client.get("/api/v1/auth/me").status_code == 200

    client.post("/api/v1/auth/logout")
    old_password_login = client.post(
        "/api/v1/auth/login",
        json={"username": settings.admin_username, "password": settings.admin_password},
    )
    assert old_password_login.status_code == 401

    new_password_login = client.post(
        "/api/v1/auth/login",
        json={"username": settings.admin_username, "password": "new-super-admin-password"},
    )
    assert new_password_login.status_code == 200


def test_tenant_user_cannot_change_super_admin_password():
    tenant_admin = TestClient(app)
    owner_email = "password-test-owner@example.test"
    created = tenant_admin.post(
        "/api/v1/auth/register",
        json={
            "account_type": "tenant",
            "username": "password-test-owner",
            "password": "password-test-owner-secret",
            "email": owner_email,
            "turnstile_token": "test-turnstile-token",
            "tenant_name": "Password Test Tenant",
        },
    )
    verify_registered_email(tenant_admin, created, owner_email)
    invite = tenant_admin.post("/api/v1/admin/invites", json={}).json()
    client = TestClient(app)
    standard_email = "password-test-standard@example.test"
    signup = client.post(
        "/api/v1/auth/register",
        json={
            "account_type": "standard",
            "username": "password-test-standard",
            "password": "standard-user-password",
            "email": standard_email,
            "turnstile_token": "test-turnstile-token",
            "invite_code": invite["code"],
        },
    )
    verify_registered_email(client, signup, standard_email)
    assert client.put(
        "/api/v1/auth/password",
        json={
            "current_password": "standard-user-password",
            "new_password": "new-standard-user-password",
        },
    ).status_code == 403


def test_password_change_requires_a_strong_new_password():
    client = TestClient(app)
    client.post(
        "/api/v1/auth/login",
        json={"username": settings.admin_username, "password": settings.admin_password},
    )

    response = client.put(
        "/api/v1/auth/password",
        json={
            "current_password": settings.admin_password,
            "new_password": "too-short",
        },
    )
    assert response.status_code == 422
