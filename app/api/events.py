from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.event import AutomationEvent

router = APIRouter(prefix="/events", tags=["events"])


@router.get("")
async def list_events(db: Session = Depends(get_db)) -> list[dict[str, object]]:
    events = db.query(AutomationEvent).order_by(AutomationEvent.created_at.desc()).all()
    return [
        {
            "id": event.id,
            "event_type": event.event_type,
            "success": event.success,
            "reason": event.reason,
            "endpoint_id": event.endpoint_id,
            "device_id": event.device_id,
            "channel_id": event.channel_id,
            "previous_state": event.previous_state,
            "new_state": event.new_state,
            "created_at": event.created_at.isoformat() if event.created_at else None,
        }
        for event in events
    ]
