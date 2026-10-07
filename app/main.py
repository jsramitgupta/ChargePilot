import secrets
import string
from datetime import UTC, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app.api.devices import router as devices_router
from app.api.endpoints import router as endpoints_router
from app.api.events import router as events_router
from app.api.health import router as health_router
from app.api.mappings import router as mappings_router
from app.api.telemetry import router as telemetry_router
from app.core.config import settings
from app.core.database import SessionLocal, create_db_and_tables, ensure_default_admin_user, get_db
from app.core.security import hash_password, verify_password
from app.models.device import Device, DeviceChannel
from app.models.endpoint import Endpoint
from app.models.event import AutomationEvent
from app.models.mapping import Mapping
from app.models.tenant import Tenant
from app.models.user import User
from app.services.smartlife_service import SmartLifeService
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
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)


def get_current_user(request: Request, db: Session) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        request.session.clear()
    return user


def require_user(request: Request, db: Session) -> User:
    user = get_current_user(request, db)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return user


def filter_by_user(query, user: User | None, owner_field: str = "owner_id"):
    if user is not None and not is_super_admin_user(user):
        model = query.column_descriptions[0]["entity"] if query.column_descriptions else None
        if model is not None and hasattr(model, "tenant_id"):
            if user.tenant_id is not None:
                return query.filter(model.tenant_id == user.tenant_id)
        if model is not None and hasattr(model, owner_field):
            return query.filter(getattr(model, owner_field) == user.id)
    return query


def generate_agent_token() -> str:
    return "".join(secrets.choice(string.ascii_letters) for _ in range(32))


def generate_unique_agent_token(db: Session | None = None) -> str:
    while True:
        token = generate_agent_token()
        if db is None:
            return token
        if db.query(Tenant).filter(Tenant.agent_token == token).first() is None:
            return token


def is_super_admin_user(user: User | None) -> bool:
    if user is None:
        return False
    if user.username == settings.admin_username:
        return True
    return user.role == "super_admin" or (user.is_admin and user.tenant_id is None)


def normalize_role(role: str | None) -> str:
    allowed = {"tenant_admin", "manager", "standard_user", "viewer"}
    value = (role or "standard_user").strip().lower()
    return value if value in allowed else "standard_user"


def is_role_admin(role: str | None) -> bool:
    return normalize_role(role) in {"tenant_admin", "manager"}


create_db_and_tables()
ensure_default_admin_user()


