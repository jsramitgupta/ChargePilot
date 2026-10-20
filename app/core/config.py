import os
import re
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field
from pydantic import SecretStr
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_POSTGRES_URL = "postgresql+psycopg://chargepilot:chargepilot@localhost:5432/chargepilot"
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


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
    telemetry_max_age_seconds: int = Field(default=604800, ge=1)
    telemetry_max_future_skew_seconds: int = Field(default=300, ge=0)
    telemetry_automation_max_age_seconds: int = Field(default=600, ge=1)
    telemetry_enabled_platforms: str = "windows,macos,android,ios"
    telemetry_automation_enabled_platforms: str = "windows,macos"
    api_v1_prefix: str = "/api/v1"
    api_url: str = ""
    frontend_url: str = ""
    turnstile_site_key: str = ""
    turnstile_secret_key: SecretStr = SecretStr("")
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_from_email: str = ""
    smtp_from_name: str = "ChargePilot"
    smtp_use_starttls: bool = True
    smtp_use_ssl: bool = False
    support_recipient: str = Field(
        default="chargepilot.support@endusercompute.in",
        min_length=3,
        max_length=254,
    )
    session_cookie_secure: bool = False
    session_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    kafka_bootstrap_servers: str = "kafka:9092"
    kafka_security_protocol: Literal["PLAINTEXT", "SSL", "SASL_PLAINTEXT", "SASL_SSL"] = "PLAINTEXT"
    kafka_sasl_mechanism: str | None = None
    kafka_sasl_username: SecretStr | None = None
    kafka_sasl_password: SecretStr | None = None
    kafka_ssl_ca_file: str | None = None
    telemetry_kafka_topic: str = "chargepilot.telemetry.v1"
    telemetry_dead_letter_topic: str = "chargepilot.telemetry.dlq.v1"
    telemetry_consumer_group: str = "chargepilot-automation-v1"

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_prefix="CHARGEPILOT_",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        valid_platforms = {"windows", "macos", "android", "ios"}
        for setting_name, value in (
            ("telemetry_enabled_platforms", self.telemetry_enabled_platforms),
            ("telemetry_automation_enabled_platforms", self.telemetry_automation_enabled_platforms),
        ):
            platforms = {item.strip().casefold() for item in value.split(",") if item.strip()}
            if not platforms or not platforms <= valid_platforms:
                raise ValueError(
                    f"{setting_name} must be a comma-separated list of supported platforms."
                )
        enabled_platforms = {
            item.strip().casefold()
            for item in self.telemetry_enabled_platforms.split(",")
            if item.strip()
        }
        automation_platforms = {
            item.strip().casefold()
            for item in self.telemetry_automation_enabled_platforms.split(",")
            if item.strip()
        }
        if not automation_platforms <= enabled_platforms:
            raise ValueError("Automation platforms must also be enabled for telemetry.")
        if self.telemetry_automation_max_age_seconds > self.telemetry_max_age_seconds:
            raise ValueError(
                "Telemetry automation maximum age cannot exceed the telemetry ingress maximum age."
            )
        smtp_settings_present = any(
            (
                self.smtp_host,
                self.smtp_username,
                self.smtp_password.get_secret_value(),
                self.smtp_from_email,
            )
        )
        if smtp_settings_present and not all(
            (
                self.smtp_host,
                self.smtp_username,
                self.smtp_password.get_secret_value(),
                self.smtp_from_email,
            )
        ):
            raise ValueError(
                "SMTP requires a host, username, password, and sender email address."
            )
        if self.smtp_use_starttls and self.smtp_use_ssl:
            raise ValueError("SMTP STARTTLS and implicit SSL cannot both be enabled.")
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", self.support_recipient):
            raise ValueError("Support recipient must be a valid email address.")

        for setting_name, url in (
            ("API", self.api_url),
            ("Frontend", self.frontend_url),
        ):
            if not url:
                continue
            parsed_url = urlsplit(url)
            if (
                parsed_url.scheme not in {"http", "https"}
                or not parsed_url.netloc
                or parsed_url.username is not None
                or parsed_url.password is not None
                or parsed_url.path not in {"", "/"}
                or parsed_url.query
                or parsed_url.fragment
            ):
                raise ValueError(
                    f"{setting_name} URL must be an HTTP(S) origin without credentials, "
                    "a path, query, or fragment."
                )

        if self.session_cookie_samesite == "none" and not self.session_cookie_secure:
            raise ValueError("SameSite=None session cookies require secure cookies.")

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
        if not self.session_cookie_secure:
            raise ValueError("Production requires secure session cookies.")
        return self

    @property
    def enabled_telemetry_platforms(self) -> frozenset[str]:
        return frozenset(
            item.strip().casefold()
            for item in self.telemetry_enabled_platforms.split(",")
            if item.strip()
        )

    @property
    def automation_telemetry_platforms(self) -> frozenset[str]:
        return frozenset(
            item.strip().casefold()
            for item in self.telemetry_automation_enabled_platforms.split(",")
            if item.strip()
        )

    @property
    def smtp_configured(self) -> bool:
        return bool(
            self.smtp_host
            and self.smtp_username
            and self.smtp_password.get_secret_value()
            and self.smtp_from_email
        )


settings = Settings()
