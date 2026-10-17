from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from fastapi import Header

from app.core.database import get_db
from app.core.authorization import get_authenticated_user, is_super_admin_user, tenant_scoped_query
from app.models.device import Device
from app.models.endpoint import Endpoint
from app.models.mapping import Mapping
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.endpoint import EndpointCreate, EndpointRead, EndpointTenantAssignment
from app.services.endpoint_service import (
    EndpointTenantAssignmentError,
    assign_unassigned_endpoint,
    authenticate_endpoint_token,
)

router = APIRouter(prefix="/endpoints", tags=["endpoints"])


def _normalize_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@router.get("")
async def list_endpoints(
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    endpoints = tenant_scoped_query(db.query(Endpoint), Endpoint, user).order_by(
        Endpoint.last_seen_at.desc().nullslast()
    ).all()
    tenant_ids = {endpoint.tenant_id for endpoint in endpoints if endpoint.tenant_id is not None}
    tenant_names = {
        tenant.id: tenant.name
        for tenant in db.query(Tenant).filter(Tenant.id.in_(tenant_ids)).all()
    } if tenant_ids else {}
    rows: list[dict[str, object]] = []
    mapped_names: dict[str, str] = {}
    mapped_states: dict[str, bool] = {}
    mapped_tenant_names: dict[str, str] = {}
    endpoint_ids = [endpoint.id for endpoint in endpoints]
    if endpoint_ids:
        mapped_rows = (
            db.query(Mapping.endpoint_id, Device.name, Device.current_state, Device.tenant_id)
            .join(Device, Device.id == Mapping.device_id)
            .join(Endpoint, Endpoint.id == Mapping.endpoint_id)
            .filter(Mapping.endpoint_id.in_(endpoint_ids), Mapping.enabled.is_(True))
            .filter(
                Mapping.tenant_id.is_not_distinct_from(Endpoint.tenant_id),
                Device.tenant_id.is_not_distinct_from(Endpoint.tenant_id),
            )
            .order_by(Mapping.created_at.desc())
            .all()
        )
        for endpoint_id, device_name, current_state, device_tenant_id in mapped_rows:
            mapped_names.setdefault(endpoint_id, device_name)
            mapped_states.setdefault(endpoint_id, current_state)
            mapped_tenant_names.setdefault(endpoint_id, tenant_names.get(device_tenant_id, "Unassigned"))
    for endpoint in endpoints:
        last_seen = _normalize_utc(endpoint.last_seen_at)
        rows.append(
            {
                "id": endpoint.id,
                "tenant_id": endpoint.tenant_id,
                "tenant_name": tenant_names.get(endpoint.tenant_id),
                "hostname": endpoint.hostname,
                "hardware_uuid": endpoint.hardware_uuid,
                "ip_address": endpoint.ip_address,
                "battery": endpoint.battery_percentage,
                "charging": endpoint.charging,
                "ac_connected": endpoint.ac_connected,
                "last_seen_at": last_seen.isoformat() if last_seen else None,
                "status": "online" if last_seen and (datetime.now(UTC) - last_seen).total_seconds() <= 600 else "offline",
                "mapped_device": mapped_names.get(endpoint.id, "No mapped switch"),
                "mapped_device_tenant": mapped_tenant_names.get(endpoint.id),
                "switch_state": mapped_states.get(endpoint.id),
            }
        )
    return rows


@router.post("", response_model=EndpointRead, status_code=status.HTTP_201_CREATED)
async def create_endpoint(
    payload: EndpointCreate,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    hardware_uuid = str(payload.hardware_uuid) if payload.hardware_uuid else None
    if hardware_uuid and db.query(Endpoint.id).filter(
        Endpoint.hardware_uuid == hardware_uuid
    ).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This hardware UUID is already registered.",
        )

    endpoint = Endpoint(
        owner_id=user.id,
        tenant_id=user.tenant_id,
        name=payload.name or payload.hostname,
        hostname=payload.hostname,
        hardware_uuid=hardware_uuid,
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


@router.delete("/{endpoint_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_endpoint(
    endpoint_id: UUID,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    endpoint = tenant_scoped_query(db.query(Endpoint), Endpoint, user).filter(
        Endpoint.id == str(endpoint_id)
    ).first()
    if endpoint is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not found.")
    db.query(Mapping).filter(Mapping.endpoint_id == endpoint.id).delete(synchronize_session=False)
    db.delete(endpoint)
    db.commit()


@router.patch("/{endpoint_id}/tenant")
async def assign_endpoint_tenant(
    endpoint_id: UUID,
    payload: EndpointTenantAssignment,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    if not is_super_admin_user(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the Super Admin can assign an endpoint to a tenant.",
        )

    endpoint = db.query(Endpoint).filter(Endpoint.id == str(endpoint_id)).with_for_update().first()
    if endpoint is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not found.")

    tenant = db.query(Tenant).filter(Tenant.id == str(payload.tenant_id)).first()
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found.")

    try:
        changed = assign_unassigned_endpoint(db, endpoint, tenant)
    except EndpointTenantAssignmentError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    if changed:
        db.commit()
    return {"id": endpoint.id, "tenant_id": tenant.id, "tenant_name": tenant.name}


def _serialize_agent_config(endpoint: Endpoint, db: Session) -> dict[str, object]:
    mappings = (
        db.query(Mapping)
        .filter(Mapping.endpoint_id == endpoint.id, Mapping.tenant_id == endpoint.tenant_id)
        .order_by(Mapping.created_at.desc())
        .all()
    )
    return {
        "endpoint_id": endpoint.id,
        "hostname": endpoint.hostname,
        "hardware_uuid": endpoint.hardware_uuid,
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
    hardware_uuid: UUID | None = None,
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
):
    is_valid, tenant = authenticate_endpoint_token(authorization, db)
    if not is_valid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing endpoint token.")

    if not hostname and not hardware_uuid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="hardware_uuid or hostname query parameter is required.",
        )

    endpoint_query = db.query(Endpoint)
    if tenant is not None:
        endpoint_query = endpoint_query.filter(Endpoint.tenant_id == tenant.id)
    else:
        endpoint_query = endpoint_query.filter(Endpoint.tenant_id.is_(None))

    endpoint = None
    if hardware_uuid:
        any_tenant_endpoint = db.query(Endpoint).filter(
            Endpoint.hardware_uuid == str(hardware_uuid)
        ).first()
        if any_tenant_endpoint is not None:
            if any_tenant_endpoint.tenant_id != (tenant.id if tenant else None):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Endpoint not found.",
                )
            endpoint = any_tenant_endpoint
    if endpoint is None and hostname:
        legacy_matches = endpoint_query.filter(
            Endpoint.hostname == hostname,
            Endpoint.hardware_uuid.is_(None),
        ).all()
        if len(legacy_matches) > 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Multiple legacy endpoints share this hostname; use the hardware UUID.",
            )
        endpoint = legacy_matches[0] if legacy_matches else None
    if endpoint is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not found.")

    return _serialize_agent_config(endpoint, db)


@router.get("/{endpoint_id}/agent-config")
async def get_endpoint_agent_config(
    endpoint_id: str,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    endpoint = tenant_scoped_query(db.query(Endpoint), Endpoint, user).filter(
        Endpoint.id == endpoint_id
    ).first()
    if endpoint is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not found.")

    return _serialize_agent_config(endpoint, db)


@router.get("/{endpoint_id}/readings")
async def get_endpoint_readings(
    endpoint_id: str,
    limit: int = 30,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    from app.models.telemetry import BatteryReading

    endpoint = tenant_scoped_query(db.query(Endpoint), Endpoint, user).filter(
        Endpoint.id == endpoint_id
    ).first()
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
