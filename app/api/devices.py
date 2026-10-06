from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.device import Device, DeviceChannel
from app.schemas.device import (
    DeviceChannelCreate,
    DeviceChannelRead,
    DeviceChannelUpdate,
    DeviceCreate,
    DeviceRead,
    DeviceUpdate,
)

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("", response_model=list[DeviceRead])
async def list_devices(db: Session = Depends(get_db)):
    return db.query(Device).order_by(Device.created_at.desc()).all()


@router.post("", response_model=DeviceRead, status_code=status.HTTP_201_CREATED)
async def create_device(payload: DeviceCreate, db: Session = Depends(get_db)):
    existing = db.query(Device).filter(Device.device_id == payload.device_id).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Device with device_id '{payload.device_id}' already exists.",
        )

    device = Device(
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
    return device


@router.get("/{device_id}", response_model=DeviceRead)
async def get_device(device_id: UUID, db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.id == str(device_id)).first()
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found.")
    return device


@router.get("/{device_id}/channels", response_model=list[DeviceChannelRead])
async def list_device_channels(device_id: UUID, db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.id == str(device_id)).first()
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found.")

    return (
        db.query(DeviceChannel)
        .filter(DeviceChannel.device_id == device.id)
        .order_by(DeviceChannel.channel_index.asc())
        .all()
    )


@router.post("/{device_id}/channels", response_model=DeviceChannelRead, status_code=status.HTTP_201_CREATED)
async def create_device_channel(device_id: UUID, payload: DeviceChannelCreate, db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.id == str(device_id)).first()
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found.")

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
async def get_device_channel(channel_id: UUID, db: Session = Depends(get_db)):
    channel = db.query(DeviceChannel).filter(DeviceChannel.id == str(channel_id)).first()
    if channel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device channel not found.")
    return channel


@router.get("/{device_id}/channels/{channel_id}", response_model=DeviceChannelRead)
async def get_device_channel_for_device(device_id: UUID, channel_id: UUID, db: Session = Depends(get_db)):
    channel = (
        db.query(DeviceChannel)
        .filter(DeviceChannel.device_id == str(device_id), DeviceChannel.id == str(channel_id))
        .first()
    )
    if channel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device channel not found.")
    return channel


@router.put("/channels/{channel_id}", response_model=DeviceChannelRead)
async def update_device_channel(channel_id: UUID, payload: DeviceChannelUpdate, db: Session = Depends(get_db)):
    channel = db.query(DeviceChannel).filter(DeviceChannel.id == str(channel_id)).first()
    if channel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device channel not found.")

    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(channel, field, value)

    db.commit()
    db.refresh(channel)
    return channel


@router.delete("/channels/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device_channel(channel_id: UUID, db: Session = Depends(get_db)):
    channel = db.query(DeviceChannel).filter(DeviceChannel.id == str(channel_id)).first()
    if channel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device channel not found.")

    db.delete(channel)
    db.commit()
    return None


@router.put("/{device_id}", response_model=DeviceRead)
async def update_device(device_id: UUID, payload: DeviceUpdate, db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.id == str(device_id)).first()
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found.")

    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(device, field, value)

    db.commit()
    db.refresh(device)
    return device


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(device_id: UUID, db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.id == str(device_id)).first()
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found.")

    db.delete(device)
    db.commit()
    return None
