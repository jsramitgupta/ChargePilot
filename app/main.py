import asyncio
import io
import logging
import secrets
import string
import zipfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app.api.devices import router as devices_router
from app.api.endpoints import router as endpoints_router
from app.api.events import router as events_router
from app.api.health import router as health_router
from app.api.mappings import router as mappings_router
from app.api.onboarding import router as onboarding_router
from app.api.telemetry import router as telemetry_router
from app.api.auth import router as auth_router
from app.api.connectors import router as connectors_router
from app.core.authorization import is_super_admin_user, tenant_scoped_query
from app.core.config import settings
from app.core.database import SessionLocal, create_db_and_tables, get_db
from app.core.security import hash_password, verify_password
from app.models.device import Device, DeviceChannel
from app.models.connector import DeviceCommand, SiteConnector
from app.models.endpoint import Endpoint
from app.models.event import AutomationEvent
from app.models.mapping import Mapping
from app.models.tenant import Tenant
from app.models.system_setting import SystemSetting
from app.models.user import User
from app.services.event_retention import purge_expired_events
from app.services.tuya_service import TuyaService
from app.services.connector_service import (
    connector_is_online,
    expire_overdue_commands,
    hash_connector_token,
    queue_device_command,
)
from app.services.local_key_service import encrypt_local_key

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
logger = logging.getLogger("chargepilot.events")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    create_db_and_tables()
    tasks = (
        asyncio.create_task(event_retention_loop()),
        asyncio.create_task(connector_maintenance_loop()),
    )
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Self-hosted battery automation platform for local Tuya control.",
    lifespan=lifespan,
)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    same_site=settings.session_cookie_samesite,
    https_only=settings.session_cookie_secure,
)
if settings.frontend_url:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_url.rstrip("/")],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
    )


def frontend_redirect(path: str, status_code: int = 303) -> RedirectResponse:
    target = f"{settings.frontend_url.rstrip('/')}{path}" if settings.frontend_url else path
    return RedirectResponse(url=target, status_code=status_code)


def get_current_user(request: Request, db: Session) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        request.session.clear()
        return None
    request.session["user_timezone"] = resolve_user_timezone(user)
    return user


def require_user(request: Request, db: Session) -> User:
    user = get_current_user(request, db)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return user


def generate_agent_token() -> str:
    return "".join(secrets.choice(string.ascii_letters) for _ in range(32))


def generate_unique_agent_token(db: Session | None = None) -> str:
    while True:
        token = generate_agent_token()
        if db is None:
            return token
        if db.query(Tenant).filter(Tenant.agent_token == token).first() is None:
            return token


def ensure_tenant_agent_token(tenant: Tenant, db: Session) -> str:
    if not tenant.agent_token:
        tenant.agent_token = generate_unique_agent_token(db)
        tenant.updated_at = datetime.now(UTC)
        db.commit()
    return tenant.agent_token


def get_global_agent_token(db: Session, create_if_missing: bool = False) -> str | None:
    setting = db.query(SystemSetting).filter(SystemSetting.key == "global_agent_token").first()
    if setting is None and create_if_missing:
        setting = SystemSetting(key="global_agent_token", value=secrets.token_urlsafe(32))
        db.add(setting)
        db.commit()
        db.refresh(setting)
    return setting.value if setting is not None else None


def _quote_powershell_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def normalize_role(role: str | None) -> str:
    allowed = {"tenant_admin", "manager", "standard_user", "viewer"}
    value = (role or "standard_user").strip().lower()
    return value if value in allowed else "standard_user"


def resolve_user_timezone(user: User | None) -> str:
    timezone_name = (getattr(user, "timezone", "") or "").strip()
    if timezone_name and timezone_name != "local":
        try:
            ZoneInfo(timezone_name)
            return timezone_name
        except ZoneInfoNotFoundError:
            pass
    return "UTC"


def get_timezone_options() -> list[str]:
    if hasattr(ZoneInfo, "available_timezones"):
        try:
            options = sorted(ZoneInfo.available_timezones())
            if options:
                return options
        except Exception:
            pass

    return sorted(
        {
            "UTC",
            "America/New_York",
            "America/Chicago",
            "America/Denver",
            "America/Los_Angeles",
            "Europe/London",
            "Europe/Paris",
            "Europe/Berlin",
            "Africa/Johannesburg",
            "Asia/Kolkata",
            "Asia/Singapore",
            "Asia/Tokyo",
            "Australia/Sydney",
        }
    )


def is_role_admin(role: str | None) -> bool:
    return normalize_role(role) in {"tenant_admin", "manager"}


async def event_retention_loop() -> None:
    while True:
        try:
            with SessionLocal() as db:
                deleted = purge_expired_events(db)
                if deleted:
                    logger.info("Purged %s automation events older than 30 days.", deleted)
        except SQLAlchemyError:
            logger.exception("Could not purge expired automation events.")
        await asyncio.sleep(24 * 60 * 60)


