from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


def test_login_and_registration_pages_redirect_to_frontend():
    client = TestClient(app)

    for path in ("/login", "/register"):
        response = client.get(path, follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"].endswith(path)
        assert "<form" not in response.text


def test_super_admin_can_change_password_after_reauthenticating():
    client = TestClient(app)
    login = client.post(
        "/login",
        data={
            "username": settings.admin_username,
            "password": settings.admin_password,
        },
        follow_redirects=False,
    )
    assert login.status_code == 303

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

    client.get("/logout", follow_redirects=False)
    old_password_login = client.post(
        "/login",
        data={
            "username": settings.admin_username,
            "password": settings.admin_password,
        },
        follow_redirects=False,
    )
    assert "Invalid+username+or+password" in old_password_login.headers["location"]

    new_password_login = client.post(
        "/login",
        data={
            "username": settings.admin_username,
            "password": "new-super-admin-password",
        },
        follow_redirects=False,
    )
    assert new_password_login.status_code == 303


def test_only_super_admin_can_change_password():
    client = TestClient(app)
    client.post(
        "/register",
        data={"username": "password-change-user", "password": "secret123"},
        follow_redirects=False,
    )

    response = client.put(
        "/api/v1/auth/password",
        json={
            "current_password": "secret123",
            "new_password": "new-standard-user-password",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Only the super admin can change this password."


def test_password_change_requires_a_strong_new_password():
    client = TestClient(app)
    client.post(
        "/login",
        data={
            "username": settings.admin_username,
            "password": settings.admin_password,
        },
        follow_redirects=False,
    )

    response = client.put(
        "/api/v1/auth/password",
        json={
            "current_password": settings.admin_password,
            "new_password": "too-short",
        },
    )

    assert response.status_code == 422
