import os

from pydantic import Field
from pydantic import model_validator
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

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        if self.environment.casefold() != "production":
            return self

        if not self.database_url.startswith("postgresql+psycopg://"):
            raise ValueError("Production requires a PostgreSQL psycopg database URL.")
        if self.secret_key == "change-me-in-production" or len(self.secret_key) < 32:
            raise ValueError("Production requires a unique secret key of at least 32 characters.")
        if self.encryption_key == "replace-with-32-byte-base64-key" or len(self.encryption_key) < 32:
            raise ValueError("Production requires a unique encryption key of at least 32 characters.")
        if self.admin_password == "change-me" or len(self.admin_password) < 12:
            raise ValueError("Production requires an admin password of at least 12 characters.")
        return self


settings = Settings()
