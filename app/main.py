from datetime import UTC, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.api.devices import router as devices_router
from app.api.endpoints import router as endpoints_router
from app.api.events import router as events_router
from app.api.health import router as health_router
from app.api.mappings import router as mappings_router
from app.api.telemetry import router as telemetry_router
from app.core.config import settings
from app.core.database import create_db_and_tables, get_db
from app.models.device import Device, DeviceChannel
from app.models.endpoint import Endpoint
from app.models.event import AutomationEvent
from app.models.mapping import Mapping
from app.services.tuya_service import TuyaService

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Self-hosted battery automation platform for local Tuya control.",
)

create_db_and_tables()


@app.on_event("startup")
async def startup_event() -> None:
    create_db_and_tables()


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.include_router(health_router)
app.include_router(telemetry_router, prefix=settings.api_v1_prefix)
app.include_router(endpoints_router, prefix=settings.api_v1_prefix)
app.include_router(devices_router, prefix=settings.api_v1_prefix)
app.include_router(mappings_router, prefix=settings.api_v1_prefix)
app.include_router(events_router, prefix=settings.api_v1_prefix)


def _normalize_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@app.get("/", response_class=HTMLResponse)
async def dashboard_view(request: Request, db: Session = Depends(get_db)):
    endpoints = db.query(Endpoint).order_by(Endpoint.last_seen_at.desc().nullslast()).all()
    devices = db.query(Device).all()
    mappings = db.query(Mapping).all()

    total_endpoints = len(endpoints)
    online_threshold = 600
    online_endpoints = sum(
        1
        for endpoint in endpoints
        if (
            endpoint.last_seen_at is not None
            and _normalize_utc(endpoint.last_seen_at) is not None
            and (datetime.now(UTC) - _normalize_utc(endpoint.last_seen_at)).total_seconds() <= online_threshold
        )
    )
    offline_endpoints = total_endpoints - online_endpoints
    total_devices = len(devices)
    online_devices = sum(1 for device in devices if device.enabled)
    active_automations = len(mappings)
    failed_automations = 0

    rows = []
    for endpoint in endpoints:
        mapped_device = None
        if mappings:
            for mapping in mappings:
                if mapping.endpoint_id == endpoint.id:
                    mapped_device = db.query(Device).filter(Device.id == mapping.device_id).first()
                    break
        switch_name = mapped_device.name if mapped_device else "No mapped switch"
        switch_state = "ON" if mapped_device and mapped_device.current_state else "OFF"
        last_seen = _normalize_utc(endpoint.last_seen_at) if endpoint.last_seen_at else None
        rows.append(
            {
                "hostname": endpoint.hostname,
                "battery": endpoint.battery_percentage,
                "charging": endpoint.charging,
                "switch": switch_name,
                "switch_state": switch_state,
                "last_seen": last_seen.isoformat() if last_seen else "never",
            }
        )

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "total_endpoints": total_endpoints,
            "online_endpoints": online_endpoints,
            "offline_endpoints": offline_endpoints,
            "total_devices": total_devices,
            "online_devices": online_devices,
            "active_automations": active_automations,
            "failed_automations": failed_automations,
            "rows": rows,
        },
    )


@app.get("/endpoints", response_class=HTMLResponse)
async def endpoints_view(request: Request, db: Session = Depends(get_db)):
    endpoints = db.query(Endpoint).order_by(Endpoint.last_seen_at.desc().nullslast()).all()
    rows = []
    for endpoint in endpoints:
        last_seen = _normalize_utc(endpoint.last_seen_at)
        rows.append(
            {
                "id": endpoint.id,
                "hostname": endpoint.hostname,
                "ip_address": endpoint.ip_address or "unknown",
                "battery": endpoint.battery_percentage,
                "charging": endpoint.charging,
                "last_seen": last_seen.isoformat() if last_seen else "never",
                "status": "online" if last_seen and (datetime.now(UTC) - last_seen).total_seconds() <= 600 else "offline",
            }
        )
    return templates.TemplateResponse("endpoints.html", {"request": request, "rows": rows})


