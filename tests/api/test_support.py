import smtplib

from fastapi.testclient import TestClient

from app.api import support as support_api
from app.core.config import settings
from app.main import app
from conftest import api_login


def test_support_configuration_requires_login():
    response = TestClient(app).get("/api/v1/support/config")

    assert response.status_code == 401


def test_authenticated_user_can_send_support_email(monkeypatch):
    sent = {}

    def capture_support_email(**kwargs):
        sent.update(kwargs)

    monkeypatch.setattr(support_api, "send_support_email", capture_support_email)
    client = TestClient(app)
    api_login(client, settings.admin_username, settings.admin_password)

    configuration = client.get("/api/v1/support/config")
    assert configuration.status_code == 200
    assert configuration.json() == {
        "configured": True,
        "recipient": settings.support_recipient,
    }

    response = client.post(
        "/api/v1/support/email",
        json={
            "reply_email": "  Person@Example.Test ",
            "subject": "Device setup question",
            "body": "I need help finishing the device setup.",
        },
    )

    assert response.status_code == 202
    assert response.json()["message"] == "Your message has been sent to ChargePilot support."
    assert response.headers["Cache-Control"] == "no-store"
    assert sent == {
        "recipient": settings.support_recipient,
        "reply_email": "person@example.test",
        "subject": "Device setup question",
        "body": "I need help finishing the device setup.",
        "username": settings.admin_username,
        "tenant_name": None,
    }


def test_support_email_is_unavailable_when_smtp_is_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "")
    client = TestClient(app)
    api_login(client, settings.admin_username, settings.admin_password)

    assert client.get("/api/v1/support/config").json()["configured"] is False
    response = client.post(
        "/api/v1/support/email",
        json={
            "reply_email": "person@example.test",
            "subject": "Device setup question",
            "body": "I need help finishing the device setup.",
        },
    )

    assert response.status_code == 503


def test_support_email_rejects_invalid_headers_and_short_messages():
    client = TestClient(app)
    api_login(client, settings.admin_username, settings.admin_password)

    response = client.post(
        "/api/v1/support/email",
        json={
            "reply_email": "person@example.test",
            "subject": "Bad subject\nBcc: attacker@example.test",
            "body": "I need help finishing the device setup.",
        },
    )

    assert response.status_code == 422


def test_support_email_delivery_failure_is_reported(monkeypatch):
    def fail_delivery(**_kwargs):
        raise smtplib.SMTPAuthenticationError(535, b"Authentication failed")

    monkeypatch.setattr(support_api, "send_support_email", fail_delivery)
    client = TestClient(app)
    api_login(client, settings.admin_username, settings.admin_password)

    response = client.post(
        "/api/v1/support/email",
        json={
            "reply_email": "person@example.test",
            "subject": "Device setup question",
            "body": "I need help finishing the device setup.",
        },
    )

    assert response.status_code == 503
    assert "could not be sent" in response.json()["detail"]