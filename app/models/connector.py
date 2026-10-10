from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SiteConnector(Base):
    __tablename__ = "site_connectors"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    enrollment_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    enrollment_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class DeviceCommand(Base):
    __tablename__ = "device_commands"
    __table_args__ = (
        Index("ix_device_commands_connector_status", "connector_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    connector_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("site_connectors.id", ondelete="CASCADE"), nullable=False
    )
    device_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("devices.id", ondelete="CASCADE"), nullable=True
    )
    channel_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    operation: Mapped[str] = mapped_column(String(24), nullable=False)
    desired_state: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    channel_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    context_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
