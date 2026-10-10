from collections.abc import Generator
import secrets

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.security import hash_password


class Base(DeclarativeBase):
    pass


# Import all model modules so Base.metadata includes every table for fresh database creation.
from app.models.device import Device, DeviceChannel  # noqa: F401,E402
from app.models.endpoint import Endpoint  # noqa: F401,E402
from app.models.event import AutomationEvent  # noqa: F401,E402
from app.models.mapping import Mapping  # noqa: F401,E402
from app.models.telemetry import BatteryReading  # noqa: F401,E402
from app.models.tenant import Tenant  # noqa: F401,E402
from app.models.user import User  # noqa: F401,E402
from app.models.system_setting import SystemSetting  # noqa: F401,E402


engine_kwargs = {"pool_pre_ping": True}
if settings.database_url.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
    if settings.database_url == "sqlite://":
        engine_kwargs["poolclass"] = StaticPool

engine = create_engine(
    settings.database_url,
    **engine_kwargs,
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def _ensure_table_columns() -> None:
    inspector = inspect(engine)
    column_defs = {
        "devices": {
            "owner_id": "VARCHAR(36)",
            "tenant_id": "VARCHAR(36)",
            "current_state": "BOOLEAN NOT NULL DEFAULT FALSE",
            "last_state_change_at": "TIMESTAMPTZ",
            "last_seen_at": "TIMESTAMPTZ",
            "updated_at": "TIMESTAMPTZ NOT NULL DEFAULT NOW()",
        },
        "endpoints": {
            "owner_id": "VARCHAR(36)",
            "tenant_id": "VARCHAR(36)",
            "updated_at": "TIMESTAMPTZ NOT NULL DEFAULT NOW()",
        },
        "mappings": {
            "owner_id": "VARCHAR(36)",
            "tenant_id": "VARCHAR(36)",
            "updated_at": "TIMESTAMPTZ NOT NULL DEFAULT NOW()",
        },
        "automation_events": {
            "tenant_id": "VARCHAR(36)",
            "battery_percentage": "INTEGER",
        },
        "users": {
            "tenant_id": "VARCHAR(36)",
            "role": "VARCHAR(40) NOT NULL DEFAULT 'standard_user'",
            "timezone": "VARCHAR(64) NOT NULL DEFAULT 'UTC'",
            "smartlife_user_code": "VARCHAR(120)",
        },
        "device_channels": {
            "enabled": "BOOLEAN NOT NULL DEFAULT TRUE",
            "current_state": "BOOLEAN NOT NULL DEFAULT FALSE",
        },
    }

    for table_name, columns in column_defs.items():
        if not inspector.has_table(table_name):
            continue
        existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
        with engine.begin() as conn:
            for column_name, ddl in columns.items():
                if column_name in existing_columns:
                    continue
                conn.execute(text(f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {ddl}'))


def _ensure_cascade_foreign_keys() -> None:
    if not settings.database_url.startswith("postgresql"):
        return

    with engine.begin() as conn:
        conn.execute(text("""
            ALTER TABLE IF EXISTS mappings
                DROP CONSTRAINT IF EXISTS mappings_endpoint_id_fkey,
                DROP CONSTRAINT IF EXISTS mappings_device_id_fkey,
                DROP CONSTRAINT IF EXISTS mappings_channel_id_fkey;
        """))

        conn.execute(text("""
            ALTER TABLE IF EXISTS device_channels
                DROP CONSTRAINT IF EXISTS device_channels_device_id_fkey;
        """))

        conn.execute(text("""
            ALTER TABLE IF EXISTS mappings
                ADD CONSTRAINT mappings_endpoint_id_fkey
                    FOREIGN KEY (endpoint_id) REFERENCES endpoints(id) ON DELETE CASCADE,
                ADD CONSTRAINT mappings_device_id_fkey
                    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
                ADD CONSTRAINT mappings_channel_id_fkey
                    FOREIGN KEY (channel_id) REFERENCES device_channels(id) ON DELETE SET NULL;
        """))

        conn.execute(text("""
            ALTER TABLE IF EXISTS device_channels
                ADD CONSTRAINT device_channels_device_id_fkey
                    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE;
        """))


def _backfill_tenant_ownership() -> None:
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE devices
            SET tenant_id = (
                SELECT users.tenant_id
                FROM users
                WHERE users.id = devices.owner_id
            )
            WHERE tenant_id IS NULL
              AND owner_id IS NOT NULL
              AND EXISTS (
                  SELECT 1 FROM users
                  WHERE users.id = devices.owner_id
                    AND users.tenant_id IS NOT NULL
              )
        """))
        conn.execute(text("""
            UPDATE endpoints
            SET tenant_id = (
                SELECT users.tenant_id
                FROM users
                WHERE users.id = endpoints.owner_id
            )
            WHERE tenant_id IS NULL
              AND owner_id IS NOT NULL
              AND EXISTS (
                  SELECT 1 FROM users
                  WHERE users.id = endpoints.owner_id
                    AND users.tenant_id IS NOT NULL
              )
        """))
        conn.execute(text("""
            UPDATE mappings
            SET tenant_id = (
                SELECT endpoints.tenant_id
                FROM endpoints
                JOIN devices ON devices.id = mappings.device_id
                WHERE endpoints.id = mappings.endpoint_id
                  AND endpoints.tenant_id = devices.tenant_id
                  AND endpoints.tenant_id IS NOT NULL
            )
            WHERE tenant_id IS NULL
              AND EXISTS (
                  SELECT 1
                  FROM endpoints
                  JOIN devices ON devices.id = mappings.device_id
                  WHERE endpoints.id = mappings.endpoint_id
                    AND endpoints.tenant_id = devices.tenant_id
                    AND endpoints.tenant_id IS NOT NULL
              )
        """))
        conn.execute(text("""
            UPDATE automation_events
            SET tenant_id = CASE
                WHEN endpoint_id IS NOT NULL AND device_id IS NOT NULL THEN (
                    SELECT endpoints.tenant_id
                    FROM endpoints
                    JOIN devices ON devices.id = automation_events.device_id
                    WHERE endpoints.id = automation_events.endpoint_id
                      AND endpoints.tenant_id = devices.tenant_id
                      AND endpoints.tenant_id IS NOT NULL
                )
                WHEN endpoint_id IS NOT NULL THEN (
                    SELECT endpoints.tenant_id
                    FROM endpoints
                    WHERE endpoints.id = automation_events.endpoint_id
                      AND endpoints.tenant_id IS NOT NULL
                )
                WHEN device_id IS NOT NULL THEN (
                    SELECT devices.tenant_id
                    FROM devices
                    WHERE devices.id = automation_events.device_id
                      AND devices.tenant_id IS NOT NULL
                )
                ELSE NULL
            END
            WHERE tenant_id IS NULL
              AND (
                  EXISTS (
                      SELECT 1 FROM endpoints
                      WHERE endpoints.id = automation_events.endpoint_id
                        AND endpoints.tenant_id IS NOT NULL
                  )
                  OR EXISTS (
                      SELECT 1 FROM devices
                      WHERE devices.id = automation_events.device_id
                        AND devices.tenant_id IS NOT NULL
                  )
              )
        """))


def _ensure_tenant_indexes() -> None:
    with engine.begin() as conn:
        for table_name in ("users", "devices", "endpoints", "mappings", "automation_events"):
            conn.execute(
                text(
                    f'CREATE INDEX IF NOT EXISTS "ix_{table_name}_tenant_id" '
                    f'ON "{table_name}" ("tenant_id")'
                )
            )


def ensure_default_admin_user() -> None:
    with SessionLocal() as db:
        existing = db.query(User).filter(User.username == settings.admin_username).first()
        if existing is not None:
            existing.role = "super_admin"
            existing.is_admin = True
            existing.tenant_id = None
            db.commit()
            return

        db.add(
            User(
                username=settings.admin_username,
                password_hash=hash_password(settings.admin_password),
                tenant_id=None,
                role="super_admin",
                is_admin=True,
            )
        )
        db.commit()


def ensure_default_system_settings() -> None:
    with SessionLocal() as db:
        setting = db.query(SystemSetting).filter(SystemSetting.key == "global_agent_token").first()
        if setting is None:
            db.add(SystemSetting(key="global_agent_token", value=secrets.token_urlsafe(32)))
            db.commit()


def create_db_and_tables() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_table_columns()
    _backfill_tenant_ownership()
    _ensure_tenant_indexes()
    _ensure_cascade_foreign_keys()
    ensure_default_admin_user()
    ensure_default_system_settings()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
