from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DeviceBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    device_id: str
    ip_address: str | None = None
    device_type: str | None = "default"
    protocol_version: str | None = "3.5"
    enabled: bool = True
    current_state: bool = False


class DeviceCreate(DeviceBase):
    encrypted_local_key: str = Field(..., min_length=1)


class DeviceUpdate(BaseModel):
    name: str | None = None
    device_id: str | None = None
    ip_address: str | None = None
    device_type: str | None = None
    protocol_version: str | None = None
    enabled: bool | None = None
    encrypted_local_key: str | None = None


class DeviceChannelBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    channel_index: int = Field(..., ge=1, le=16)
    name: str
    dp_id: str | None = None
    enabled: bool = True
    current_state: bool = False


class DeviceChannelCreate(DeviceChannelBase):
    pass


class DeviceChannelUpdate(BaseModel):
    channel_index: int | None = Field(default=None, ge=1, le=16)
    name: str | None = None
    dp_id: str | None = None
    enabled: bool | None = None


class DeviceRead(DeviceBase):
    id: UUID
    last_seen_at: datetime | None = None


class DeviceChannelRead(DeviceChannelBase):
    id: UUID
    device_id: UUID | str