@app.post("/endpoints/{endpoint_id}/delete")
async def delete_endpoint_form(endpoint_id: str, db: Session = Depends(get_db)):
    endpoint = db.query(Endpoint).filter(Endpoint.id == endpoint_id).first()
    if endpoint is not None:
        for mapping in db.query(Mapping).filter(Mapping.endpoint_id == endpoint.id).all():
            db.delete(mapping)
        for event in db.query(AutomationEvent).filter(AutomationEvent.endpoint_id == endpoint.id).all():
            db.delete(event)
        db.delete(endpoint)
        db.commit()
    return RedirectResponse(url="/endpoints", status_code=303)


@app.get("/devices", response_class=HTMLResponse)
async def devices_view(request: Request, db: Session = Depends(get_db)):
    devices = db.query(Device).order_by(Device.created_at.desc()).all()
    for device in devices:
        device.channels = (
            db.query(DeviceChannel)
            .filter(DeviceChannel.device_id == device.id)
            .order_by(DeviceChannel.channel_index.asc())
            .all()
        )
    return templates.TemplateResponse("devices.html", {"request": request, "devices": devices})


@app.get("/devices/wizard", response_class=HTMLResponse)
async def device_scan_wizard(request: Request, db: Session = Depends(get_db)):
    discovered_devices = await TuyaService().discover()
    return templates.TemplateResponse(
        "device_wizard.html",
        {"request": request, "discovered_devices": discovered_devices},
    )


@app.post("/devices/scan", response_class=HTMLResponse)
async def scan_devices_form(request: Request, db: Session = Depends(get_db)):
    discovered_devices = await TuyaService().discover()
    return templates.TemplateResponse(
        "device_wizard.html",
        {"request": request, "discovered_devices": discovered_devices},
    )


@app.post("/devices")
async def create_device_form(
    name: str = Form(...),
    device_id: str = Form(...),
    ip_address: str = Form(""),
    device_type: str = Form("default"),
    protocol_version: str = Form("3.5"),
    encrypted_local_key: str = Form(...),
    channel_count: int = Form(1),
    db: Session = Depends(get_db),
):
    channel_count = max(1, min(int(channel_count), 8))
    device = Device(
        name=name,
        device_id=device_id,
        encrypted_local_key=encrypted_local_key,
        ip_address=ip_address or None,
        device_type=device_type,
        protocol_version=protocol_version,
        enabled=True,
    )
    db.add(device)
    db.commit()
    db.refresh(device)

    for index in range(1, channel_count + 1):
        db.add(
            DeviceChannel(
                device_id=device.id,
                channel_index=index,
                name=f"Channel {index}",
                dp_id=str(index),
                enabled=True,
            )
        )

    db.commit()
    return RedirectResponse(url="/devices", status_code=303)


@app.get("/mappings", response_class=HTMLResponse)
async def mappings_view(request: Request, db: Session = Depends(get_db)):
    mappings = db.query(Mapping).order_by(Mapping.created_at.desc()).all()
    devices = db.query(Device).all()
    endpoints = db.query(Endpoint).order_by(Endpoint.last_seen_at.desc().nullslast()).all()
    all_channels = (
        db.query(DeviceChannel)
        .order_by(DeviceChannel.device_id.asc(), DeviceChannel.channel_index.asc())
        .all()
    )
    error_message = request.query_params.get("error")

    mapped_rows = []
    for mapping in mappings:
        endpoint = db.query(Endpoint).filter(Endpoint.id == mapping.endpoint_id).first()
        device = db.query(Device).filter(Device.id == mapping.device_id).first()
        channel = db.query(DeviceChannel).filter(DeviceChannel.id == mapping.channel_id).first() if mapping.channel_id else None
        mapped_rows.append(
            {
                "id": mapping.id,
                "endpoint_name": endpoint.hostname if endpoint else mapping.endpoint_id,
                "device_name": device.name if device else mapping.device_id,
                "channel_name": channel.name if channel else "Default device state",
                "on_threshold": mapping.on_threshold,
                "off_threshold": mapping.off_threshold,
            }
        )

    return templates.TemplateResponse(
        "mappings.html",
        {
            "request": request,
            "mappings": mapped_rows,
            "devices": devices,
            "endpoints": endpoints,
            "channels": all_channels,
            "error_message": error_message,
        },
    )


