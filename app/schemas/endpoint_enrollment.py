from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


Platform = Literal["windows", "macos", "android", "ios"]
DeviceClass = Literal["laptop", "desktop", "phone", "tablet"]


class EndpointEnrollmentCreate(BaseModel):
    platform: Platform = "macos"
    tenant_id: UUID | None = None


class EndpointEnrollmentCreated(BaseModel):
    id: UUID
    platform: Platform
    enrollment_code: str
    expires_at: datetime


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
