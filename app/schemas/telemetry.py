from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class TelemetryPayload(BaseModel):
    hostname: str = Field(min_length=1, max_length=160)
    hardware_uuid: UUID | None = None
    ip_address: str = Field(min_length=7, max_length=64)
    battery_percentage: int = Field(ge=0, le=100)
    charging: bool
    ac_connected: bool
    switch_state: bool | None = None
    timestamp: datetime
    agent_version: str = Field(min_length=1, max_length=50)

    @field_validator("hardware_uuid")
    @classmethod
    def validate_hardware_uuid(cls, value: UUID | None) -> UUID | None:
        if value is not None and value.int in {0, (1 << 128) - 1}:
            raise ValueError("hardware_uuid must be a valid, non-placeholder hardware UUID.")
        return value


class TelemetryResponse(BaseModel):
    status: str
    hostname: str
    hardware_uuid: UUID | None = None
    battery_percentage: int
    message: str
