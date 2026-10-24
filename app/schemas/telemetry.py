from datetime import datetime
from uuid import UUID

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class DiskUsage(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    used_bytes: int = Field(ge=0)
    total_bytes: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_capacity(self) -> "DiskUsage":
        if self.used_bytes > self.total_bytes:
            raise ValueError("Disk usage cannot exceed total capacity.")
        return self


class SystemMetrics(BaseModel):
    cpu_usage_percent: float | None = Field(default=None, ge=0, le=100)
    gpu_usage_percent: float | None = Field(default=None, ge=0, le=100)
    memory_used_bytes: int | None = Field(default=None, ge=0)
    memory_total_bytes: int | None = Field(default=None, gt=0)
    disks: list[DiskUsage] = Field(default_factory=list, max_length=16)

    @model_validator(mode="after")
    def validate_memory(self) -> "SystemMetrics":
        if (
            self.memory_used_bytes is not None
            and self.memory_total_bytes is not None
            and self.memory_used_bytes > self.memory_total_bytes
        ):
            raise ValueError("Memory usage cannot exceed total memory.")
        return self


class TelemetryPayload(BaseModel):
    hostname: str = Field(min_length=1, max_length=160)
    hardware_uuid: UUID | None = None
    installation_id: UUID | None = None
    platform: Literal["windows", "macos", "android", "ios"] = "windows"
    device_class: Literal["laptop", "desktop", "phone", "tablet"] | None = None
    ip_address: str | None = Field(default=None, min_length=7, max_length=64)
    battery_percentage: int = Field(ge=0, le=100)
    charging: bool
    ac_connected: bool | None = None
    switch_state: bool | None = None
    system_metrics: SystemMetrics | None = None
    timestamp: datetime
    agent_version: str = Field(min_length=1, max_length=50)

    @field_validator("hardware_uuid")
    @classmethod
    def validate_hardware_uuid(cls, value: UUID | None) -> UUID | None:
        if value is not None and value.int in {0, (1 << 128) - 1}:
            raise ValueError("hardware_uuid must be a valid, non-placeholder hardware UUID.")
        return value

    @model_validator(mode="after")
    def validate_device_class(self) -> "TelemetryPayload":
        if self.device_class is None:
            return self
        expected = (
            {"laptop", "desktop"}
            if self.platform in {"windows", "macos"}
            else {"phone", "tablet"}
        )
        if self.device_class not in expected:
            raise ValueError("device_class is not supported for this platform.")
        return self


class TelemetryResponse(BaseModel):
    status: str
    hostname: str
    hardware_uuid: UUID | None = None
    platform: str = "windows"
    battery_percentage: int
    message: str
    reporting_interval_seconds: int = 300
