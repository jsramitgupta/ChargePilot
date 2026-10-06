from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.endpoint import Endpoint

router = APIRouter(prefix="/endpoints", tags=["endpoints"])


def _normalize_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@router.get("")
async def list_endpoints(db: Session = Depends(get_db)) -> list[dict[str, object]]:
    endpoints = db.query(Endpoint).order_by(Endpoint.last_seen_at.desc().nullslast()).all()
    rows: list[dict[str, object]] = []
    for endpoint in endpoints:
        last_seen = _normalize_utc(endpoint.last_seen_at)
        rows.append(
            {
                "id": endpoint.id,
                "hostname": endpoint.hostname,
                "ip_address": endpoint.ip_address,
                "battery": endpoint.battery_percentage,
                "status": "online" if last_seen and (datetime.now(UTC) - last_seen).total_seconds() <= 600 else "offline",
                "mapped_device": "No mapped switch",
            }
        )
    return rows
