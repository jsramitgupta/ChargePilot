import os

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_POSTGRES_URL = "postgresql+psycopg://chargepilot:chargepilot@localhost:5432/chargepilot"


class Settings(BaseSettings):
    app_name: str = "ChargePilot"
    environment: str = "development"
    secret_key: str = Field(default="change-me-in-production")
    database_url: str = Field(
        default_factory=lambda: (
            os.environ.get("CHARGEPILOT_DATABASE_URL")
            or ("sqlite://" if os.environ.get("PYTEST_CURRENT_TEST") else DEFAULT_POSTGRES_URL)
        )
    )
    encryption_key: str = Field(default="replace-with-32-byte-base64-key")
    admin_username: str = "admin"
    admin_password: str = "change-me"
    telemetry_rate_limit_per_minute: int = 60
    endpoint_offline_timeout_seconds: int = 600
    api_v1_prefix: str = "/api/v1"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="CHARGEPILOT_",
        extra="ignore",
    )


settings = Settings()
