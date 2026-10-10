from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.authorization import get_authenticated_user, tenant_scoped_query
from app.core.database import get_db
from app.models.device import Device, DeviceChannel
from app.models.user import User
from app.schemas.device import (
    DeviceChannelCreate,
    DeviceChannelRead,
    DeviceChannelUpdate,
    DeviceCreate,
    DeviceRead,
    DeviceUpdate,
)
from app.services.broadcaster import publish_event

router = APIRouter(prefix="/devices", tags=["devices"])


def _get_device(db: Session, device_id: str, user: User) -> Device:
    device = tenant_scoped_query(db.query(Device), Device, user).filter(Device.id == device_id).first()
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found.")
    return device


def _get_channel(db: Session, channel_id: str, user: User) -> DeviceChannel:
    channel = (
        db.query(DeviceChannel)
        .join(Device, Device.id == DeviceChannel.device_id)
        .filter(DeviceChannel.id == channel_id)
    )
    channel = tenant_scoped_query(channel, Device, user).first()
    if channel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device channel not found.")
    return channel


@router.get("", response_model=list[DeviceRead])
async def list_devices(
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    return tenant_scoped_query(db.query(Device), Device, user).order_by(Device.created_at.desc()).all()


@router.post("", response_model=DeviceRead, status_code=status.HTTP_201_CREATED)
async def create_device(
    payload: DeviceCreate,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    existing = db.query(Device.id).filter(Device.device_id == payload.device_id).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A device with this device ID already exists.",
        )

    device = Device(
        owner_id=user.id,
        tenant_id=user.tenant_id,
        name=payload.name,
        device_id=payload.device_id,
        encrypted_local_key=payload.encrypted_local_key,
        ip_address=payload.ip_address,
        device_type=payload.device_type,
        protocol_version=payload.protocol_version,
        enabled=payload.enabled,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    publish_event(
        {
            "type": "device_created",
            "tenant_id": device.tenant_id,
            "device": {"id": device.id, "name": device.name, "device_id": device.device_id},
        }
    )
    return device


@router.get("/{device_id}", response_model=DeviceRead)
async def get_device(
    device_id: UUID,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    return _get_device(db, str(device_id), user)


@router.get("/{device_id}/channels", response_model=list[DeviceChannelRead])
async def list_device_channels(
    device_id: UUID,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    device = _get_device(db, str(device_id), user)
    return (
        db.query(DeviceChannel)
        .filter(DeviceChannel.device_id == device.id)
        .order_by(DeviceChannel.channel_index.asc())
        .all()
    )


@router.post("/{device_id}/channels", response_model=DeviceChannelRead, status_code=status.HTTP_201_CREATED)
async def create_device_channel(
    device_id: UUID,
    payload: DeviceChannelCreate,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    device = _get_device(db, str(device_id), user)
    existing = (
        db.query(DeviceChannel)
        .filter(DeviceChannel.device_id == device.id, DeviceChannel.channel_index == payload.channel_index)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Channel {payload.channel_index} already exists for this device.",
        )

    channel = DeviceChannel(
        device_id=device.id,
        channel_index=payload.channel_index,
        name=payload.name,
        dp_id=payload.dp_id,
        enabled=payload.enabled,
    )
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return channel


@router.get("/channels/{channel_id}", response_model=DeviceChannelRead)
async def get_device_channel(
    channel_id: UUID,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    return _get_channel(db, str(channel_id), user)


@router.get("/{device_id}/channels/{channel_id}", response_model=DeviceChannelRead)
async def get_device_channel_for_device(
    device_id: UUID,
    channel_id: UUID,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    device = _get_device(db, str(device_id), user)
    channel = (
        db.query(DeviceChannel)
        .filter(DeviceChannel.device_id == device.id, DeviceChannel.id == str(channel_id))
        .first()
    )
    if channel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device channel not found.")
    return channel


@router.put("/channels/{channel_id}", response_model=DeviceChannelRead)
async def update_device_channel(
    channel_id: UUID,
    payload: DeviceChannelUpdate,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    channel = _get_channel(db, str(channel_id), user)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(channel, field, value)
    db.commit()
    db.refresh(channel)
    return channel


@router.delete("/channels/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device_channel(
    channel_id: UUID,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    channel = _get_channel(db, str(channel_id), user)
    db.delete(channel)
    db.commit()


@router.put("/{device_id}", response_model=DeviceRead)
async def update_device(
    device_id: UUID,
    payload: DeviceUpdate,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    device = _get_device(db, str(device_id), user)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(device, field, value)
    db.commit()
    db.refresh(device)
    publish_event(
        {
            "type": "device_updated",
            "tenant_id": device.tenant_id,
            "device": {"id": device.id, "name": device.name, "current_state": device.current_state},
        }
    )
    return device


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(
    device_id: UUID,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    device = _get_device(db, str(device_id), user)
    db.delete(device)
    db.commit()