@app.post("/mappings")
async def create_mapping_form(
    endpoint_id: str = Form(...),
    device_id: str = Form(...),
    channel_id: str | None = Form(None),
    on_threshold: int = Form(79),
    off_threshold: int = Form(99),
    minimum_state_change_interval: int = Form(300),
    db: Session = Depends(get_db),
):
    existing = db.query(Mapping).filter(Mapping.endpoint_id == endpoint_id, Mapping.device_id == device_id).first()
    if existing is not None:
        return RedirectResponse(url="/mappings?error=A+mapping+for+this+endpoint+and+switch+already+exists.", status_code=303)

    mapping = Mapping(
        endpoint_id=endpoint_id,
        device_id=device_id,
        channel_id=channel_id or None,
        enabled=True,
        on_threshold=on_threshold,
        off_threshold=off_threshold,
        minimum_state_change_interval=minimum_state_change_interval,
    )
    db.add(mapping)
    db.commit()
    return RedirectResponse(url="/mappings", status_code=303)


@app.post("/mappings/{mapping_id}/delete")
async def delete_mapping_form(mapping_id: str, db: Session = Depends(get_db)):
    mapping = db.query(Mapping).filter(Mapping.id == mapping_id).first()
    if mapping is not None:
        db.delete(mapping)
        db.commit()
    return RedirectResponse(url="/mappings", status_code=303)


@app.post("/devices/{device_id}/delete")
async def delete_device_form(device_id: str, db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.id == device_id).first()
    if device is not None:
        for mapping in db.query(Mapping).filter(Mapping.device_id == device.id).all():
            db.delete(mapping)
        for channel in db.query(DeviceChannel).filter(DeviceChannel.device_id == device.id).all():
            db.delete(channel)
        db.delete(device)
        db.commit()
    return RedirectResponse(url="/devices", status_code=303)


@app.post("/devices/{device_id}/turn-on")
async def turn_on_device_form(device_id: str, db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.id == device_id).first()
    if device is None:
        return RedirectResponse(url="/devices", status_code=303)

    previous_state = device.current_state
    channel = (
        db.query(DeviceChannel)
        .filter(DeviceChannel.device_id == device.id)
        .order_by(DeviceChannel.channel_index.asc())
        .first()
    )
    channel_index = channel.channel_index if channel else 1
    payload = await TuyaService.from_device(device).set_state(device.device_id, on=True, channel=channel_index)
    success = bool(payload.get("success", True))
    device.current_state = True
    device.last_state_change_at = datetime.now(UTC)
    device.updated_at = datetime.now(UTC)
    if channel is not None:
        channel.current_state = True
    db.add(
        AutomationEvent(
            event_type="MANUAL_ON",
            reason="Manual override via UI",
            endpoint_id=None,
            device_id=device.id,
            channel_id=channel.id if channel else None,
            previous_state=str(previous_state).lower(),
            new_state="true",
            success=success,
        )
    )
    db.commit()
    return RedirectResponse(url="/devices", status_code=303)


