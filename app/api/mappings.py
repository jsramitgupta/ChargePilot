from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.authorization import get_authenticated_user, tenant_scoped_query
from app.core.database import get_db
from app.models.device import Device, DeviceChannel
from app.models.endpoint import Endpoint
from app.models.mapping import Mapping
from app.models.user import User
from app.schemas.mapping import MappingCreate, MappingRead, MappingUpdate

router = APIRouter(prefix="/mappings", tags=["mappings"])


def _get_mapping(db: Session, mapping_id: str, user: User) -> Mapping:
    mapping = tenant_scoped_query(db.query(Mapping), Mapping, user).filter(Mapping.id == mapping_id).first()
    if mapping is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mapping not found.")
    return mapping


def _get_mapping_resources(
    db: Session,
    user: User,
    endpoint_id: str,
    device_id: str,
    channel_id: str | None,
) -> tuple[Endpoint, Device, DeviceChannel | None]:
    endpoint = tenant_scoped_query(db.query(Endpoint), Endpoint, user).filter(Endpoint.id == endpoint_id).first()
    device = tenant_scoped_query(db.query(Device), Device, user).filter(Device.id == device_id).first()
    if endpoint is None or device is None or endpoint.tenant_id != device.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint or device not found.")

    channel = None
    if channel_id is not None:
        channel = (
            db.query(DeviceChannel)
            .filter(DeviceChannel.id == channel_id, DeviceChannel.device_id == device.id)
            .first()
        )
        if channel is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device channel not found.")
    return endpoint, device, channel


def _ensure_unique_mapping(db: Session, endpoint_id: str, device_id: str, mapping_id: str | None = None):
    queryset = db.query(Mapping).filter(Mapping.endpoint_id == endpoint_id, Mapping.device_id == device_id)
    if mapping_id is not None:
        queryset = queryset.filter(Mapping.id != mapping_id)
    if queryset.first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A mapping for this endpoint and switch already exists.",
        )


@router.get("", response_model=list[MappingRead])
async def list_mappings(
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    return tenant_scoped_query(db.query(Mapping), Mapping, user).order_by(Mapping.created_at.desc()).all()


@router.post("", response_model=MappingRead, status_code=status.HTTP_201_CREATED)
async def create_mapping(
    payload: MappingCreate,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    endpoint_id = str(payload.endpoint_id)
    device_id = str(payload.device_id)
    channel_id = str(payload.channel_id) if payload.channel_id is not None else None
    endpoint, device, _ = _get_mapping_resources(db, user, endpoint_id, device_id, channel_id)
    _ensure_unique_mapping(db, endpoint_id, device_id)

    mapping = Mapping(
        owner_id=user.id,
        tenant_id=endpoint.tenant_id,
        endpoint_id=endpoint_id,
        device_id=device_id,
        channel_id=channel_id,
        enabled=payload.enabled,
        on_threshold=payload.on_threshold,
        off_threshold=payload.off_threshold,
        minimum_state_change_interval=payload.minimum_state_change_interval,
    )
    db.add(mapping)
    db.commit()
    db.refresh(mapping)
    return mapping


@router.get("/{mapping_id}", response_model=MappingRead)
async def get_mapping(
    mapping_id: UUID,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    return _get_mapping(db, str(mapping_id), user)


@router.put("/{mapping_id}", response_model=MappingRead)
async def update_mapping(
    mapping_id: UUID,
    payload: MappingUpdate,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    mapping = _get_mapping(db, str(mapping_id), user)
    endpoint_id = str(payload.endpoint_id) if payload.endpoint_id is not None else mapping.endpoint_id
    device_id = str(payload.device_id) if payload.device_id is not None else mapping.device_id
    channel_id = str(payload.channel_id) if payload.channel_id is not None else mapping.channel_id
    endpoint, _, _ = _get_mapping_resources(db, user, endpoint_id, device_id, channel_id)
    _ensure_unique_mapping(db, endpoint_id, device_id, str(mapping_id))

    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            if field in {"endpoint_id", "device_id", "channel_id"}:
                setattr(mapping, field, str(value))
            else:
                setattr(mapping, field, value)
    mapping.tenant_id = endpoint.tenant_id
    db.commit()
    db.refresh(mapping)
    return mapping


@router.delete("/{mapping_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mapping(
    mapping_id: UUID,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    mapping = _get_mapping(db, str(mapping_id), user)
    db.delete(mapping)
    db.commit()
