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
from app.models.connector import SiteConnector, DeviceCommand  # noqa: F401,E402
from app.models.messaging import TelemetryAutomationCursor, TelemetryOutbox  # noqa: F401,E402
from app.models.tenant_invite import TenantInvite  # noqa: F401,E402
from app.models.account_invitation import AccountInvitation  # noqa: F401,E402
from app.models.email_verification import EmailVerification  # noqa: F401,E402
from app.models.endpoint_enrollment import EndpointEnrollment  # noqa: F401,E402
from app.models.endpoint_shutdown_command import EndpointShutdownCommand  # noqa: F401,E402
from app.services.local_key_service import decrypt_local_key, encrypt_local_key  # noqa: E402


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
            "connector_id": "VARCHAR(36)",
            "current_state": "BOOLEAN NOT NULL DEFAULT FALSE",
            "last_state_change_at": "TIMESTAMPTZ",
            "last_seen_at": "TIMESTAMPTZ",
            "power_dp_id": "VARCHAR(50)",
            "power_multiplier": "DOUBLE PRECISION NOT NULL DEFAULT 1.0",
            "energy_dp_id": "VARCHAR(50)",
            "energy_multiplier": "DOUBLE PRECISION NOT NULL DEFAULT 0.001",
            "energy_counter_type": "VARCHAR(16) NOT NULL DEFAULT 'cumulative'",
            "meter_power_watts": "DOUBLE PRECISION",
            "meter_power_sample_at": "TIMESTAMPTZ",
            "meter_energy_month_kwh": "DOUBLE PRECISION",
            "meter_energy_sample_at": "TIMESTAMPTZ",
            "meter_energy_total_kwh": "DOUBLE PRECISION",
            "meter_month_key": "VARCHAR(7)",
            "meter_last_sample_at": "TIMESTAMPTZ",
            "meter_poll_requested_at": "TIMESTAMPTZ",
            "meter_tracking_since": "TIMESTAMPTZ",
            "updated_at": "TIMESTAMPTZ NOT NULL DEFAULT NOW()",
        },
        "endpoints": {
            "owner_id": "VARCHAR(36)",
            "tenant_id": "VARCHAR(36)",
            "hardware_uuid": "VARCHAR(36)",
            "installation_id": "VARCHAR(36)",
            "platform": "VARCHAR(16) NOT NULL DEFAULT 'windows'",
            "device_class": "VARCHAR(16)",
            "updated_at": "TIMESTAMPTZ NOT NULL DEFAULT NOW()",
            "automation_enabled": "BOOLEAN NOT NULL DEFAULT TRUE",
        },
        "tenants": {
            "telemetry_interval_minutes": "INTEGER NOT NULL DEFAULT 5",
        },
        "battery_readings": {
            "system_metrics_json": "TEXT",
        },
        "mappings": {
            "owner_id": "VARCHAR(36)",
            "tenant_id": "VARCHAR(36)",
            "updated_at": "TIMESTAMPTZ NOT NULL DEFAULT NOW()",
            "use_case": "VARCHAR(32) NOT NULL DEFAULT 'battery_cycle'",
            "turn_on_enabled": "BOOLEAN NOT NULL DEFAULT TRUE",
            "turn_off_when_charging_enabled": "BOOLEAN NOT NULL DEFAULT FALSE",
            "charging_off_threshold": "INTEGER NOT NULL DEFAULT 99",
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
            "email": "VARCHAR(254)",
            "email_verified": "BOOLEAN NOT NULL DEFAULT TRUE",
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

    if inspector.has_table("users"):
        with engine.begin() as conn:
            conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email_unique "
                "ON users (email) WHERE email IS NOT NULL"
            ))
    if inspector.has_table("endpoints"):
        with engine.begin() as conn:
            conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_endpoints_token_hash "
                "ON endpoints (token_hash) WHERE token_hash IS NOT NULL"
            ))
            conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_endpoints_installation_id "
                "ON endpoints (installation_id) WHERE installation_id IS NOT NULL"
            ))
    if inspector.has_table("battery_readings"):
        with engine.begin() as conn:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_battery_readings_endpoint_timestamp "
                "ON battery_readings (endpoint_id, timestamp)"
            ))


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


def _ensure_endpoint_hardware_uuid_index() -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_endpoints_hardware_uuid "
                "ON endpoints (hardware_uuid)"
            )
        )


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
    lock_connection = None
    if engine.dialect.name == "postgresql":
        lock_connection = engine.connect()
        lock_connection.execute(text("SELECT pg_advisory_lock(731946120587)"))
        lock_connection.commit()

    try:
        Base.metadata.create_all(bind=lock_connection or engine)
        if lock_connection is not None:
            lock_connection.commit()
        _ensure_table_columns()
        _ensure_endpoint_hardware_uuid_index()
        with SessionLocal() as db:
            for device in db.query(Device).all():
                if not device.encrypted_local_key.startswith("gAAAA"):
                    device.encrypted_local_key = encrypt_local_key(device.encrypted_local_key)
                else:
                    decrypt_local_key(device.encrypted_local_key)
            db.commit()
        _backfill_tenant_ownership()
        _ensure_tenant_indexes()
        _ensure_cascade_foreign_keys()
        ensure_default_admin_user()
        ensure_default_system_settings()
    finally:
        if lock_connection is not None:
            lock_connection.rollback()
            lock_connection.execute(text("SELECT pg_advisory_unlock(731946120587)"))
            lock_connection.commit()
            lock_connection.close()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