@app.post("/devices/{device_id}/turn-off")
async def turn_off_device_form(device_id: str, db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.id == device_id).first()
    if device is None:
        return RedirectResponse(url="/devices", status_code=303)

    previous_state = device.current_state
    channel = (
        db.query(DeviceChannel)
        .filter(DeviceChannel.device_id == device.id)
        .order_by(DeviceChannel.channel_index.asc())
        .first()
    )
    channel_index = channel.channel_index if channel else 1
    payload = await TuyaService.from_device(device).set_state(device.device_id, on=False, channel=channel_index)
    success = bool(payload.get("success", True))
    device.current_state = False
    device.last_state_change_at = datetime.now(UTC)
    device.updated_at = datetime.now(UTC)
    if channel is not None:
        channel.current_state = False
    db.add(
        AutomationEvent(
            event_type="MANUAL_OFF",
            reason="Manual override via UI",
            endpoint_id=None,
            device_id=device.id,
            channel_id=channel.id if channel else None,
            previous_state=str(previous_state).lower(),
            new_state="false",
            success=success,
        )
    )
    db.commit()
    return RedirectResponse(url="/devices", status_code=303)


@app.post("/devices/{device_id}/channels/{channel_id}/turn-on")
async def turn_on_device_channel_form(device_id: str, channel_id: str, db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.id == device_id).first()
    channel = db.query(DeviceChannel).filter(DeviceChannel.id == channel_id, DeviceChannel.device_id == device_id).first()
    if device is None or channel is None:
        return RedirectResponse(url="/devices", status_code=303)

    previous_state = channel.current_state
    payload = await TuyaService.from_device(device).set_state(device.device_id, on=True, channel=channel.channel_index)
    channel.current_state = True
    device.current_state = any(item.current_state for item in device.channels)
    device.last_state_change_at = datetime.now(UTC)
    device.updated_at = datetime.now(UTC)
    db.add(
        AutomationEvent(
            event_type="MANUAL_ON",
            reason=f"Manual override via UI for channel {channel.name}",
            endpoint_id=None,
            device_id=device.id,
            channel_id=channel.id,
            previous_state=str(previous_state).lower(),
            new_state="true",
            success=bool(payload.get("success", True)),
        )
    )
    db.commit()
    return RedirectResponse(url="/devices", status_code=303)


@app.post("/devices/{device_id}/channels/{channel_id}/turn-off")
async def turn_off_device_channel_form(device_id: str, channel_id: str, db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.id == device_id).first()
    channel = db.query(DeviceChannel).filter(DeviceChannel.id == channel_id, DeviceChannel.device_id == device_id).first()
    if device is None or channel is None:
        return RedirectResponse(url="/devices", status_code=303)

    previous_state = channel.current_state
    payload = await TuyaService.from_device(device).set_state(device.device_id, on=False, channel=channel.channel_index)
    channel.current_state = False
    device.current_state = any(item.current_state for item in device.channels)
    device.last_state_change_at = datetime.now(UTC)
    device.updated_at = datetime.now(UTC)
    db.add(
        AutomationEvent(
            event_type="MANUAL_OFF",
            reason=f"Manual override via UI for channel {channel.name}",
            endpoint_id=None,
            device_id=device.id,
            channel_id=channel.id,
            previous_state=str(previous_state).lower(),
            new_state="false",
            success=bool(payload.get("success", True)),
        )
    )
    db.commit()
    return RedirectResponse(url="/devices", status_code=303)


@app.get("/events", response_class=HTMLResponse)
async def events_view(request: Request, db: Session = Depends(get_db)):
    events = db.query(AutomationEvent).order_by(AutomationEvent.created_at.desc()).all()
    rows = []
    for event in events:
        endpoint = db.query(Endpoint).filter(Endpoint.id == event.endpoint_id).first()
        rows.append(
            {
                "created_at": event.created_at.isoformat() if event.created_at else "unknown",
                "event_type": event.event_type,
                "endpoint": endpoint.hostname if endpoint else (event.endpoint_id or "unknown"),
                "battery": event.previous_state if event.previous_state is not None else "n/a",
                "result": "Success" if event.success else "Failed",
            }
        )
    return templates.TemplateResponse("events.html", {"request": request, "rows": rows})
