from uuid import UUID

from pydantic import BaseModel, ConfigDict


class MappingBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    endpoint_id: UUID | str
    device_id: UUID | str
    channel_id: UUID | str | None = None
    enabled: bool = True
    on_threshold: int = 79
    off_threshold: int = 99
    minimum_state_change_interval: int = 300


class MappingCreate(MappingBase):
    pass


class MappingUpdate(BaseModel):
    endpoint_id: UUID | str | None = None
    device_id: UUID | str | None = None
    channel_id: UUID | str | None = None
    enabled: bool | None = None
    on_threshold: int | None = None
    off_threshold: int | None = None
    minimum_state_change_interval: int | None = None


class MappingRead(MappingBase):
    id: UUID
