import hashlib
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api import admin as admin_api
from app.core.database import SessionLocal
from app.main import app
from app.models.account_invitation import AccountInvitation
from app.models.user import User
from conftest import TEST_ACCOUNT_INVITATION_TOKENS, api_login, register_tenant_admin


def _tenant_admin_client() -> tuple[TestClient, str]:
    client = TestClient(app)
    username = f"people-admin-{uuid4().hex[:8]}"
    register_tenant_admin(client, username, "people-admin-password", "People Test")
    return client, username


def _send_invitation(
    client: TestClient,
    *,
    username: str,
    email: str,
    role: str = "tenant_admin",
    tenant_id: str | None = None,
):
    payload = {"username": username, "email": email, "role": role}
    if tenant_id:
        payload["tenant_id"] = tenant_id
    return client.post("/api/v1/admin/account-invitations", json=payload)


@pytest.mark.parametrize("role", ["tenant_admin", "manager", "standard_user", "viewer"])
def test_email_invitation_creates_account_after_one_time_password_setup(role):
    client, _ = _tenant_admin_client()
    username = f"invited-{role}-{uuid4().hex[:8]}"
    email = f"{username}@example.test"
    invitation_response = _send_invitation(client, username=username, email=email, role=role)

    assert invitation_response.status_code == 201, invitation_response.text
    invitation = invitation_response.json()
    assert invitation["username"] == username
    assert invitation["email"] == email
    assert invitation["role"] == role
    assert invitation["is_active"] is True
    assert "code" not in invitation
    assert "token" not in invitation
    code = TEST_ACCOUNT_INVITATION_TOKENS[email]

    with SessionLocal() as db:
        assert db.query(User).filter_by(username=username).first() is None

    details = client.post("/api/v1/auth/invitation-details", json={"code": code})
    assert details.status_code == 200, details.text
    assert details.json()["username"] == username
    assert details.json()["email"] == email
    assert details.headers["Cache-Control"] == "no-store"

    password = "invited-account-password"
    accepted = client.post(
        "/api/v1/auth/accept-invitation",
        json={"code": code, "password": password},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.headers["Cache-Control"] == "private, no-store"
    assert accepted.json()["user"]["role"] == role
    assert accepted.json()["user"]["email"] == email
    assert client.get("/api/v1/auth/me").json()["username"] == username
    assert client.post("/api/v1/auth/invitation-details", json={"code": code}).status_code == 422

    with SessionLocal() as db:
        account = db.query(User).filter_by(username=username).one()
        assert account.email_verified is True
        assert account.is_admin is (role == "tenant_admin")


def test_invitation_code_expires_and_cannot_be_used():
    client, _ = _tenant_admin_client()
    username = f"expired-invite-{uuid4().hex[:8]}"
    email = f"{username}@example.test"
    created = _send_invitation(client, username=username, email=email)
    assert created.status_code == 201, created.text
    code = TEST_ACCOUNT_INVITATION_TOKENS[email]
    code_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()

    with SessionLocal() as db:
        invitation = db.query(AccountInvitation).filter_by(token_hash=code_hash).one()
        invitation.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()

    details = client.post("/api/v1/auth/invitation-details", json={"code": code})
    assert details.status_code == 422
    accepted = client.post(
        "/api/v1/auth/accept-invitation",
        json={"code": code, "password": "expired-invitation-password"},
    )
    assert accepted.status_code == 422
    with SessionLocal() as db:
        assert db.query(User).filter_by(username=username).first() is None


def test_new_invitation_invalidates_previous_matching_email():
    client, _ = _tenant_admin_client()
    email = f"replacement-{uuid4().hex[:8]}@example.test"
    username = f"replacement-{uuid4().hex[:8]}"
    first = _send_invitation(client, username=username, email=email)
    assert first.status_code == 201, first.text
    first_code = TEST_ACCOUNT_INVITATION_TOKENS[email]

    second = _send_invitation(client, username=username, email=email, role="manager")
    assert second.status_code == 201, second.text
    second_code = TEST_ACCOUNT_INVITATION_TOKENS[email]
    assert second_code != first_code
    assert client.post("/api/v1/auth/invitation-details", json={"code": first_code}).status_code == 422
    assert client.post("/api/v1/auth/invitation-details", json={"code": second_code}).status_code == 200


def test_tenant_admin_cannot_invite_into_another_tenant():
    client, _ = _tenant_admin_client()
    super_admin = TestClient(app)
    api_login(super_admin, "admin", "change-me")
    other_tenant = super_admin.post(
        "/api/v1/admin/tenants",
        json={"name": f"Other {uuid4().hex[:8]}"},
    )
    assert other_tenant.status_code == 201, other_tenant.text

    username = f"scoped-invite-{uuid4().hex[:8]}"
    response = _send_invitation(
        client,
        username=username,
        email=f"{username}@example.test",
        tenant_id=other_tenant.json()["id"],
    )
    assert response.status_code == 201, response.text
    assert response.json()["tenant_id"] != other_tenant.json()["id"]
    assert response.json()["tenant_name"] == "People Test"


def test_invitation_replacement_cannot_revoke_another_tenants_invitation():
    tenant_admin, _ = _tenant_admin_client()
    username = f"cross-tenant-invite-{uuid4().hex[:8]}"
    email = f"{username}@example.test"
    original = _send_invitation(tenant_admin, username=username, email=email)
    assert original.status_code == 201, original.text
    original_code = TEST_ACCOUNT_INVITATION_TOKENS[email]

    super_admin = TestClient(app)
    api_login(super_admin, "admin", "change-me")
    other_tenant = super_admin.post(
        "/api/v1/admin/tenants",
        json={"name": f"Other {uuid4().hex[:8]}"},
    )
    assert other_tenant.status_code == 201, other_tenant.text
    replacement = _send_invitation(
        super_admin,
        username=username,
        email=email,
        tenant_id=other_tenant.json()["id"],
    )

    assert replacement.status_code == 409
    assert tenant_admin.post(
        "/api/v1/auth/invitation-details",
        json={"code": original_code},
    ).status_code == 200


def test_admin_can_delete_pending_invitation_and_invalidate_its_code():
    client, _ = _tenant_admin_client()
    username = f"deleted-invite-{uuid4().hex[:8]}"
    email = f"{username}@example.test"
    created = _send_invitation(client, username=username, email=email)
    assert created.status_code == 201, created.text
    invitation_id = created.json()["id"]
    code = TEST_ACCOUNT_INVITATION_TOKENS[email]
    code_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()

    deleted = client.delete(f"/api/v1/admin/account-invitations/{invitation_id}")

    assert deleted.status_code == 204, deleted.text
    with SessionLocal() as db:
        assert db.query(AccountInvitation).filter_by(id=invitation_id).first() is None
        assert db.query(AccountInvitation).filter_by(token_hash=code_hash).first() is None


def test_deleting_accepted_invitation_does_not_delete_account():
    admin, _ = _tenant_admin_client()
    username = f"accepted-invite-delete-{uuid4().hex[:8]}"
    email = f"{username}@example.test"
    created = _send_invitation(admin, username=username, email=email, role="standard_user")
    assert created.status_code == 201, created.text
    code = TEST_ACCOUNT_INVITATION_TOKENS[email]
    invitation_id = created.json()["id"]
    recipient = TestClient(app)
    accepted = recipient.post(
        "/api/v1/auth/accept-invitation",
        json={"code": code, "password": "accepted-invitation-password"},
    )
    assert accepted.status_code == 200, accepted.text

    deleted = admin.delete(f"/api/v1/admin/account-invitations/{invitation_id}")

    assert deleted.status_code == 204, deleted.text
    with SessionLocal() as db:
        assert db.query(AccountInvitation).filter_by(id=invitation_id).first() is None
        account = db.query(User).filter_by(username=username).one()
        assert account.email == email
    login = TestClient(app).post(
        "/api/v1/auth/login",
        json={"username": username, "password": "accepted-invitation-password"},
    )
    assert login.status_code == 200, login.text


def test_tenant_admin_cannot_delete_another_tenants_invitation():
    invitation_owner, _ = _tenant_admin_client()
    other_admin, _ = _tenant_admin_client()
    username = f"scoped-delete-{uuid4().hex[:8]}"
    email = f"{username}@example.test"
    created = _send_invitation(invitation_owner, username=username, email=email)
    assert created.status_code == 201, created.text
    invitation_id = created.json()["id"]

    deleted = other_admin.delete(f"/api/v1/admin/account-invitations/{invitation_id}")

    assert deleted.status_code == 404
    with SessionLocal() as db:
        assert db.query(AccountInvitation).filter_by(id=invitation_id).first() is not None


def test_email_delivery_failure_revokes_invitation(monkeypatch):
    client, _ = _tenant_admin_client()
    username = f"mail-failure-{uuid4().hex[:8]}"

    def fail_delivery(**_kwargs):
        raise RuntimeError("smtp unavailable")

    monkeypatch.setattr(admin_api, "send_account_invitation_email", fail_delivery)
    response = _send_invitation(
        client,
        username=username,
        email=f"{username}@example.test",
    )

    assert response.status_code == 503
    with SessionLocal() as db:
        invitation = db.query(AccountInvitation).filter_by(username=username).one()
        assert invitation.revoked_at is not None


def test_non_super_admin_can_change_own_password_from_account_api():
    client, username = _tenant_admin_client()
    response = client.put(
        "/api/v1/auth/password",
        json={
            "current_password": "people-admin-password",
            "new_password": "new-people-admin-password",
        },
    )

    assert response.status_code == 200, response.text
    replacement_client = TestClient(app)
    login = replacement_client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "new-people-admin-password"},
    )
    assert login.status_code == 200, login.text
