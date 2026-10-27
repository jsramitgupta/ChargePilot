import asyncio
import logging
import re
import secrets
import string
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse, StreamingResponse
from starlette.background import BackgroundTask
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.connectors import router as connectors_router
from app.api.devices import router as devices_router
from app.api.endpoints import router as endpoints_router
from app.api.endpoint_commands import router as endpoint_commands_router
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
from app.services.event_retention import purge_expired_events, purge_expired_telemetry
from app.services.endpoint_shutdown_service import maintain_shutdown_commands

BASE_DIR = Path(__file__).resolve().parent
AGENT_RELEASE_API_URL = (
    "https://api.github.com/repos/jsramitgupta/ChargePilot/releases/latest"
)
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
    if settings.api_url:
        return settings.api_url.rstrip("/")
    if settings.frontend_url:
        return settings.frontend_url.rstrip("/")
    return str(request.base_url).rstrip("/")


async def event_retention_loop() -> None:
    while True:
        try:
            with SessionLocal() as db:
                deleted = purge_expired_events(db)
                if deleted:
                    logger.info("Purged %s automation events older than 30 days.", deleted)
                deleted_readings = purge_expired_telemetry(db)
                if deleted_readings:
                    logger.info("Purged %s telemetry readings older than 30 days.", deleted_readings)
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
                expired_shutdowns, purged_shutdowns = maintain_shutdown_commands(db)
                if expired_shutdowns or purged_shutdowns:
                    logger.info(
                        "Expired %s pending shutdown requests and purged %s requests older than 30 days.",
                        expired_shutdowns,
                        purged_shutdowns,
                    )
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
app.include_router(endpoint_commands_router, prefix=settings.api_v1_prefix)
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


@app.get(f"{settings.api_v1_prefix}/agent/releases/latest")
async def get_latest_agent_release(
    request: Request,
    response: Response,
):
    response.headers["Cache-Control"] = "public, max-age=300"
    release = await _get_latest_agent_release()
    version = release["tag_name"].removeprefix("agents-v")
    assets = []
    for asset in release["assets"]:
        if not isinstance(asset, dict):
            continue
        name = asset.get("name")
        if not isinstance(name, str) or not _is_supported_agent_asset(name, version):
            continue
        assets.append(
            {
                "name": name,
                "url": f"{_agent_server_url(request)}/agent/releases/latest/download/{name}",
            }
        )
    return {"tag": release["tag_name"], "assets": assets}


def _github_release_headers(accept: str) -> dict[str, str]:
    headers = {
        "Accept": accept,
        "User-Agent": "ChargePilotAgentSetup",
    }
    token = settings.agent_release_github_token.get_secret_value()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _is_supported_agent_asset(name: str, version: str) -> bool:
    return name in {
        "ChargePilotAgent.exe",
        f"ChargePilotAgent-{version}.dmg",
        f"ChargePilotAgent-{version}.ipa",
        f"ChargePilotAgent-{version}.apk",
    }


def _is_github_release_asset_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed_url = httpx.URL(value)
    except httpx.InvalidURL:
        return False
    return (
        parsed_url.scheme == "https"
        and parsed_url.host == "api.github.com"
        and re.fullmatch(
            r"/repos/jsramitgupta/ChargePilot/releases/assets/\d+",
            parsed_url.path,
        )
        is not None
    )


async def _get_latest_agent_release() -> dict:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            release_response = await client.get(
                AGENT_RELEASE_API_URL,
                headers=_github_release_headers("application/vnd.github+json"),
            )
    except httpx.RequestError as error:
        logger.warning("Could not reach GitHub while loading agent release assets: %s", error)
        raise HTTPException(
            status_code=502,
            detail="Could not reach the agent package service. Try again later.",
        ) from error

    if release_response.status_code != 200:
        logger.warning(
            "GitHub returned HTTP %s while loading agent release assets",
            release_response.status_code,
        )
        raise HTTPException(
            status_code=502,
            detail="The agent package service could not provide the latest packages. Try again later.",
        )

    try:
        release = release_response.json()
    except ValueError as error:
        raise HTTPException(
            status_code=502,
            detail="GitHub returned an unreadable agent release response.",
        ) from error

    if (
        not isinstance(release, dict)
        or not isinstance(release.get("tag_name"), str)
        or (
            tag_match := re.fullmatch(
                r"agents-v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)",
                release["tag_name"],
            )
        )
        is None
        or not isinstance(release.get("assets"), list)
    ):
        raise HTTPException(
            status_code=502,
            detail="GitHub returned an incomplete latest agent release.",
        )

    version = ".".join(tag_match.groups())
    release["assets"] = [
        asset
        for asset in release["assets"]
        if isinstance(asset, dict)
        and isinstance(asset.get("name"), str)
        and _is_supported_agent_asset(asset["name"], version)
        and _is_github_release_asset_url(asset.get("url"))
    ]
    return release


