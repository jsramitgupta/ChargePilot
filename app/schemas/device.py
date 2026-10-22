from datetime import datetime
from uuid import UUID

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    tenant_id: UUID | None = None


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
    connector_id: UUID | None = None
    tenant_id: UUID | None = None
    tenant_name: str | None = None
    last_seen_at: datetime | None = None
    power_dp_id: str | None = None
    power_multiplier: float = 1.0
    energy_dp_id: str | None = None
    energy_multiplier: float = 0.001
    energy_counter_type: Literal["cumulative", "monthly"] = "cumulative"
    meter_power_watts: float | None = None
    meter_power_sample_at: datetime | None = None
    meter_energy_month_kwh: float | None = None
    meter_energy_sample_at: datetime | None = None
    meter_month_key: str | None = None
    meter_last_sample_at: datetime | None = None
    meter_tracking_since: datetime | None = None


class DeviceMeterSettingsUpdate(BaseModel):
    power_dp_id: str | None = Field(default=None, max_length=50)
    power_multiplier: float = Field(default=1.0, gt=0, le=1_000_000)
    energy_dp_id: str | None = Field(default=None, max_length=50)
    energy_multiplier: float = Field(default=0.001, gt=0, le=1_000_000)
    energy_counter_type: Literal["cumulative", "monthly"] = "cumulative"

    @field_validator("power_dp_id", "energy_dp_id")
    @classmethod
    def normalize_dp_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class DeviceChannelRead(DeviceChannelBase):
    id: UUID
    device_id: UUID | str
