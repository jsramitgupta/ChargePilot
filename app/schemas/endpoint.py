from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class EndpointBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str | None = None
    hostname: str
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