async def connector_maintenance_loop() -> None:
    while True:
        try:
            with SessionLocal() as db:
                expired = expire_overdue_commands(db)
                if expired:
                    logger.info("Expired %s uncompleted site connector commands.", expired)
        except SQLAlchemyError:
            logger.exception("Could not expire site connector commands.")
        await asyncio.sleep(30)


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.include_router(health_router)
app.include_router(telemetry_router, prefix=settings.api_v1_prefix)
app.include_router(auth_router, prefix=settings.api_v1_prefix)
app.include_router(connectors_router, prefix=settings.api_v1_prefix)
app.include_router(endpoints_router, prefix=settings.api_v1_prefix)
app.include_router(devices_router, prefix=settings.api_v1_prefix)
app.include_router(onboarding_router)
app.include_router(mappings_router, prefix=settings.api_v1_prefix)
app.include_router(events_router, prefix=settings.api_v1_prefix)


def _normalize_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _to_user_timezone(value: datetime | None, user: User | None) -> datetime | None:
    if value is None:
        return None
    normalized = _normalize_utc(value)
    if normalized is None:
        return None
    tz_name = resolve_user_timezone(user)
    try:
        zone = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("UTC")
    return normalized.astimezone(zone)


def _current_agent_tenant(request: Request, db: Session) -> tuple[User | None, Tenant | None]:
    current_user = get_current_user(request, db)
    if current_user is None:
        return None, None
    if current_user.tenant_id is None:
        return current_user, None
    return current_user, db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()


@app.get("/agent", response_class=HTMLResponse)
async def agent_setup_page(request: Request, db: Session = Depends(get_db)):
    current_user, tenant = _current_agent_tenant(request, db)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    is_super_admin = is_super_admin_user(current_user)
    global_token = get_global_agent_token(db, create_if_missing=True) if is_super_admin else None
    token = (
        ensure_tenant_agent_token(tenant, db)
        if tenant is not None
        else global_token
    )
    server_url = str(request.base_url).rstrip("/")
    install_command = ""
    if token:
        install_command = (
            "powershell.exe -NoProfile -ExecutionPolicy Bypass -File "
            + _quote_powershell_literal(".\\CreateAgentScheduledTask.ps1")
            + " -ServerUrl "
            + _quote_powershell_literal(server_url)
            + " -EndpointToken "
            + _quote_powershell_literal(token)
            + " -AgentVersion '1.0.0'"
        )
    return templates.TemplateResponse(
        "agent_setup.html",
        {
            "request": request,
            "current_user": current_user,
            "tenant": tenant,
            "tenant_token": token,
            "global_agent_token": global_token,
            "token_scope": "system-wide Super Admin token" if is_super_admin and tenant is None else "tenant",
            "is_super_admin": is_super_admin,
            "install_command": install_command,
            "message": request.query_params.get("message"),
            "error": request.query_params.get("error"),
        },
    )


@app.get("/agent/guide", response_class=HTMLResponse)
async def agent_setup_guide(request: Request, db: Session = Depends(get_db)):
    current_user, tenant = _current_agent_tenant(request, db)
    if current_user is None:
        raise HTTPException(status_code=401, detail="Authentication required.")

    is_super_admin = is_super_admin_user(current_user)
    global_token = get_global_agent_token(db, create_if_missing=True) if is_super_admin else None
    token = (
        ensure_tenant_agent_token(tenant, db)
        if tenant is not None
        else global_token
    )
    server_url = str(request.base_url).rstrip("/")
    install_command = ""
    if token:
        install_command = (
            "powershell.exe -NoProfile -ExecutionPolicy Bypass -File "
            + _quote_powershell_literal(".\\CreateAgentScheduledTask.ps1")
            + " -ServerUrl "
            + _quote_powershell_literal(server_url)
            + " -EndpointToken "
            + _quote_powershell_literal(token)
            + " -AgentVersion '1.0.0'"
        )
    return templates.TemplateResponse(
        "agent_setup_modal_content.html",
        {
            "request": request,
            "current_user": current_user,
            "tenant": tenant,
            "tenant_token": token,
            "global_agent_token": global_token,
            "token_scope": "system-wide Super Admin token" if is_super_admin and tenant is None else "tenant",
            "is_super_admin": is_super_admin,
            "install_command": install_command,
        },
    )


@app.get("/agent/download")
async def download_agent_scripts(request: Request, db: Session = Depends(get_db)):
    current_user, tenant = _current_agent_tenant(request, db)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)
    if tenant is None and not is_super_admin_user(current_user):
        raise HTTPException(status_code=403, detail="An assigned tenant is required to download the agent scripts.")

    if tenant is not None:
        ensure_tenant_agent_token(tenant, db)
    else:
        get_global_agent_token(db, create_if_missing=True)
    agent_dir = Path(__file__).resolve().parent.parent / "agent"
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for script_name in ("BatteryAgent.ps1", "CreateAgentScheduledTask.ps1"):
            script_path = agent_dir / script_name
            if not script_path.is_file():
                raise HTTPException(status_code=500, detail=f"Required agent script is missing: {script_name}")
            bundle.write(script_path, arcname=script_name)
    archive.seek(0)
    return StreamingResponse(
        archive,
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="chargepilot-agent-scripts.zip"',
            "Cache-Control": "private, no-store",
        },
    )


