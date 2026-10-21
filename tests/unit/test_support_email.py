from email.message import EmailMessage

from pydantic import SecretStr

from app.core.config import settings
from app.services import support_email


def test_build_verification_url_encodes_token():
    url = support_email.build_verification_url("https://app.example.test/", "token+with/slash")

    assert url == "https://app.example.test/verify-email?token=token%2Bwith%2Fslash"


def test_send_verification_email_uses_starttls_and_configured_sender(monkeypatch):
    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            calls.append(("connect", host, port, timeout))

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def ehlo(self):
            calls.append(("ehlo",))

        def starttls(self):
            calls.append(("starttls",))

        def login(self, username, password):
            calls.append(("login", username, password))

        def send_message(self, message: EmailMessage):
            calls.append(("send", message))

    monkeypatch.setattr(settings, "smtp_host", "smtp.example.test")
    monkeypatch.setattr(settings, "smtp_port", 587)
    monkeypatch.setattr(settings, "smtp_username", "mailer@example.test")
    monkeypatch.setattr(settings, "smtp_password", SecretStr("secret-password"))
    monkeypatch.setattr(settings, "smtp_from_email", "mailer@example.test")
    monkeypatch.setattr(settings, "smtp_from_name", "Test ChargePilot")
    monkeypatch.setattr(settings, "smtp_use_starttls", True)
    monkeypatch.setattr(settings, "smtp_use_ssl", False)
    monkeypatch.setattr(support_email.smtplib, "SMTP", FakeSMTP)

    support_email.send_verification_email(
        recipient="new-user@example.test",
        username="new-user",
        verification_url="https://app.example.test/verify-email?token=secret-token",
    )

    assert calls[:3] == [
        ("connect", "smtp.example.test", 587, 10),
        ("ehlo",),
        ("starttls",),
    ]
    assert calls[3] == ("ehlo",)
    assert calls[4] == ("login", "mailer@example.test", "secret-password")
    sent_message = calls[5][1]
    assert sent_message["From"] == "Test ChargePilot <mailer@example.test>"
    assert sent_message["To"] == "new-user@example.test"
    assert "https://app.example.test/verify-email?token=secret-token" in sent_message.get_content()


def test_send_verification_email_rejects_missing_smtp_configuration(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "")

    try:
        support_email.send_verification_email(
            recipient="new-user@example.test",
            username="new-user",
            verification_url="https://app.example.test/verify-email?token=secret-token",
        )
    except RuntimeError as error:
        assert "SMTP is not configured" in str(error)
    else:
        raise AssertionError("Expected missing SMTP configuration to be rejected.")


def test_send_support_email_uses_fixed_recipient_and_reply_to(monkeypatch):
    sent = []

    class FakeSMTP:
        def __init__(self, *_args, **_kwargs):
            return None

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def ehlo(self):
            return None

        def starttls(self):
            return None

        def login(self, *_args):
            return None

        def send_message(self, message):
            sent.append(message)

    monkeypatch.setattr(settings, "smtp_host", "smtp.example.test")
    monkeypatch.setattr(settings, "smtp_username", "mailer@example.test")
    monkeypatch.setattr(settings, "smtp_password", SecretStr("secret-password"))
    monkeypatch.setattr(settings, "smtp_from_email", "mailer@example.test")
    monkeypatch.setattr(settings, "smtp_use_starttls", True)
    monkeypatch.setattr(settings, "smtp_use_ssl", False)
    monkeypatch.setattr(support_email.smtplib, "SMTP", FakeSMTP)

    support_email.send_support_email(
        recipient="support@example.test",
        reply_email="person@example.test",
        subject="Setup question",
        body="I need help configuring a device.",
        username="person",
        tenant_name="Home lab",
    )

    assert len(sent) == 1
    assert sent[0]["To"] == "support@example.test"
    assert sent[0]["Reply-To"] == "person@example.test"
    assert sent[0]["Subject"] == "[ChargePilot Support] Setup question"
    content = sent[0].get_content()
    assert "Support request from person" in content
    assert "Tenant: Home lab" in content
    assert "I need help configuring a device." in content