from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.authorization import get_authenticated_user, tenant_scoped_query
from app.core.database import get_db
from app.models.event import AutomationEvent
from app.models.user import User

router = APIRouter(prefix="/events", tags=["events"])


@router.get("")
async def list_events(
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    events = tenant_scoped_query(db.query(AutomationEvent), AutomationEvent, user).order_by(
        AutomationEvent.created_at.desc()
    ).all()
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