@app.post("/agent/global-token")
async def update_global_agent_token(
    request: Request,
    action: str = Form(...),
    token: str = Form(""),
    db: Session = Depends(get_db),
):
    current_user = get_current_user(request, db)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)
    if not is_super_admin_user(current_user):
        return RedirectResponse(url="/agent?error=Only+the+Super+Admin+can+change+the+system-wide+agent+token", status_code=303)

    setting = db.query(SystemSetting).filter(SystemSetting.key == "global_agent_token").first()
    if setting is None:
        setting = SystemSetting(key="global_agent_token", value="test-endpoint-token")
        db.add(setting)
        db.flush()

    if action == "regenerate":
        setting.value = generate_unique_agent_token(db)
    elif action == "save":
        updated_token = token.strip()
        if len(updated_token) < 16 or len(updated_token) > 512:
            return RedirectResponse(url="/agent?error=Agent+tokens+must+be+between+16+and+512+characters", status_code=303)
        tenant_conflict = db.query(Tenant).filter(Tenant.agent_token == updated_token).first()
        if tenant_conflict is not None:
            return RedirectResponse(url="/agent?error=That+token+is+already+assigned+to+a+tenant", status_code=303)
        setting.value = updated_token
    else:
        return RedirectResponse(url="/agent?error=Invalid+agent+token+action", status_code=303)

    db.commit()
    message = "System-wide+agent+token+regenerated+successfully" if action == "regenerate" else "System-wide+agent+token+updated+successfully"
    return RedirectResponse(url=f"/agent?message={message}", status_code=303)


def _is_ajax(request: Request) -> bool:
    # Accept X-Requested-With or Accept: application/json as AJAX indicators
    try:
        xrw = request.headers.get("x-requested-with", "").lower()
        accept = request.headers.get("accept", "")
        return xrw == "xmlhttprequest" or "application/json" in accept
    except Exception:
        return False


@app.get("/", response_class=HTMLResponse)
async def dashboard_view(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    endpoints_query = tenant_scoped_query(db.query(Endpoint), Endpoint, current_user)
    endpoints = endpoints_query.order_by(Endpoint.last_seen_at.desc().nullslast()).all()

    devices_query = tenant_scoped_query(db.query(Device), Device, current_user)
    devices = devices_query.all()

    mappings_query = tenant_scoped_query(db.query(Mapping), Mapping, current_user)
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
                    mapped_device = tenant_scoped_query(
                        db.query(Device), Device, current_user
                    ).filter(Device.id == mapping.device_id).first()
                    break
        switch_name = mapped_device.name if mapped_device else "No mapped switch"
        switch_state = "ON" if mapped_device and mapped_device.current_state else "OFF"
        last_seen = _to_user_timezone(endpoint.last_seen_at, current_user) if endpoint.last_seen_at else None
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
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    endpoints_query = tenant_scoped_query(db.query(Endpoint), Endpoint, current_user)
    endpoints = endpoints_query.order_by(Endpoint.last_seen_at.desc().nullslast()).all()
    rows = []
    for endpoint in endpoints:
        last_seen = _to_user_timezone(endpoint.last_seen_at, current_user)
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
                "last_seen": last_seen.strftime("%Y-%m-%d %H:%M:%S %Z") if last_seen else "never",
                "status": "online" if last_seen and (datetime.now(UTC) - _normalize_utc(endpoint.last_seen_at)).total_seconds() <= 600 else "offline",
            }
        )
    return templates.TemplateResponse("endpoints.html", {"request": request, "rows": rows})


