from datetime import datetime

from pydantic import BaseModel, Field


class TelemetryPayload(BaseModel):
    hostname: str = Field(min_length=1, max_length=160)
    ip_address: str = Field(min_length=7, max_length=64)
    battery_percentage: int = Field(ge=0, le=100)
    charging: bool
    ac_connected: bool
    switch_state: bool | None = None
    timestamp: datetime
    agent_version: str = Field(min_length=1, max_length=50)


class TelemetryResponse(BaseModel):
    status: str
    hostname: str
    battery_percentage: int
    message: str
