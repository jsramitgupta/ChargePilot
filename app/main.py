import asyncio
import io
import logging
import secrets
import string
import zipfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse, StreamingResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.connectors import router as connectors_router
from app.api.devices import router as devices_router
from app.api.endpoints import router as endpoints_router
from app.api.endpoint_enrollment import router as endpoint_enrollment_router
from app.api.events import router as events_router
from app.api.health import router as health_router
from app.api.mappings import router as mappings_router
from app.api.onboarding import router as onboarding_router
from app.api.support import router as support_router
from app.api.telemetry import router as telemetry_router
from app.core.authorization import get_authenticated_user, is_super_admin_user
from app.core.config import settings
from app.core.database import SessionLocal, create_db_and_tables, get_db
from app.models.system_setting import SystemSetting
from app.models.tenant import Tenant
from app.models.user import User
from app.services.connector_service import expire_overdue_commands
from app.services.event_retention import purge_expired_events

BASE_DIR = Path(__file__).resolve().parent
logger = logging.getLogger("chargepilot.main")


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


@app.middleware("http")
async def secure_browser_requests(request: Request, call_next):
    origin = request.headers.get("origin")
    if (
        origin
        and request.method in {"POST", "PUT", "PATCH", "DELETE"}
        and settings.frontend_url
        and origin.rstrip("/") != settings.frontend_url.rstrip("/")
    ):
        response = JSONResponse(
            status_code=403,
            content={"detail": "Requests from this origin are not allowed."},
        )
    else:
        response = await call_next(request)

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), geolocation=(), microphone=()"
    if settings.environment.casefold() == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


def frontend_redirect(path: str, status_code: int = 307) -> RedirectResponse:
    target = f"{settings.frontend_url.rstrip('/')}{path}" if settings.frontend_url else path
    return RedirectResponse(url=target, status_code=status_code)


def generate_agent_token() -> str:
    return "".join(secrets.choice(string.ascii_letters) for _ in range(32))


def generate_unique_agent_token(db: Session | None = None) -> str:
    while True:
        token = generate_agent_token()
        if db is None or db.query(Tenant).filter(Tenant.agent_token == token).first() is None:
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


def _escape_powershell_expandable(value: str) -> str:
    return value.replace("`", "``").replace("$", "`$").replace('"', '`"')


def _agent_server_url(request: Request) -> str:
    return settings.api_url.rstrip("/") if settings.api_url else str(request.base_url).rstrip("/")


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


app.include_router(health_router)
app.include_router(telemetry_router, prefix=settings.api_v1_prefix)
app.include_router(auth_router, prefix=settings.api_v1_prefix)
app.include_router(admin_router, prefix=settings.api_v1_prefix)
app.include_router(connectors_router, prefix=settings.api_v1_prefix)
app.include_router(endpoints_router, prefix=settings.api_v1_prefix)
app.include_router(endpoint_enrollment_router, prefix=settings.api_v1_prefix)
app.include_router(devices_router, prefix=settings.api_v1_prefix)
app.include_router(onboarding_router)
app.include_router(mappings_router, prefix=settings.api_v1_prefix)
app.include_router(events_router, prefix=settings.api_v1_prefix)
app.include_router(support_router, prefix=settings.api_v1_prefix)


@app.get(f"{settings.api_v1_prefix}/agent/setup")
async def get_agent_setup(
    request: Request,
    response: Response,
    tenant_id: UUID | None = None,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    is_super_admin = is_super_admin_user(user)
    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first() if user.tenant_id else None
    if tenant_id is not None:
        if not is_super_admin:
            raise HTTPException(status_code=403, detail="Only the Super Admin can select another tenant.")
        tenant = db.query(Tenant).filter(Tenant.id == str(tenant_id)).first()
        if tenant is None:
            raise HTTPException(status_code=404, detail="Tenant not found.")
    if tenant is None and not is_super_admin:
        raise HTTPException(status_code=403, detail="An assigned tenant is required to configure the agent.")

    response.headers["Cache-Control"] = "private, no-store"
    server_url = _agent_server_url(request)
    install_url = f"{server_url}/agent/install.ps1"
    install_command = (
        'iex "& { $(irm '
        + _quote_powershell_literal(_escape_powershell_expandable(install_url))
        + ") } -ServerUrl "
        + _quote_powershell_literal(_escape_powershell_expandable(server_url))
        + " -AgentVersion '1.0.0'\""
    )
    return {
        "install_command": install_command,
        "is_super_admin": is_super_admin,
    }


@app.get("/agent/download")
async def download_agent_scripts():
    agent_dir = BASE_DIR.parent / "agent"
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
            "Cache-Control": "public, max-age=300",
        },
    )


@app.get("/agent/macos/download")
async def download_macos_agent():
    macos_agent_dir = BASE_DIR.parent / "agent" / "macos"
    archive = io.BytesIO()
    sources = (
        ("Package.swift", "chargepilot-macos-agent/Package.swift"),
        ("README.md", "chargepilot-macos-agent/README.md"),
        ("Sources/ChargePilotAgent/main.swift", "chargepilot-macos-agent/Sources/ChargePilotAgent/main.swift"),
    )
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for source, name in sources:
            source_path = macos_agent_dir / source
            if not source_path.is_file():
                raise HTTPException(
                    status_code=500,
                    detail=f"Required macOS agent source is missing: {source}",
                )
            bundle.write(source_path, arcname=name)
    archive.seek(0)
    return StreamingResponse(
        archive,
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="chargepilot-macos-agent.zip"',
            "Cache-Control": "public, max-age=300",
        },
    )