@app.post("/endpoints/{endpoint_id}/delete")
async def delete_endpoint_form(request: Request, endpoint_id: str, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    endpoint = tenant_scoped_query(db.query(Endpoint), Endpoint, current_user).filter(
        Endpoint.id == endpoint_id
    ).first()
    if endpoint is None:
        return RedirectResponse(url="/endpoints?error=Endpoint+not+found", status_code=303)
    if endpoint is not None:
        for mapping in db.query(Mapping).filter(
            Mapping.endpoint_id == endpoint.id,
            Mapping.tenant_id == endpoint.tenant_id,
        ).all():
            db.delete(mapping)
        for event in db.query(AutomationEvent).filter(
            AutomationEvent.endpoint_id == endpoint.id,
            AutomationEvent.tenant_id == endpoint.tenant_id,
        ).all():
            db.delete(event)
        db.delete(endpoint)
        db.commit()
    if _is_ajax(request):
        return JSONResponse({"ok": True, "redirect": "/endpoints"})
    return RedirectResponse(url="/endpoints", status_code=303)


@app.get("/devices", response_class=HTMLResponse)
async def devices_view(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    devices_query = tenant_scoped_query(db.query(Device), Device, current_user)
    devices = devices_query.order_by(Device.created_at.desc()).all()
    for device in devices:
        device.channels = (
            db.query(DeviceChannel)
            .filter(DeviceChannel.device_id == device.id)
            .order_by(DeviceChannel.channel_index.asc())
            .all()
        )

    # compute total channels for template (avoid complex Jinja attribute expression)
    total_channels = sum(len(getattr(device, "channels", []) or []) for device in devices)
    connectors = tenant_scoped_query(db.query(SiteConnector), SiteConnector, current_user).order_by(
        SiteConnector.name.asc()
    ).all()
    for connector in connectors:
        connector.is_online = connector_is_online(connector)
    pending_commands = {
        command.device_id
        for command in tenant_scoped_query(db.query(DeviceCommand), DeviceCommand, current_user)
        .filter(DeviceCommand.status.in_(("queued", "leased")))
        .all()
        if command.device_id
    }

    # Clear Jinja2 template cache so filesystem edits are picked up in long-running test sessions
    try:
        templates.env.cache.clear()
    except Exception:
        pass

    return templates.TemplateResponse(
        "devices.html",
        {
            "request": request,
            "devices": devices,
            "total_channels": total_channels,
            "smartlife_user_code": current_user.smartlife_user_code or "",
            "connectors": connectors,
            "can_manage_connectors": is_super_admin_user(current_user)
            or current_user.role in {"tenant_admin", "manager"},
            "pending_device_commands": pending_commands,
            "message": request.query_params.get("message"),
            "error_message": request.query_params.get("error"),
        },
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
    if db.query(Device.id).filter(Device.device_id == device_id).first() is not None:
        return RedirectResponse(url="/devices?error=This+switch+has+already+been+added", status_code=303)
    device = Device(
        owner_id=current_user.id,
        tenant_id=current_user.tenant_id,
        name=name,
        device_id=device_id,
        encrypted_local_key=encrypt_local_key(encrypted_local_key),
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
    if _is_ajax(request):
        return JSONResponse({"ok": True, "redirect": "/devices"})
    return RedirectResponse(url="/devices", status_code=303)


@app.get("/mappings", response_class=HTMLResponse)
async def mappings_view(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    mappings_query = tenant_scoped_query(db.query(Mapping), Mapping, current_user)
    mappings = mappings_query.order_by(Mapping.created_at.desc()).all()

    devices_query = tenant_scoped_query(db.query(Device), Device, current_user)
    devices = devices_query.all()

    endpoints_query = tenant_scoped_query(db.query(Endpoint), Endpoint, current_user)
    endpoints = endpoints_query.order_by(Endpoint.last_seen_at.desc().nullslast()).all()
    device_ids = [device.id for device in devices]
    all_channels = db.query(DeviceChannel).filter(
        DeviceChannel.device_id.in_(device_ids)
    ).order_by(
        DeviceChannel.device_id.asc(), DeviceChannel.channel_index.asc()
    ).all() if device_ids else []
    error_message = request.query_params.get("error")

    mapped_rows = []
    for mapping in mappings:
        endpoint = endpoints_query.filter(Endpoint.id == mapping.endpoint_id).first()
        device = devices_query.filter(Device.id == mapping.device_id).first()
        channel = (
            db.query(DeviceChannel)
            .filter(DeviceChannel.id == mapping.channel_id, DeviceChannel.device_id == mapping.device_id)
            .first()
            if mapping.channel_id else None
        )
        mapped_rows.append(
            {
                "id": mapping.id,
                "endpoint_name": endpoint.hostname if endpoint else mapping.endpoint_id,
                "device_name": device.name if device else mapping.device_id,
                "channel_name": channel.name if channel else "Default device state",
                "on_threshold": mapping.on_threshold,
                "off_threshold": mapping.off_threshold,
                "minimum_state_change_interval": mapping.minimum_state_change_interval,
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

    endpoint = tenant_scoped_query(db.query(Endpoint), Endpoint, current_user).filter(
        Endpoint.id == endpoint_id
    ).first()
    device = tenant_scoped_query(db.query(Device), Device, current_user).filter(
        Device.id == device_id
    ).first()
    if endpoint is None or device is None or endpoint.tenant_id != device.tenant_id:
        return RedirectResponse(url="/mappings?error=Selected+endpoint+or+switch+was+not+found.", status_code=303)
    if channel_id:
        channel = db.query(DeviceChannel).filter(
            DeviceChannel.id == channel_id,
            DeviceChannel.device_id == device.id,
        ).first()
        if channel is None:
            return RedirectResponse(url="/mappings?error=Selected+channel+does+not+belong+to+this+switch.", status_code=303)

    existing = db.query(Mapping).filter(Mapping.endpoint_id == endpoint_id, Mapping.device_id == device_id).first()
    if existing is not None:
        return RedirectResponse(url="/mappings?error=A+mapping+for+this+endpoint+and+switch+already+exists.", status_code=303)

    mapping = Mapping(
        owner_id=current_user.id,
        tenant_id=endpoint.tenant_id,
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
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)
    mapping = tenant_scoped_query(db.query(Mapping), Mapping, current_user).filter(
        Mapping.id == mapping_id
    ).first()
    if mapping is None:
        return RedirectResponse(url="/mappings?error=Mapping+not+found", status_code=303)
    db.delete(mapping)
    db.commit()
    return RedirectResponse(url="/mappings", status_code=303)


@app.post("/devices/{device_id}/delete")
async def delete_device_form(request: Request, device_id: str, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)
    device = tenant_scoped_query(db.query(Device), Device, current_user).filter(
        Device.id == device_id
    ).first()
    if device is None:
        return RedirectResponse(url="/devices?error=Device+not+found", status_code=303)
    for mapping in db.query(Mapping).filter(
        Mapping.device_id == device.id,
        Mapping.tenant_id == device.tenant_id,
    ).all():
        db.delete(mapping)
    for channel in db.query(DeviceChannel).filter(DeviceChannel.device_id == device.id).all():
        db.delete(channel)
    db.delete(device)
    db.commit()
    return RedirectResponse(url="/devices", status_code=303)


@app.post("/devices/{device_id}/connector")
async def assign_device_connector(
    request: Request,
    device_id: str,
    connector_id: str = Form(""),
    db: Session = Depends(get_db),
):
    current_user = get_current_user(request, db)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)
    if not is_super_admin_user(current_user) and current_user.role not in {"tenant_admin", "manager"}:
        return RedirectResponse(url="/devices?error=Connector+assignment+requires+administrator+access", status_code=303)
    device = tenant_scoped_query(db.query(Device), Device, current_user).filter(
        Device.id == device_id
    ).first()
    if device is None:
        return RedirectResponse(url="/devices?error=Switch+not+found", status_code=303)
    if connector_id:
        connector = tenant_scoped_query(db.query(SiteConnector), SiteConnector, current_user).filter(
            SiteConnector.id == connector_id,
            SiteConnector.tenant_id == device.tenant_id,
            SiteConnector.is_active.is_(True),
            SiteConnector.token_hash.is_not(None),
        ).first()
        if connector is None:
            return RedirectResponse(url="/devices?error=Choose+an+active+connector+for+this+tenant", status_code=303)
        device.connector_id = connector.id
    else:
        device.connector_id = None
    db.commit()
    return RedirectResponse(url="/devices?message=Switch+connector+assignment+saved", status_code=303)


@app.get("/connectors", response_class=HTMLResponse)
async def connectors_view(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)
    if not is_super_admin_user(current_user) and current_user.role not in {"tenant_admin", "manager"}:
        raise HTTPException(status_code=403, detail="Connector administration permission required.")
    connectors = tenant_scoped_query(db.query(SiteConnector), SiteConnector, current_user).order_by(
        SiteConnector.created_at.desc()
    ).all()
    for connector in connectors:
        connector.is_online = connector_is_online(connector)
    tenants = db.query(Tenant).order_by(Tenant.name.asc()).all() if is_super_admin_user(current_user) else []
    enrollment_code = request.session.pop("connector_enrollment_code", None)
    return templates.TemplateResponse(
        "connectors.html",
        {
            "request": request,
            "connectors": connectors,
            "tenants": tenants,
            "current_user": current_user,
            "enrollment_code": enrollment_code,
            "message": request.query_params.get("message"),
            "error_message": request.query_params.get("error"),
        },
        headers={"Cache-Control": "private, no-store"} if enrollment_code else None,
    )


@app.get("/connectors/download")
async def download_site_connector(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)
    archive = io.BytesIO()
    connector_dir = BASE_DIR.parent / "connector"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.write(connector_dir / "__init__.py", "connector/__init__.py")
        package.write(connector_dir / "chargepilot_connector.py", "connector/chargepilot_connector.py")
        package.write(connector_dir / "requirements.txt", "requirements.txt")
        package.write(connector_dir / "Dockerfile", "connector/Dockerfile")
        package.write(connector_dir / "docker-compose.yml", "docker-compose.yml")
        package.write(connector_dir / ".env.example", ".env.example")
        package.write(connector_dir / "README.md", "README.md")
    archive.seek(0)
    return StreamingResponse(
        archive,
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="chargepilot-site-connector.zip"',
            "Cache-Control": "private, no-store",
        },
    )


@app.post("/connectors")
async def create_site_connector(
    request: Request,
    name: str = Form(...),
    tenant_id: str = Form(""),
    db: Session = Depends(get_db),
):
    current_user = get_current_user(request, db)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)
    if not is_super_admin_user(current_user) and current_user.role not in {"tenant_admin", "manager"}:
        raise HTTPException(status_code=403, detail="Connector administration permission required.")
    target_tenant_id = tenant_id if is_super_admin_user(current_user) else current_user.tenant_id
    if not target_tenant_id or db.query(Tenant.id).filter(Tenant.id == target_tenant_id).first() is None:
        return RedirectResponse(url="/connectors?error=Select+a+valid+tenant", status_code=303)
    connector_name = name.strip()
    if not connector_name:
        return RedirectResponse(url="/connectors?error=Connector+name+is+required", status_code=303)
    enrollment_code = secrets.token_urlsafe(32)
    connector = SiteConnector(
        tenant_id=target_tenant_id,
        name=connector_name,
        enrollment_token_hash=hash_connector_token(enrollment_code),
        enrollment_expires_at=datetime.now(UTC) + timedelta(minutes=15),
        is_active=True,
    )
    db.add(connector)
    db.commit()
    request.session["connector_enrollment_code"] = enrollment_code
    return RedirectResponse(url="/connectors", status_code=303)


@app.post("/connectors/{connector_id}/revoke")
async def revoke_site_connector(request: Request, connector_id: str, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)
    if not is_super_admin_user(current_user) and current_user.role not in {"tenant_admin", "manager"}:
        raise HTTPException(status_code=403, detail="Connector administration permission required.")
    connector = tenant_scoped_query(db.query(SiteConnector), SiteConnector, current_user).filter(
        SiteConnector.id == connector_id
    ).first()
    if connector is None:
        return RedirectResponse(url="/connectors?error=Connector+not+found", status_code=303)
    connector.is_active = False
    connector.token_hash = None
    connector.enrollment_token_hash = None
    connector.enrollment_expires_at = None
    db.query(Device).filter(Device.connector_id == connector.id).update(
        {Device.connector_id: None}, synchronize_session=False
    )
    db.commit()
    return RedirectResponse(url="/connectors?message=Connector+revoked", status_code=303)


@app.post("/connectors/{connector_id}/delete")
async def delete_site_connector(request: Request, connector_id: str, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)
    if not is_super_admin_user(current_user) and current_user.role not in {"tenant_admin", "manager"}:
        raise HTTPException(status_code=403, detail="Connector administration permission required.")
    connector = tenant_scoped_query(db.query(SiteConnector), SiteConnector, current_user).filter(
        SiteConnector.id == connector_id
    ).first()
    if connector is None:
        return RedirectResponse(url="/connectors?error=Connector+not+found", status_code=303)
    if connector.is_active:
        return RedirectResponse(url="/connectors?error=Revoke+the+connector+before+deleting+it", status_code=303)
    db.query(DeviceCommand).filter(DeviceCommand.connector_id == connector.id).delete(synchronize_session=False)
    db.delete(connector)
    db.commit()
    return RedirectResponse(url="/connectors?message=Connector+deleted", status_code=303)


async def _handle_manual_switch_control(
    db: Session,
    device: Device,
    *,
    desired_state: bool,
    channel: DeviceChannel | None,
) -> str:
    channel_index = channel.channel_index if channel is not None else 1
    previous_state = channel.current_state if channel is not None else device.current_state
    state_label = "ON" if desired_state else "OFF"
    reason = f"Manual override via UI for {channel.name}" if channel else "Manual override via UI"

    if device.connector_id:
        try:
            queue_device_command(
                db,
                device=device,
                operation="set_state",
                channel_index=channel_index,
                channel_id=channel.id if channel else None,
                desired_state=desired_state,
                context={
                    "event_type": f"MANUAL_{state_label}",
                    "reason": reason,
                    "previous_state": str(previous_state).lower(),
                    "new_state": str(desired_state).lower(),
                },
            )
            db.commit()
            return "queued"
        except ValueError as exc:
            db.rollback()
            logger.warning("Could not queue manual command for device %s: %s", device.id, exc)
            return "failed"

    result = await TuyaService.from_device(device).set_state(
        device.device_id,
        on=desired_state,
        channel=channel_index,
    )
    success = bool(result.get("success", False))
    if success:
        if channel is not None:
            channel.current_state = desired_state
            device.current_state = any(
                item.current_state
                for item in db.query(DeviceChannel).filter(DeviceChannel.device_id == device.id).all()
            )
        else:
            device.current_state = desired_state
        device.last_state_change_at = datetime.now(UTC)
        device.updated_at = datetime.now(UTC)
    db.add(
        AutomationEvent(
            tenant_id=device.tenant_id,
            event_type=f"MANUAL_{state_label}",
            reason=reason,
            device_id=device.id,
            channel_id=channel.id if channel else None,
            previous_state=str(previous_state).lower(),
            new_state=str(desired_state).lower(),
            success=success,
            error=None if success else str(result.get("error") or "Local device command failed.")[:255],
        )
    )
    db.commit()
    return "succeeded" if success else "failed"


@app.post("/devices/{device_id}/turn-on")
async def turn_on_device_form(request: Request, device_id: str, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)
    device = tenant_scoped_query(db.query(Device), Device, current_user).filter(
        Device.id == device_id
    ).first()
    if device is None:
        return RedirectResponse(url="/devices", status_code=303)

    channel = (
        db.query(DeviceChannel)
        .filter(DeviceChannel.device_id == device.id)
        .order_by(DeviceChannel.channel_index.asc())
        .first()
    )
    outcome = await _handle_manual_switch_control(db, device, desired_state=True, channel=channel)
    message = "Switch+command+queued" if outcome == "queued" else "Switch+turned+on" if outcome == "succeeded" else "Switch+command+failed"
    return RedirectResponse(url=f"/devices?message={message}", status_code=303)


@app.post("/devices/{device_id}/turn-off")
async def turn_off_device_form(request: Request, device_id: str, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)
    device = tenant_scoped_query(db.query(Device), Device, current_user).filter(
        Device.id == device_id
    ).first()
    if device is None:
        return RedirectResponse(url="/devices", status_code=303)

    channel = (
        db.query(DeviceChannel)
        .filter(DeviceChannel.device_id == device.id)
        .order_by(DeviceChannel.channel_index.asc())
        .first()
    )
    outcome = await _handle_manual_switch_control(db, device, desired_state=False, channel=channel)
    message = "Switch+command+queued" if outcome == "queued" else "Switch+turned+off" if outcome == "succeeded" else "Switch+command+failed"
    return RedirectResponse(url=f"/devices?message={message}", status_code=303)


@app.post("/devices/{device_id}/channels/{channel_id}/turn-on")
async def turn_on_device_channel_form(
    request: Request,
    device_id: str,
    channel_id: str,
    db: Session = Depends(get_db),
):
    current_user = get_current_user(request, db)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)
    device = tenant_scoped_query(db.query(Device), Device, current_user).filter(
        Device.id == device_id
    ).first()
    channel = db.query(DeviceChannel).filter(DeviceChannel.id == channel_id, DeviceChannel.device_id == device_id).first()
    if device is None or channel is None:
        return RedirectResponse(url="/devices", status_code=303)

    outcome = await _handle_manual_switch_control(db, device, desired_state=True, channel=channel)
    message = "Switch+command+queued" if outcome == "queued" else "Switch+turned+on" if outcome == "succeeded" else "Switch+command+failed"
    return RedirectResponse(url=f"/devices?message={message}", status_code=303)


@app.post("/devices/{device_id}/channels/{channel_id}/turn-off")
async def turn_off_device_channel_form(
    request: Request,
    device_id: str,
    channel_id: str,
    db: Session = Depends(get_db),
):
    current_user = get_current_user(request, db)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)
    device = tenant_scoped_query(db.query(Device), Device, current_user).filter(
        Device.id == device_id
    ).first()
    channel = db.query(DeviceChannel).filter(
        DeviceChannel.id == channel_id,
        DeviceChannel.device_id == device_id,
    ).first() if device is not None else None
    if device is None or channel is None:
        return RedirectResponse(url="/devices", status_code=303)

    outcome = await _handle_manual_switch_control(db, device, desired_state=False, channel=channel)
    message = "Switch+command+queued" if outcome == "queued" else "Switch+turned+off" if outcome == "succeeded" else "Switch+command+failed"
    return RedirectResponse(url=f"/devices?message={message}", status_code=303)


@app.get("/events", response_class=HTMLResponse)
async def events_view(
    request: Request,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, alias="per_page"),
    db: Session = Depends(get_db),
):
    if per_page not in {50, 100, 500}:
        raise HTTPException(status_code=422, detail="Page size must be 50, 100, or 500.")
    current_user = get_current_user(request, db)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)
    events_query = tenant_scoped_query(db.query(AutomationEvent), AutomationEvent, current_user)
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
        for endpoint in tenant_scoped_query(db.query(Endpoint), Endpoint, current_user)
        .filter(Endpoint.id.in_(endpoint_ids)).all()
    } if endpoint_ids else {}
    rows = []
    for event in events:
        endpoint = endpoints_by_id.get(event.endpoint_id)
        created_at = _to_user_timezone(event.created_at, current_user)
        rows.append(
            {
                "created_at": created_at.isoformat() if created_at else "unknown",
                "created_at_display": created_at.strftime("%Y-%m-%d %H:%M:%S %Z") if created_at else "unknown",
                "event_type": event.event_type,
                "endpoint": endpoint.hostname if endpoint else (event.endpoint_id or "unknown"),
                "battery": f"{event.battery_percentage}%" if event.battery_percentage is not None else "n/a",
                "activity": event.reason or event.event_type,
                "result": "Success" if event.success else "Failed",
            }
        )
    first_row = (page - 1) * per_page + 1 if total_events else 0
    last_row = min(page * per_page, total_events)
    return templates.TemplateResponse(
        "events.html",
        {
            "request": request,
            "rows": rows,
            "page": page,
            "per_page": per_page,
            "total_events": total_events,
            "total_pages": total_pages,
            "first_row": first_row,
            "last_row": last_row,
        },
    )


