import pytest
from pydantic import ValidationError

from app.core.config import ENV_FILE, Settings


def test_dotenv_path_is_anchored_to_project_root():
    assert ENV_FILE.is_absolute()
    assert ENV_FILE.name == ".env"
    assert Settings.model_config["env_file"] == ENV_FILE


def test_platform_telemetry_defaults_and_allow_lists_are_validated():
    settings = Settings(_env_file=None)

    assert settings.enabled_telemetry_platforms == {"windows", "macos", "android", "ios"}
    assert settings.automation_telemetry_platforms == {"windows", "macos"}
    assert settings.telemetry_automation_max_age_seconds == 600

    android_enabled = Settings(
        _env_file=None,
        telemetry_enabled_platforms="windows,macos,android",
        telemetry_automation_enabled_platforms="windows,macos",
    )
    assert "android" in android_enabled.enabled_telemetry_platforms

    with pytest.raises(ValidationError, match="supported platforms"):
        Settings(_env_file=None, telemetry_enabled_platforms="windows,unknown")
    with pytest.raises(ValidationError, match="also be enabled"):
        Settings(
            _env_file=None,
            telemetry_enabled_platforms="windows,macos",
            telemetry_automation_enabled_platforms="windows,ios",
        )


def test_production_settings_reject_weak_secrets_and_non_postgresql_database():
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            environment="production",
            database_url="sqlite://",
            secret_key="change-me-in-production",
            encryption_key="replace-with-32-byte-base64-key",
            admin_password="change-me",
        )


def test_production_settings_accept_postgres_and_strong_secrets():
    settings = Settings(
        _env_file=None,
        environment="production",
        database_url="postgresql+psycopg://chargepilot:secret@db:5432/chargepilot",
        secret_key="s" * 43,
        encryption_key="e" * 43,
        admin_password="p" * 24,
        session_cookie_secure=True,
    )

    assert settings.environment == "production"


def test_cross_site_session_cookies_require_secure_transport():
    with pytest.raises(ValidationError, match="SameSite=None"):
        Settings(
            _env_file=None,
            session_cookie_samesite="none",
            session_cookie_secure=False,
        )


def test_frontend_url_must_be_an_origin():
    with pytest.raises(ValidationError, match="HTTP\\(S\\) origin"):
        Settings(_env_file=None, frontend_url="https://chargepilot.example.com/app")


def test_api_url_must_be_an_origin():
    with pytest.raises(ValidationError, match="HTTP\\(S\\) origin"):
        Settings(_env_file=None, api_url="https://chargepilot.example.com/api/v1")


def test_frontend_url_rejects_embedded_credentials():
    with pytest.raises(ValidationError, match="HTTP\\(S\\) origin"):
        Settings(
            _env_file=None,
            frontend_url="https://user:password@chargepilot.example.com",
        )


def test_production_requires_secure_session_cookies():
    with pytest.raises(ValidationError, match="secure session cookies"):
        Settings(
            _env_file=None,
            environment="production",
            database_url="postgresql+psycopg://user:pass@db:5432/chargepilot",
            secret_key="s" * 43,
            encryption_key="e" * 43,
            admin_password="p" * 24,
            session_cookie_secure=False,
        )


def test_smtp_settings_must_be_configured_as_a_complete_set():
    with pytest.raises(ValidationError, match="SMTP requires"):
        Settings(
            _env_file=None,
            smtp_host="smtp.example.test",
        )


def test_smtp_cannot_enable_starttls_and_implicit_ssl_together():
    with pytest.raises(ValidationError, match="cannot both be enabled"):
        Settings(
            _env_file=None,
            smtp_host="smtp.example.test",
            smtp_username="mailer@example.test",
            smtp_password="smtp-password",
            smtp_from_email="mailer@example.test",
            smtp_use_starttls=True,
            smtp_use_ssl=True,
        )


def test_support_recipient_must_be_an_email_address():
    with pytest.raises(ValidationError, match="Support recipient"):
        Settings(_env_file=None, support_recipient="not-an-email")
