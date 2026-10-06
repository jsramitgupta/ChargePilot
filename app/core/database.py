from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings


class Base(DeclarativeBase):
    pass


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
            "current_state": "BOOLEAN NOT NULL DEFAULT FALSE",
            "last_state_change_at": "TIMESTAMPTZ",
            "last_seen_at": "TIMESTAMPTZ",
            "updated_at": "TIMESTAMPTZ NOT NULL DEFAULT NOW()",
        },
        "endpoints": {
            "updated_at": "TIMESTAMPTZ NOT NULL DEFAULT NOW()",
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


def create_db_and_tables() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_table_columns()
    _ensure_cascade_foreign_keys()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
