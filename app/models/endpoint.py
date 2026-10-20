from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Endpoint(Base):
    __tablename__ = "endpoints"
    __table_args__ = (
        Index("ix_endpoints_tenant_hostname", "tenant_id", "hostname"),
        Index("ix_endpoints_hardware_uuid", "hardware_uuid", unique=True),
        Index("ix_endpoints_token_hash", "token_hash", unique=True),
        Index("ix_endpoints_installation_id", "installation_id", unique=True),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    tenant_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    hardware_uuid: Mapped[str | None] = mapped_column(String(36), nullable=True)
    installation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    platform: Mapped[str] = mapped_column(String(16), default="windows", server_default="windows")
    device_class: Mapped[str | None] = mapped_column(String(16), nullable=True)
    name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    hostname: Mapped[str] = mapped_column(String(160), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    battery_percentage: Mapped[int] = mapped_column(default=0)
    charging: Mapped[bool] = mapped_column(Boolean, default=False)
    ac_connected: Mapped[bool | None] = mapped_column(Boolean, default=False, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    agent_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    automation_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="TRUE")
    token_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
