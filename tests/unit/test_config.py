import pytest
from pydantic import ValidationError

from app.core.config import ENV_FILE, Settings


def test_dotenv_path_is_anchored_to_project_root():
    assert ENV_FILE.is_absolute()
    assert ENV_FILE.name == ".env"
    assert Settings.model_config["env_file"] == ENV_FILE


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
    )

    assert settings.environment == "production"
