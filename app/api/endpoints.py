from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from fastapi import Header

from app.core.database import get_db
from app.models.endpoint import Endpoint
from app.models.mapping import Mapping
from app.schemas.endpoint import EndpointCreate, EndpointRead
from app.services.endpoint_service import validate_endpoint_auth

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


@router.post("", response_model=EndpointRead, status_code=status.HTTP_201_CREATED)
async def create_endpoint(payload: EndpointCreate, db: Session = Depends(get_db)):
    endpoint = Endpoint(
        name=payload.name or payload.hostname,
        hostname=payload.hostname,
        ip_address=payload.ip_address,
        battery_percentage=payload.battery_percentage,
        charging=payload.charging,
        ac_connected=payload.ac_connected,
        enabled=payload.enabled,
        agent_version=payload.agent_version,
    )
    db.add(endpoint)
    db.commit()
    db.refresh(endpoint)
    return endpoint


def _serialize_agent_config(endpoint: Endpoint, db: Session) -> dict[str, object]:
    mappings = (
        db.query(Mapping)
        .filter(Mapping.endpoint_id == endpoint.id)
        .order_by(Mapping.created_at.desc())
        .all()
    )
    return {
        "endpoint_id": endpoint.id,
        "hostname": endpoint.hostname,
        "mappings": [
            {
                "id": mapping.id,
                "endpoint_id": mapping.endpoint_id,
                "device_id": mapping.device_id,
                "channel_id": mapping.channel_id,
                "enabled": mapping.enabled,
                "on_threshold": mapping.on_threshold,
                "off_threshold": mapping.off_threshold,
                "minimum_state_change_interval": mapping.minimum_state_change_interval,
            }
            for mapping in mappings
        ],
    }


@router.get("/agent-config")
async def get_endpoint_agent_config_by_hostname(
    hostname: str | None = None,
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
):
    if not validate_endpoint_auth(authorization, db):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing endpoint token.")

    if not hostname:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="hostname query parameter is required.")

    endpoint = db.query(Endpoint).filter(Endpoint.hostname == hostname).first()
    if endpoint is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not found.")

    return _serialize_agent_config(endpoint, db)


@router.get("/{endpoint_id}/agent-config")
async def get_endpoint_agent_config(endpoint_id: str, db: Session = Depends(get_db)):
    endpoint = db.query(Endpoint).filter(Endpoint.id == endpoint_id).first()
    if endpoint is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not found.")

    return _serialize_agent_config(endpoint, db)


@router.get("/{endpoint_id}/readings")
async def get_endpoint_readings(endpoint_id: str, limit: int = 30, db: Session = Depends(get_db)):
    from app.models.telemetry import BatteryReading

    endpoint = db.query(Endpoint).filter(Endpoint.id == endpoint_id).first()
    if endpoint is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not found.")

    readings = (
        db.query(BatteryReading)
        .filter(BatteryReading.endpoint_id == endpoint_id)
        .order_by(BatteryReading.timestamp.desc())
        .limit(limit)
        .all()
    )

    # return in chronological order
    data = [
        {"timestamp": r.timestamp.isoformat(), "battery_percentage": r.battery_percentage}
        for r in reversed(readings)
    ]

    return {"endpoint_id": endpoint_id, "readings": data}
