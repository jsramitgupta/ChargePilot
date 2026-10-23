from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EndpointBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str | None = None
    hostname: str
    hardware_uuid: UUID | None = None
    ip_address: str | None = None
    battery_percentage: int = 0
    charging: bool = False
    ac_connected: bool = False
    enabled: bool = True
    agent_version: str | None = None


class EndpointCreate(EndpointBase):
    pass


class EndpointRead(EndpointBase):
    id: UUID
    last_seen_at: datetime | None = None


class EndpointTenantAssignment(BaseModel):
    tenant_id: UUID


class EndpointAutomationUpdate(BaseModel):
    enabled: bool


class EndpointLabelUpdate(BaseModel):
    label: str = Field(min_length=1, max_length=160)

    @field_validator("label")
    @classmethod
    def trim_label(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("A device label is required.")
        return value
