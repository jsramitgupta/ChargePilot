from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AutomationEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_type: str
    reason: str | None = None
    endpoint_id: UUID | None = None
    device_id: UUID | None = None
    success: bool = True
    error: str | None = None
    created_at: datetime
