from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


Platform = Literal["windows", "macos", "android", "ios"]
DeviceClass = Literal["laptop", "desktop", "phone", "tablet"]


class EndpointEnrollmentCreate(BaseModel):
    tenant_id: UUID | None = None


class EndpointEnrollmentCreated(BaseModel):
    id: UUID
    enrollment_code: str
    expires_at: datetime

    @field_validator("expires_at", mode="before")
    @classmethod
    def normalize_expiration_timezone(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class EndpointEnrollmentInfo(BaseModel):
    id: UUID
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    enrollment_count: int
    last_used_at: datetime | None

    @field_validator("created_at", "expires_at", "revoked_at", "last_used_at", mode="before")
    @classmethod
    def normalize_datetime_timezone(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class EndpointEnrollmentExchange(BaseModel):
    code: str = Field(min_length=20, max_length=128)
    platform: Platform
    installation_id: UUID
    hostname: str = Field(min_length=1, max_length=160)
    device_class: DeviceClass | None = None

    @field_validator("hostname")
    @classmethod
    def trim_hostname(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("A device label is required.")
        return normalized

    @model_validator(mode="after")
    def validate_device_class(self) -> "EndpointEnrollmentExchange":
        if self.device_class is None:
            return self
        supported = (
            {"laptop", "desktop"}
            if self.platform in {"windows", "macos"}
            else {"phone", "tablet"}
        )
        if self.device_class not in supported:
            raise ValueError("device_class is not supported for this platform.")
        return self


class EndpointEnrollmentCredentials(BaseModel):
    endpoint_id: UUID
    installation_id: UUID
    platform: Platform
    credential: str