async def _download_native_agent(platform: str, archive_filename: str):
    agent_dir = BASE_DIR.parent / "agent" / platform
    archive = io.BytesIO()
    required_files = {
        "android": (
            "README.md",
            "settings.gradle.kts",
            "build.gradle.kts",
            "gradle.properties",
            "app/build.gradle.kts",
            "app/src/main/AndroidManifest.xml",
        ),
        "ios": (
            "README.md",
            "Info.plist",
            "ChargePilotAgent.xcodeproj/project.pbxproj",
            "ChargePilotAgent/ChargePilotAgentApp.swift",
        ),
    }
    sources = required_files.get(platform)
    if sources is None:
        raise HTTPException(status_code=404, detail="Native agent platform not found.")
    included_sources = set(sources)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for source in sources:
            source_path = agent_dir / source
            if not source_path.is_file():
                raise HTTPException(
                    status_code=500,
                    detail=f"Required {platform} agent source is missing: {source}",
                )
            bundle.write(source_path, arcname=f"chargepilot-{platform}-agent/{source}")
        source_root = agent_dir / "app/src/main/java" if platform == "android" else agent_dir / "ChargePilotAgent"
        for source_path in sorted(source_root.rglob("*")):
            if source_path.is_file():
                relative_path = source_path.relative_to(agent_dir)
                if relative_path.as_posix() in included_sources:
                    continue
                bundle.write(
                    source_path,
                    arcname=f"chargepilot-{platform}-agent/{relative_path.as_posix()}",
                )
    archive.seek(0)
    return StreamingResponse(
        archive,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{archive_filename}"',
            "Cache-Control": "public, max-age=300",
        },
    )


@app.get("/agent/android/download")
async def download_android_agent():
    return await _download_native_agent("android", "chargepilot-android-agent.zip")


@app.get("/agent/ios/download")
async def download_ios_agent():
    return await _download_native_agent("ios", "chargepilot-ios-agent.zip")


@app.get("/agent/install.ps1", include_in_schema=False)
async def download_agent_installer():
    script_path = BASE_DIR.parent / "agent" / "CreateAgentScheduledTask.ps1"
    if not script_path.is_file():
        raise HTTPException(status_code=500, detail="The agent installer script is missing.")
    return PlainTextResponse(
        script_path.read_text(encoding="utf-8"),
        headers={"Cache-Control": "public, max-age=300", "X-Content-Type-Options": "nosniff"},
    )


@app.get("/agent/BatteryAgent.ps1", include_in_schema=False)
async def download_battery_agent():
    script_path = BASE_DIR.parent / "agent" / "BatteryAgent.ps1"
    if not script_path.is_file():
        raise HTTPException(status_code=500, detail="The battery agent script is missing.")
    return PlainTextResponse(
        script_path.read_text(encoding="utf-8"),
        headers={"Cache-Control": "public, max-age=300", "X-Content-Type-Options": "nosniff"},
    )


@app.get("/connectors/download")
async def download_site_connector():
    archive = io.BytesIO()
    connector_dir = BASE_DIR.parent / "connector"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as package:
        for source, name in (
            ("__init__.py", "connector/__init__.py"),
            ("chargepilot_connector.py", "connector/chargepilot_connector.py"),
            ("requirements.txt", "requirements.txt"),
            ("Dockerfile", "connector/Dockerfile"),
            ("docker-compose.yml", "docker-compose.yml"),
            (".env.example", ".env.example"),
            ("install.sh", "install.sh"),
            ("README.md", "README.md"),
        ):
            package.write(connector_dir / source, name)
    archive.seek(0)
    return StreamingResponse(
        archive,
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="chargepilot-site-connector.zip"',
            "Cache-Control": "public, max-age=300",
        },
    )


@app.get("/connectors/install.sh", include_in_schema=False)
async def download_site_connector_installer(request: Request):
    script_path = BASE_DIR.parent / "connector" / "install.sh"
    if not script_path.is_file():
        raise HTTPException(status_code=500, detail="The site connector installer script is missing.")
    server_url = _agent_server_url(request)
    script = script_path.read_text(encoding="utf-8").replace("__CHARGEPILOT_SERVER_URL__", server_url)
    return PlainTextResponse(
        script,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@app.get("/logout", include_in_schema=False)
async def legacy_logout(request: Request):
    request.session.clear()
    return frontend_redirect("/login")


@app.get("/", include_in_schema=False)
@app.get("/login", include_in_schema=False)
@app.get("/register", include_in_schema=False)
@app.get("/endpoints", include_in_schema=False)
@app.get("/devices", include_in_schema=False)
@app.get("/mappings", include_in_schema=False)
@app.get("/connectors", include_in_schema=False)
@app.get("/events", include_in_schema=False)
@app.get("/profile", include_in_schema=False)
@app.get("/users", include_in_schema=False)
@app.get("/tenants", include_in_schema=False)
@app.get("/agent", include_in_schema=False)
@app.get("/account", include_in_schema=False)
@app.get("/agent/guide", include_in_schema=False)
async def legacy_frontend_route(request: Request):
    path = "/agent" if request.url.path == "/agent/guide" else request.url.path
    query = request.url.query
    return frontend_redirect(f"{path}?{query}" if query else path)
