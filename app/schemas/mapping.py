from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MappingBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    endpoint_id: UUID | str
    device_id: UUID | str
    channel_id: UUID | str | None = None
    enabled: bool = True
    turn_on_enabled: bool = True
    on_threshold: int = Field(default=79, ge=0, le=100)
    off_threshold: int = Field(default=99, ge=0, le=100)
    turn_off_when_charging_enabled: bool = False
    charging_off_threshold: int = Field(default=99, ge=0, le=100)
    minimum_state_change_interval: int = Field(default=300, ge=0)


class MappingCreate(MappingBase):
    pass


class MappingUpdate(BaseModel):
    endpoint_id: UUID | str | None = None
    device_id: UUID | str | None = None
    channel_id: UUID | str | None = None
    enabled: bool | None = None
    turn_on_enabled: bool | None = None
    on_threshold: int | None = Field(default=None, ge=0, le=100)
    off_threshold: int | None = Field(default=None, ge=0, le=100)
    turn_off_when_charging_enabled: bool | None = None
    charging_off_threshold: int | None = Field(default=None, ge=0, le=100)
    minimum_state_change_interval: int | None = Field(default=None, ge=0)

    @field_validator(
        "on_threshold",
        "off_threshold",
        "charging_off_threshold",
        "minimum_state_change_interval",
        mode="before",
    )
    @classmethod
    def reject_null_numeric_values(cls, value: int | None) -> int:
        if value is None:
            raise ValueError("This field cannot be null.")
        return value


class MappingRead(MappingBase):
    id: UUID
    tenant_name: str | None = None