@app.get("/agent/download")
async def download_agent_scripts():
    raise HTTPException(
        status_code=410,
        detail="Agent source archives are no longer distributed by this service.",
    )


@app.get("/agent/ChargePilotAgent.exe", include_in_schema=False)
async def download_windows_agent_executable():
    return await _download_latest_agent_asset("ChargePilotAgent.exe")


@app.get("/agent/macos/download")
async def download_macos_agent():
    raise HTTPException(
        status_code=410,
        detail="Agent source archives are no longer distributed by this service.",
    )


async def _download_latest_agent_asset(asset_name: str) -> StreamingResponse:
    release = await _get_latest_agent_release()
    version = release["tag_name"].removeprefix("agents-v")
    if not _is_supported_agent_asset(asset_name, version):
        raise HTTPException(status_code=404, detail="Agent package not found.")
    asset = next(
        (item for item in release["assets"] if item.get("name") == asset_name),
        None,
    )
    if asset is None:
        raise HTTPException(status_code=404, detail="Agent package not found.")

    asset_url = asset.get("url")
    if not _is_github_release_asset_url(asset_url):
        raise HTTPException(status_code=502, detail="GitHub returned an invalid agent package URL.")

    client = httpx.AsyncClient(
        timeout=httpx.Timeout(10.0, read=60.0),
        follow_redirects=True,
    )
    try:
        github_response = await client.send(
            client.build_request(
                "GET",
                asset_url,
                headers=_github_release_headers("application/octet-stream"),
            ),
            stream=True,
        )
    except httpx.RequestError as error:
        await client.aclose()
        logger.warning("Could not download agent package %s from GitHub: %s", asset_name, error)
        raise HTTPException(
            status_code=502,
            detail="Could not download the agent package from GitHub.",
        ) from error

    if github_response.status_code != 200:
        status_code = github_response.status_code
        await github_response.aclose()
        await client.aclose()
        logger.warning(
            "GitHub returned HTTP %s while downloading agent package %s",
            status_code,
            asset_name,
        )
        raise HTTPException(
            status_code=502,
            detail="GitHub could not provide the requested agent package.",
        )

    async def close_github_stream() -> None:
        await github_response.aclose()
        await client.aclose()

    return StreamingResponse(
        github_response.aiter_bytes(),
        media_type="application/octet-stream",
        headers={
            "Cache-Control": "public, max-age=300",
            "Content-Disposition": f'attachment; filename="{asset_name}"',
        },
        background=BackgroundTask(close_github_stream),
    )


@app.get("/agent/releases/latest/download/{asset_name}", include_in_schema=False)
async def download_latest_agent_release_asset(asset_name: str):
    return await _download_latest_agent_asset(asset_name)


@app.get("/agent/android/download")
async def download_android_agent():
    raise HTTPException(
        status_code=410,
        detail="Agent source archives are no longer distributed by this service.",
    )


@app.get("/agent/ios/download")
async def download_ios_agent():
    raise HTTPException(
        status_code=410,
        detail="Agent source archives are no longer distributed by this service.",
    )


@app.get("/agent/install.ps1", include_in_schema=False)
async def download_agent_installer():
    installer_path = BASE_DIR.parent / "agent" / "windows" / "install.ps1"
    if not installer_path.is_file():
        raise HTTPException(status_code=500, detail="The ChargePilot agent installer is missing.")
    return PlainTextResponse(
        installer_path.read_text(encoding="utf-8"),
        media_type="text/plain",
        headers={"Cache-Control": "public, max-age=300"},
    )


@app.get("/agent/BatteryAgent.ps1", include_in_schema=False)
async def download_battery_agent():
    raise HTTPException(
        status_code=410,
        detail="The legacy PowerShell agent is no longer distributed by this service.",
    )


@app.get("/connectors/download")
async def download_site_connector():
    raise HTTPException(
        status_code=410,
        detail="Connector source archives are no longer distributed by this service.",
    )


@app.get("/connectors/install.sh", include_in_schema=False)
async def download_site_connector_installer():
    raise HTTPException(
        status_code=410,
        detail="The source-based Python connector installer is no longer available. Use the published Docker image.",
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