@app.get("/login")
async def login_page(request: Request):
    return frontend_redirect(f"/login{'?' + request.url.query if request.url.query else ''}")


@app.post("/login")
async def login_user(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username).first()
    if user is None or not verify_password(password, user.password_hash):
        return frontend_redirect("/login?error=Invalid+username+or+password")

    request.session["user_id"] = user.id
    request.session["user_timezone"] = resolve_user_timezone(user)
    return frontend_redirect("/")


@app.get("/logout")
async def logout_user(request: Request):
    request.session.clear()
    return frontend_redirect("/login")


@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
    timezone_options = get_timezone_options()
    request.session["user_timezone"] = resolve_user_timezone(current_user)
    return templates.TemplateResponse(
        "profile.html",
        {
            "request": request,
            "current_user": current_user,
            "tenant": tenant,
            "role_label": current_user.role.replace("_", " ").title(),
            "message": request.query_params.get("message"),
            "error": request.query_params.get("error"),
            "timezone_options": timezone_options,
        },
    )


@app.post("/profile/timezone")
async def update_profile_timezone(request: Request, timezone: str = Form(...), db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    normalized = (timezone or "").strip()
    if normalized and normalized != "local":
        try:
            ZoneInfo(normalized)
        except ZoneInfoNotFoundError:
            return RedirectResponse(url="/profile?error=Invalid+timezone+selected", status_code=303)

    current_user.timezone = normalized or "UTC"
    db.commit()
    request.session["user_timezone"] = resolve_user_timezone(current_user)
    return RedirectResponse(url="/profile?message=Timezone+updated+successfully", status_code=303)


@app.post("/tenant/rotate-agent-token")
async def rotate_tenant_agent_token(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)
    if not current_user.is_admin:
        return RedirectResponse(url="/agent?error=Only+tenant+admins+can+regenerate+the+agent+token", status_code=303)

    tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
    if tenant is None:
        return RedirectResponse(url="/agent?error=Tenant+not+found", status_code=303)

    tenant.agent_token = generate_unique_agent_token(db)
    tenant.updated_at = datetime.now(UTC)
    db.commit()
    return RedirectResponse(url="/agent?message=Agent+token+regenerated+successfully", status_code=303)


@app.get("/register")
async def register_page(request: Request):
    return frontend_redirect(f"/register{'?' + request.url.query if request.url.query else ''}")


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
        return frontend_redirect("/register?error=Username+and+password+are+required")

    existing = db.query(User).filter(User.username == username).first()
    if existing is not None:
        return frontend_redirect("/register?error=User+already+exists")

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
        request.session["user_timezone"] = resolve_user_timezone(user)
        return RedirectResponse(url="/agent?message=Tenant+created+successfully", status_code=303)

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
    request.session["user_timezone"] = resolve_user_timezone(user)
    return frontend_redirect("/")


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
    return RedirectResponse(url="/tenants?message=Agent+token+rotated+successfully", status_code=303)


@app.get("/users", response_class=HTMLResponse)
async def users_page(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)
    if not (is_super_admin_user(current_user) or (current_user.is_admin and current_user.tenant_id is not None)):
        return RedirectResponse(url="/", status_code=303)

    if is_super_admin_user(current_user):
        users = db.query(User).order_by(User.created_at.desc()).all()
    else:
        users = tenant_scoped_query(db.query(User), User, current_user).order_by(User.created_at.desc()).all()
    visible_tenants = (
        db.query(Tenant).order_by(Tenant.name.asc()).all()
        if is_super_admin_user(current_user)
        else db.query(Tenant).filter(Tenant.id == current_user.tenant_id).all()
    )
    tenant_names = {tenant.id: tenant.name for tenant in visible_tenants}
    return templates.TemplateResponse(
        "users.html",
        {
            "request": request,
            "current_user": current_user,
            "users": users,
            "roles": ["tenant_admin", "manager", "standard_user", "viewer"],
            "tenants": visible_tenants if is_super_admin_user(current_user) else [],
            "tenant_names": tenant_names,
            "is_super_admin": is_super_admin_user(current_user),
            "error": request.query_params.get("error"),
            "message": request.query_params.get("message"),
        },
    )


@app.post("/users")
async def create_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form("standard_user"),
    tenant_id: str | None = Form(None),
    db: Session = Depends(get_db),
):
    current_user = get_current_user(request, db)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)
    if not (is_super_admin_user(current_user) or (current_user.is_admin and current_user.tenant_id is not None)):
        return RedirectResponse(url="/", status_code=303)

    username = username.strip()
    role = normalize_role(role)
    if not username or not password:
        return RedirectResponse(url="/users?error=Username+and+password+are+required", status_code=303)

    if db.query(User).filter(User.username == username).first() is not None:
        return RedirectResponse(url="/users?error=User+already+exists", status_code=303)

    if is_super_admin_user(current_user):
        assigned_tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first() if tenant_id else None
        if assigned_tenant is None:
            return RedirectResponse(url="/users?error=Select+a+tenant+for+this+account", status_code=303)
        tenant_id = assigned_tenant.id
    else:
        tenant_id = current_user.tenant_id
        if tenant_id is None:
            return RedirectResponse(url="/users?error=Your+account+is+not+assigned+to+a+tenant", status_code=303)
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
    tenant_id: str | None = Form(None),
    db: Session = Depends(get_db),
):
    current_user = get_current_user(request, db)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)
    if not (is_super_admin_user(current_user) or (current_user.is_admin and current_user.tenant_id is not None)):
        return RedirectResponse(url="/", status_code=303)

    normalized_role = normalize_role(role)
    target = db.query(User).filter(User.id == user_id).first()
    if target is None:
        return RedirectResponse(url="/users?error=User+not+found", status_code=303)
    if is_super_admin_user(target):
        return RedirectResponse(url="/users?error=Super+admin+accounts+cannot+be+reassigned", status_code=303)
    if not is_super_admin_user(current_user) and target.tenant_id != current_user.tenant_id:
        return RedirectResponse(url="/users?error=User+not+found", status_code=303)
    if target.id == current_user.id and normalized_role != "tenant_admin":
        return RedirectResponse(url="/users?error=You+cannot+remove+your+own+admin+role", status_code=303)

    old_tenant_id = target.tenant_id
    if is_super_admin_user(current_user):
        assigned_tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first() if tenant_id else None
        if assigned_tenant is None:
            return RedirectResponse(url="/users?error=Select+a+tenant+for+this+account", status_code=303)
        new_tenant_id = assigned_tenant.id
    else:
        new_tenant_id = old_tenant_id

    new_is_admin = is_role_admin(normalized_role)
    if target.is_admin and old_tenant_id is not None and (
        old_tenant_id != new_tenant_id or not new_is_admin
    ):
        admin_count = db.query(User).filter(
            User.tenant_id == old_tenant_id,
            User.is_admin.is_(True),
        ).count()
        if admin_count <= 1:
            return RedirectResponse(
                url="/users?error=At+least+one+admin+must+remain+for+this+tenant",
                status_code=303,
            )

    target.role = normalized_role
    target.is_admin = new_is_admin
    target.tenant_id = new_tenant_id
    db.commit()
    return RedirectResponse(url="/users?message=User+updated+successfully", status_code=303)


@app.post("/users/{user_id}/delete")
async def delete_user_form(
    request: Request,
    user_id: str,
    db: Session = Depends(get_db),
):
    current_user = get_current_user(request, db)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)
    if not (is_super_admin_user(current_user) or (current_user.is_admin and current_user.tenant_id is not None)):
        return RedirectResponse(url="/", status_code=303)

    target = db.query(User).filter(User.id == user_id).first()
    if target is None:
        return RedirectResponse(url="/users?error=User+not+found", status_code=303)
    if is_super_admin_user(target):
        return RedirectResponse(url="/users?error=Super+admin+accounts+cannot+be+deleted", status_code=303)
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