@app.on_event("startup")
async def startup_event() -> None:
    create_db_and_tables()
    ensure_default_admin_user()


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
    current_user = get_current_user(request, db)

    endpoints_query = db.query(Endpoint)
    if current_user is not None and not is_super_admin_user(current_user) and current_user.tenant_id is not None:
        endpoints_query = endpoints_query.filter(Endpoint.tenant_id == current_user.tenant_id)
    endpoints = endpoints_query.order_by(Endpoint.last_seen_at.desc().nullslast()).all()

    devices_query = db.query(Device)
    if current_user is not None and not is_super_admin_user(current_user) and current_user.tenant_id is not None:
        devices_query = devices_query.filter(Device.tenant_id == current_user.tenant_id)
    devices = devices_query.all()

    mappings_query = db.query(Mapping)
    if current_user is not None and not is_super_admin_user(current_user) and current_user.tenant_id is not None:
        mappings_query = mappings_query.filter(Mapping.tenant_id == current_user.tenant_id)
    mappings = mappings_query.all()

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
        power_state = "Charging" if endpoint.charging else ("On AC" if endpoint.ac_connected else "On battery")
        rows.append(
            {
                "hostname": endpoint.hostname,
                "battery": endpoint.battery_percentage,
                "charging": endpoint.charging,
                "ac_connected": endpoint.ac_connected,
                "power_state": power_state,
                "switch": switch_name,
                "switch_state": switch_state,
                "last_seen_iso": last_seen.isoformat() if last_seen else None,
                "last_seen": last_seen.strftime("%Y-%m-%d %H:%M:%S %Z") if last_seen else "never",
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
    current_user = get_current_user(request, db)

    endpoints_query = db.query(Endpoint)
    if current_user is not None and not is_super_admin_user(current_user) and current_user.tenant_id is not None:
        endpoints_query = endpoints_query.filter(Endpoint.tenant_id == current_user.tenant_id)
    endpoints = endpoints_query.order_by(Endpoint.last_seen_at.desc().nullslast()).all()
    rows = []
    for endpoint in endpoints:
        last_seen = _normalize_utc(endpoint.last_seen_at)
        power_state = "Charging" if endpoint.charging else ("On AC" if endpoint.ac_connected else "On battery")
        rows.append(
            {
                "id": endpoint.id,
                "hostname": endpoint.hostname,
                "ip_address": endpoint.ip_address or "unknown",
                "battery": endpoint.battery_percentage,
                "charging": endpoint.charging,
                "ac_connected": endpoint.ac_connected,
                "power_state": power_state,
                "last_seen": last_seen.isoformat() if last_seen else "never",
                "status": "online" if last_seen and (datetime.now(UTC) - last_seen).total_seconds() <= 600 else "offline",
            }
        )
    return templates.TemplateResponse("endpoints.html", {"request": request, "rows": rows})


@app.post("/endpoints/{endpoint_id}/delete")
async def delete_endpoint_form(request: Request, endpoint_id: str, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)

    endpoint = db.query(Endpoint).filter(Endpoint.id == endpoint_id).first()
    if endpoint is not None and current_user is not None and not is_super_admin_user(current_user):
        if endpoint.tenant_id != current_user.tenant_id:
            return RedirectResponse(url="/endpoints?error=You+cannot+delete+that+endpoint.", status_code=303)
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
    current_user = get_current_user(request, db)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    devices_query = db.query(Device)
    if not is_super_admin_user(current_user):
        devices_query = devices_query.filter(Device.tenant_id == current_user.tenant_id)
    devices = devices_query.order_by(Device.created_at.desc()).all()
    for device in devices:
        device.channels = (
            db.query(DeviceChannel)
            .filter(DeviceChannel.device_id == device.id)
            .order_by(DeviceChannel.channel_index.asc())
            .all()
        )

    smartlife_state = SmartLifeService.load_session()
    smartlife_error = request.session.pop("smartlife_error", None)
    return templates.TemplateResponse(
        "devices.html",
        {
            "request": request,
            "devices": devices,
            "smartlife_state": smartlife_state,
            "smartlife_error": smartlife_error,
        },
    )


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
    request: Request,
    name: str = Form(...),
    device_id: str = Form(...),
    ip_address: str = Form(""),
    device_type: str = Form("default"),
    protocol_version: str = Form("3.5"),
    encrypted_local_key: str = Form(...),
    channel_count: int = Form(1),
    db: Session = Depends(get_db),
):
    current_user = get_current_user(request, db)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)
    if current_user.tenant_id is None and not is_super_admin_user(current_user):
        return RedirectResponse(url="/devices?error=Your+account+is+not+assigned+to+a+tenant", status_code=303)
    channel_count = max(1, min(int(channel_count), 8))
    device = Device(
        owner_id=current_user.id,
        tenant_id=current_user.tenant_id,
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


@app.post("/devices/smartlife/login")
async def smartlife_login(request: Request, user_code: str = Form(...), db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    try:
        SmartLifeService.start_login(user_code)
    except ValueError as exc:
        request.session["smartlife_error"] = str(exc)
        return RedirectResponse(url="/devices", status_code=303)

    return RedirectResponse(url="/devices", status_code=303)


@app.post("/devices/smartlife/fetch")
async def smartlife_fetch(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    try:
        SmartLifeService.fetch_linked_devices()
    except (TimeoutError, ValueError) as exc:
        request.session["smartlife_error"] = str(exc)

    return RedirectResponse(url="/devices", status_code=303)


@app.get("/mappings", response_class=HTMLResponse)
async def mappings_view(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    mappings_query = db.query(Mapping)
    if not is_super_admin_user(current_user) and current_user.tenant_id is not None:
        mappings_query = mappings_query.filter(Mapping.tenant_id == current_user.tenant_id)
    mappings = mappings_query.order_by(Mapping.created_at.desc()).all()

    devices_query = db.query(Device)
    if not is_super_admin_user(current_user) and current_user.tenant_id is not None:
        devices_query = devices_query.filter(Device.tenant_id == current_user.tenant_id)
    devices = devices_query.all()

    endpoints_query = db.query(Endpoint)
    if not is_super_admin_user(current_user) and current_user.tenant_id is not None:
        endpoints_query = endpoints_query.filter(Endpoint.tenant_id == current_user.tenant_id)
    endpoints = endpoints_query.order_by(Endpoint.last_seen_at.desc().nullslast()).all()
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
    request: Request,
    endpoint_id: str = Form(...),
    device_id: str = Form(...),
    channel_id: str | None = Form(None),
    on_threshold: int = Form(79),
    off_threshold: int = Form(99),
    minimum_state_change_interval: int = Form(300),
    db: Session = Depends(get_db),
):
    current_user = get_current_user(request, db)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    endpoint = db.query(Endpoint).filter(Endpoint.id == endpoint_id).first()
    device = db.query(Device).filter(Device.id == device_id).first()
    if endpoint is None or device is None:
        return RedirectResponse(url="/mappings?error=Selected+endpoint+or+switch+was+not+found.", status_code=303)
    if not is_super_admin_user(current_user):
        if current_user.tenant_id is None or endpoint.tenant_id != current_user.tenant_id or device.tenant_id != current_user.tenant_id:
            return RedirectResponse(url="/mappings?error=You+can+only+map+switches+within+your+tenant.", status_code=303)

    existing = db.query(Mapping).filter(Mapping.endpoint_id == endpoint_id, Mapping.device_id == device_id).first()
    if existing is not None:
        return RedirectResponse(url="/mappings?error=A+mapping+for+this+endpoint+and+switch+already+exists.", status_code=303)

    mapping = Mapping(
        owner_id=current_user.id,
        tenant_id=current_user.tenant_id,
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
async def delete_mapping_form(request: Request, mapping_id: str, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    mapping = db.query(Mapping).filter(Mapping.id == mapping_id).first()
    if mapping is not None and current_user is not None and not is_super_admin_user(current_user):
        if mapping.tenant_id != current_user.tenant_id:
            return RedirectResponse(url="/mappings?error=You+cannot+delete+that+mapping.", status_code=303)
    if mapping is not None:
        db.delete(mapping)
        db.commit()
    return RedirectResponse(url="/mappings", status_code=303)


@app.post("/devices/{device_id}/delete")
async def delete_device_form(request: Request, device_id: str, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    device = db.query(Device).filter(Device.id == device_id).first()
    if device is not None and current_user is not None and not is_super_admin_user(current_user):
        if device.tenant_id != current_user.tenant_id:
            return RedirectResponse(url="/devices?error=You+cannot+delete+that+device.", status_code=303)
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
            battery_percentage=None,
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
            battery_percentage=None,
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
            battery_percentage=None,
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
            battery_percentage=None,
            previous_state=str(previous_state).lower(),
            new_state="false",
            success=bool(payload.get("success", True)),
        )
    )
    db.commit()
    return RedirectResponse(url="/devices", status_code=303)


@app.get("/events", response_class=HTMLResponse)
async def events_view(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if current_user is not None and not is_super_admin_user(current_user) and current_user.tenant_id is not None:
        endpoint_ids = [e.id for e in db.query(Endpoint).filter(Endpoint.tenant_id == current_user.tenant_id).all()]
        device_ids = [d.id for d in db.query(Device).filter(Device.tenant_id == current_user.tenant_id).all()]
        events_query = db.query(AutomationEvent).filter(
            (AutomationEvent.tenant_id == current_user.tenant_id)
            | (AutomationEvent.tenant_id.is_(None))
            | (AutomationEvent.endpoint_id.in_(endpoint_ids))
            | (AutomationEvent.device_id.in_(device_ids))
        )
    else:
        events_query = db.query(AutomationEvent)
    events = events_query.order_by(AutomationEvent.created_at.desc()).all()
    rows = []
    for event in events:
        endpoint = db.query(Endpoint).filter(Endpoint.id == event.endpoint_id).first()
        rows.append(
            {
                "created_at": event.created_at.isoformat() if event.created_at else "unknown",
                "created_at_display": event.created_at.strftime("%Y-%m-%d %H:%M:%S %Z") if event.created_at else "unknown",
                "event_type": event.event_type,
                "endpoint": endpoint.hostname if endpoint else (event.endpoint_id or "unknown"),
                "battery": f"{event.battery_percentage}%" if event.battery_percentage is not None else "n/a",
                "activity": event.reason or event.event_type,
                "result": "Success" if event.success else "Failed",
            }
        )
    return templates.TemplateResponse("events.html", {"request": request, "rows": rows})


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    message = request.query_params.get("message")
    tenant_token = request.query_params.get("tenant_token")
    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "error": request.query_params.get("error"),
            "message": message,
            "tenant_token": tenant_token,
        },
    )


@app.post("/login")
async def login_user(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username).first()
    if user is None or not verify_password(password, user.password_hash):
        return RedirectResponse(url="/login?error=Invalid+username+or+password", status_code=303)

    request.session["user_id"] = user.id
    return RedirectResponse(url="/", status_code=303)


@app.get("/logout")
async def logout_user(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
    tenant_token = tenant.agent_token if tenant else None
    return templates.TemplateResponse(
        "profile.html",
        {
            "request": request,
            "current_user": current_user,
            "tenant": tenant,
            "tenant_token": tenant_token,
            "role_label": current_user.role.replace("_", " ").title(),
            "message": request.query_params.get("message"),
            "error": request.query_params.get("error"),
        },
    )


@app.post("/tenant/rotate-agent-token")
async def rotate_tenant_agent_token(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)
    if not current_user.is_admin:
        return RedirectResponse(url="/profile?error=Only+tenant+admins+can+rotate+the+agent+token", status_code=303)

    tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
    if tenant is None:
        return RedirectResponse(url="/profile?error=Tenant+not+found", status_code=303)

    tenant.agent_token = generate_unique_agent_token(db)
    tenant.updated_at = datetime.now(UTC)
    db.commit()
    return RedirectResponse(url=f"/profile?message=Agent+token+rotated+successfully&tenant_token={tenant.agent_token}", status_code=303)


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, "error": request.query_params.get("error")})


@app.post("/register")
async def register_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    account_type: str = Form("standard"),
    tenant_name: str | None = Form(None),
    db: Session = Depends(get_db),
):
    username = username.strip()
    if not username or not password:
        return RedirectResponse(url="/register?error=Username+and+password+are+required", status_code=303)

    existing = db.query(User).filter(User.username == username).first()
    if existing is not None:
        return RedirectResponse(url="/register?error=User+already+exists", status_code=303)

    if account_type == "tenant":
        tenant_name = (tenant_name or f"{username}'s tenant").strip()
        tenant = Tenant(
            name=tenant_name,
            slug=f"tenant-{username.lower().replace(' ', '-')}-{__import__('uuid').uuid4().hex[:8]}",
            agent_token=generate_unique_agent_token(db),
            created_by_user_id=None,
        )
        db.add(tenant)
        db.commit()
        db.refresh(tenant)

        user = User(
            username=username,
            password_hash=hash_password(password),
            tenant_id=tenant.id,
            role="tenant_admin",
            is_admin=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        request.session["user_id"] = user.id
        return RedirectResponse(url=f"/login?message=Tenant+created+successfully&tenant_token={tenant.agent_token}", status_code=303)

    tenant = Tenant(
        name=f"{username}'s personal tenant",
        slug=f"personal-{username.lower().replace(' ', '-')}-{__import__('uuid').uuid4().hex[:8]}",
        agent_token=generate_unique_agent_token(db),
        created_by_user_id=None,
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    user = User(
        username=username,
        password_hash=hash_password(password),
        tenant_id=tenant.id,
        role="standard_user",
        is_admin=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    request.session["user_id"] = user.id
    return RedirectResponse(url="/", status_code=303)


@app.get("/tenants", response_class=HTMLResponse)
async def tenants_page(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)
    if not is_super_admin_user(current_user):
        return RedirectResponse(url="/", status_code=303)

    tenants = db.query(Tenant).order_by(Tenant.created_at.desc()).all()
    return templates.TemplateResponse(
        "tenants.html",
        {
            "request": request,
            "current_user": current_user,
            "tenants": tenants,
            "error": request.query_params.get("error"),
            "message": request.query_params.get("message"),
        },
    )


@app.post("/tenants")
async def create_tenant(
    request: Request,
    tenant_name: str = Form(...),
    db: Session = Depends(get_db),
):
    current_user = get_current_user(request, db)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)
    if not is_super_admin_user(current_user):
        return RedirectResponse(url="/", status_code=303)

    tenant_name = tenant_name.strip()
    if not tenant_name:
        return RedirectResponse(url="/tenants?error=Tenant+name+is+required", status_code=303)

    tenant = Tenant(
        name=tenant_name,
        slug=f"tenant-{tenant_name.lower().replace(' ', '-')}-{__import__('uuid').uuid4().hex[:8]}",
        agent_token=generate_unique_agent_token(db),
        created_by_user_id=current_user.id,
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return RedirectResponse(url="/tenants?message=Tenant+created+successfully", status_code=303)


@app.post("/tenants/{tenant_id}/delete")
async def delete_tenant(request: Request, tenant_id: str, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)
    if not is_super_admin_user(current_user):
        return RedirectResponse(url="/", status_code=303)

    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if tenant is None:
        return RedirectResponse(url="/tenants?error=Tenant+not+found", status_code=303)

    tenant_users = db.query(User).filter(User.tenant_id == tenant.id).all()
    for user in tenant_users:
        db.delete(user)

    tenant_endpoints = db.query(Endpoint).filter(Endpoint.tenant_id == tenant.id).all()
    for endpoint in tenant_endpoints:
        db.delete(endpoint)

    tenant_devices = db.query(Device).filter(Device.tenant_id == tenant.id).all()
    for device in tenant_devices:
        for mapping in db.query(Mapping).filter(Mapping.device_id == device.id).all():
            db.delete(mapping)
        for channel in db.query(DeviceChannel).filter(DeviceChannel.device_id == device.id).all():
            db.delete(channel)
        db.delete(device)

    for mapping in db.query(Mapping).filter(Mapping.tenant_id == tenant.id).all():
        db.delete(mapping)
    for event in db.query(AutomationEvent).filter(AutomationEvent.tenant_id == tenant.id).all():
        db.delete(event)

    db.delete(tenant)
    db.commit()
    return RedirectResponse(url="/tenants?message=Tenant+deleted+successfully", status_code=303)


@app.post("/tenants/{tenant_id}/rotate-agent-token")
async def rotate_tenant_agent_token_for_admin(request: Request, tenant_id: str, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)
    if not is_super_admin_user(current_user):
        return RedirectResponse(url="/", status_code=303)

    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if tenant is None:
        return RedirectResponse(url="/tenants?error=Tenant+not+found", status_code=303)

    tenant.agent_token = generate_unique_agent_token(db)
    tenant.updated_at = datetime.now(UTC)
    db.commit()
    return RedirectResponse(url=f"/tenants?message=Agent+token+rotated+successfully&tenant_token={tenant.agent_token}", status_code=303)


@app.get("/users", response_class=HTMLResponse)
async def users_page(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)
    if not (is_super_admin_user(current_user) or current_user.is_admin):
        return RedirectResponse(url="/", status_code=303)

    if is_super_admin_user(current_user):
        users = db.query(User).order_by(User.created_at.desc()).all()
    else:
        users = db.query(User).filter(User.tenant_id == current_user.tenant_id).order_by(User.created_at.desc()).all()
    return templates.TemplateResponse(
        "users.html",
        {
            "request": request,
            "current_user": current_user,
            "users": users,
            "roles": ["tenant_admin", "manager", "standard_user", "viewer"],
            "error": request.query_params.get("error"),
        },
    )


@app.post("/users")
async def create_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form("standard_user"),
    db: Session = Depends(get_db),
):
    current_user = get_current_user(request, db)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)
    if not (is_super_admin_user(current_user) or current_user.is_admin):
        return RedirectResponse(url="/", status_code=303)

    username = username.strip()
    role = normalize_role(role)
    if not username or not password:
        return RedirectResponse(url="/users?error=Username+and+password+are+required", status_code=303)

    if db.query(User).filter(User.username == username).first() is not None:
        return RedirectResponse(url="/users?error=User+already+exists", status_code=303)

    tenant_id = current_user.tenant_id if not is_super_admin_user(current_user) else None
    user = User(
        username=username,
        password_hash=hash_password(password),
        tenant_id=tenant_id,
        role=role,
        is_admin=is_role_admin(role),
    )
    db.add(user)
    db.commit()
    return RedirectResponse(url="/users", status_code=303)


@app.post("/users/{user_id}/role")
async def update_user_role(
    request: Request,
    user_id: str,
    role: str = Form(...),
    db: Session = Depends(get_db),
):
    current_user = get_current_user(request, db)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)
    if not (is_super_admin_user(current_user) or current_user.is_admin):
        return RedirectResponse(url="/", status_code=303)

    normalized_role = normalize_role(role)
    target = db.query(User).filter(User.id == user_id).first()
    if target is None:
        return RedirectResponse(url="/users?error=User+not+found", status_code=303)
    if not is_super_admin_user(current_user) and target.tenant_id != current_user.tenant_id:
        return RedirectResponse(url="/users?error=User+not+found", status_code=303)
    if target.id == current_user.id and normalized_role != "tenant_admin":
        return RedirectResponse(url="/users?error=You+cannot+remove+your+own+admin+role", status_code=303)

    target.role = normalized_role
    target.is_admin = is_role_admin(normalized_role)
    db.commit()
    return RedirectResponse(url="/users", status_code=303)


@app.post("/users/{user_id}/delete")
async def delete_user_form(
    request: Request,
    user_id: str,
    db: Session = Depends(get_db),
):
    current_user = get_current_user(request, db)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)
    if not (is_super_admin_user(current_user) or current_user.is_admin):
        return RedirectResponse(url="/", status_code=303)

    target = db.query(User).filter(User.id == user_id).first()
    if target is None:
        return RedirectResponse(url="/users?error=User+not+found", status_code=303)
    if not is_super_admin_user(current_user) and target.tenant_id != current_user.tenant_id:
        return RedirectResponse(url="/users?error=User+not+found", status_code=303)
    if target.id == current_user.id:
        return RedirectResponse(url="/users?error=You+cannot+delete+your+own+account", status_code=303)

    tenant_scope = target.tenant_id if target.tenant_id is not None else current_user.tenant_id
    if tenant_scope is not None:
        admin_count = db.query(User).filter(User.tenant_id == tenant_scope, User.is_admin.is_(True)).count()
        if target.is_admin and admin_count <= 1:
            return RedirectResponse(url="/users?error=At+least+one+admin+must+remain+for+this+tenant", status_code=303)

    db.delete(target)
    db.commit()
    return RedirectResponse(url="/users", status_code=303)
