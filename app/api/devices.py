from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.authorization import get_authenticated_user, is_super_admin_user, tenant_scoped_query
from app.core.database import get_db
from app.models.event import AutomationEvent
from app.models.connector import SiteConnector
from app.models.device import Device, DeviceChannel
from app.models.mapping import Mapping
from app.models.tenant import Tenant
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
from app.services.connector_service import connector_is_online, queue_device_command
from app.services.local_key_service import encrypt_local_key
from app.services.tuya_service import TuyaService

router = APIRouter(prefix="/devices", tags=["devices"])


class DeviceConnectorUpdate(BaseModel):
    connector_id: UUID | None = None


class DeviceStateUpdate(BaseModel):
    desired_state: bool
    channel_id: UUID | None = None


def _get_device(db: Session, device_id: str, user: User) -> Device:
    device = tenant_scoped_query(db.query(Device), Device, user).filter(Device.id == device_id).first()
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found.")
    return device


def _device_read(db: Session, device: Device) -> DeviceRead:
    tenant_name = (
        db.query(Tenant.name).filter(Tenant.id == device.tenant_id).scalar()
        if device.tenant_id is not None
        else None
    )
    return DeviceRead.model_validate(device).model_copy(update={"tenant_name": tenant_name})


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
    devices = tenant_scoped_query(db.query(Device), Device, user).order_by(Device.created_at.desc()).all()
    tenant_ids = {device.tenant_id for device in devices if device.tenant_id is not None}
    tenant_names = {
        tenant.id: tenant.name
        for tenant in db.query(Tenant).filter(Tenant.id.in_(tenant_ids)).all()
    } if tenant_ids else {}
    return [
        DeviceRead.model_validate(device).model_copy(update={"tenant_name": tenant_names.get(device.tenant_id)})
        for device in devices
    ]


