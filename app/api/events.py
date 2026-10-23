from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.authorization import get_authenticated_user, tenant_scoped_query
from app.core.database import get_db
from app.models.event import AutomationEvent
from app.models.endpoint import Endpoint
from app.models.user import User

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/page")
async def list_event_page(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, alias="per_page"),
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    if per_page not in {50, 100, 500}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Page size must be 50, 100, or 500.",
        )
    events_query = tenant_scoped_query(db.query(AutomationEvent), AutomationEvent, user)
    total_events = events_query.count()
    total_pages = max(1, (total_events + per_page - 1) // per_page)
    page = min(page, total_pages)
    events = (
        events_query.order_by(AutomationEvent.created_at.desc(), AutomationEvent.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    endpoint_ids = {event.endpoint_id for event in events if event.endpoint_id}
    endpoints_by_id = {
        endpoint.id: endpoint
        for endpoint in tenant_scoped_query(db.query(Endpoint), Endpoint, user)
        .filter(Endpoint.id.in_(endpoint_ids)).all()
    } if endpoint_ids else {}
    first_row = (page - 1) * per_page + 1 if total_events else 0
    return {
        "items": [
            {
                "id": event.id,
                "event_type": event.event_type,
                "success": event.success,
                "reason": event.reason,
                "endpoint_id": event.endpoint_id,
                "endpoint": (
                    endpoints_by_id[event.endpoint_id].name
                    or endpoints_by_id[event.endpoint_id].hostname
                )
                if event.endpoint_id in endpoints_by_id else (event.endpoint_id or "unknown"),
                "battery": f"{event.battery_percentage}%"
                if event.battery_percentage is not None else "n/a",
                "activity": event.reason or event.event_type,
                "device_id": event.device_id,
                "channel_id": event.channel_id,
                "previous_state": event.previous_state,
                "new_state": event.new_state,
                "created_at": event.created_at.isoformat() if event.created_at else None,
            }
            for event in events
        ],
        "page": page,
        "per_page": per_page,
        "total_events": total_events,
        "total_pages": total_pages,
        "first_row": first_row,
        "last_row": min(page * per_page, total_events),
    }


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