@router.post("/status/refresh")
async def refresh_device_status(
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    devices = (
        tenant_scoped_query(db.query(Device), Device, user)
        .filter(Device.enabled.is_(True))
        .order_by(Device.created_at.asc())
        .all()
    )
    commands: list[dict[str, str | None]] = []
    skipped_devices: list[dict[str, str]] = []

    for device in devices:
        if not device.connector_id:
            skipped_devices.append(
                {"device_id": device.id, "reason": "Assign an active site connector to refresh this switch."}
            )
            continue

        connector = (
            db.query(SiteConnector)
            .filter(
                SiteConnector.id == device.connector_id,
                SiteConnector.tenant_id == device.tenant_id,
                SiteConnector.is_active.is_(True),
                SiteConnector.token_hash.is_not(None),
            )
            .first()
        )
        if connector is None:
            skipped_devices.append(
                {"device_id": device.id, "reason": "The assigned site connector is not enrolled or active."}
            )
            continue
        if not connector_is_online(connector):
            skipped_devices.append(
                {"device_id": device.id, "reason": "The assigned site connector is offline."}
            )
            continue

        channels = (
            db.query(DeviceChannel)
            .filter(DeviceChannel.device_id == device.id, DeviceChannel.enabled.is_(True))
            .order_by(DeviceChannel.channel_index.asc())
            .all()
        )
        if not channels:
            channels_to_check: list[DeviceChannel | None] = [None]
        else:
            channels_to_check = channels

        for channel in channels_to_check:
            command = queue_device_command(
                db,
                device=device,
                operation="get_status",
                channel_index=channel.channel_index if channel is not None else 1,
                channel_id=channel.id if channel is not None else None,
                context={
                    "previous_state": str(
                        channel.current_state if channel is not None else device.current_state
                    ).lower(),
                },
            )
            commands.append(
                {
                    "id": command.id,
                    "device_id": device.id,
                    "channel_id": channel.id if channel is not None else None,
                }
            )

    db.commit()
    return {"commands": commands, "skipped_devices": skipped_devices}


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

    tenant_id = user.tenant_id
    if is_super_admin_user(user):
        tenant_id = str(payload.tenant_id) if payload.tenant_id else None
        if tenant_id and db.query(Tenant.id).filter(Tenant.id == tenant_id).first() is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Select a valid tenant.")

    device = Device(
        owner_id=user.id,
        tenant_id=tenant_id,
        name=payload.name,
        device_id=payload.device_id,
        encrypted_local_key=encrypt_local_key(payload.encrypted_local_key),
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
    return _device_read(db, device)


@router.get("/{device_id}", response_model=DeviceRead)
async def get_device(
    device_id: UUID,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    return _device_read(db, _get_device(db, str(device_id), user))


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
            if field == "encrypted_local_key":
                value = encrypt_local_key(value)
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
    return _device_read(db, device)


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(
    device_id: UUID,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    device = _get_device(db, str(device_id), user)
    db.query(Mapping).filter(Mapping.device_id == device.id).delete(synchronize_session=False)
    db.query(DeviceChannel).filter(DeviceChannel.device_id == device.id).delete(synchronize_session=False)
    db.delete(device)
    db.commit()


@router.put("/{device_id}/connector")
async def assign_device_connector(
    device_id: UUID,
    payload: DeviceConnectorUpdate,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    if not is_super_admin_user(user) and user.role not in {"tenant_admin", "manager"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Connector assignment requires administrator access.",
        )
    device = _get_device(db, str(device_id), user)
    if payload.connector_id is None:
        device.connector_id = None
    else:
        connector = tenant_scoped_query(db.query(SiteConnector), SiteConnector, user).filter(
            SiteConnector.id == str(payload.connector_id),
            SiteConnector.tenant_id == device.tenant_id,
            SiteConnector.is_active.is_(True),
            SiteConnector.token_hash.is_not(None),
        ).first()
        if connector is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Choose an active connector for this tenant.",
            )
        device.connector_id = connector.id
    db.commit()
    return {"message": "Switch connector assignment saved.", "connector_id": device.connector_id}


@router.post("/{device_id}/state")
async def update_device_state(
    device_id: UUID,
    payload: DeviceStateUpdate,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    device = _get_device(db, str(device_id), user)
    channel = None
    if payload.channel_id is not None:
        channel = db.query(DeviceChannel).filter(
            DeviceChannel.id == str(payload.channel_id),
            DeviceChannel.device_id == device.id,
        ).first()
        if channel is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device channel not found.")
    channel_index = channel.channel_index if channel else 1
    previous_state = channel.current_state if channel else device.current_state
    state_label = "ON" if payload.desired_state else "OFF"
    reason = f"Manual override via app for {channel.name}" if channel else "Manual override via app"

    if device.connector_id:
        try:
            command = queue_device_command(
                db,
                device=device,
                operation="set_state",
                channel_index=channel_index,
                channel_id=channel.id if channel else None,
                desired_state=payload.desired_state,
                context={
                    "event_type": f"MANUAL_{state_label}",
                    "reason": reason,
                    "previous_state": str(previous_state).lower(),
                    "new_state": str(payload.desired_state).lower(),
                },
            )
        except ValueError as exc:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Could not queue the switch command. Check the assigned connector and device.",
            ) from exc
        db.commit()
        return {"status": "queued", "command_id": command.id}

    result = await TuyaService.from_device(device).set_state(
        device.device_id,
        on=payload.desired_state,
        channel=channel_index,
    )
    success = bool(result.get("success", False))
    now = datetime.now(UTC)
    if success:
        if channel is not None:
            channel.current_state = payload.desired_state
            device.current_state = any(
                item.current_state
                for item in db.query(DeviceChannel).filter(DeviceChannel.device_id == device.id).all()
            )
        else:
            device.current_state = payload.desired_state
        device.last_state_change_at = now
        device.updated_at = now
    db.add(
        AutomationEvent(
            tenant_id=device.tenant_id,
            event_type=f"MANUAL_{state_label}",
            reason=reason,
            device_id=device.id,
            channel_id=channel.id if channel else None,
            previous_state=str(previous_state).lower(),
            new_state=str(payload.desired_state).lower(),
            success=success,
            error=None if success else str(result.get("error") or "Local device command failed.")[:255],
        )
    )
    db.commit()
    if not success:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(result.get("error") or "Local device command failed."),
        )
    return {"status": "succeeded", "message": f"Switch turned {state_label.lower()}."}
