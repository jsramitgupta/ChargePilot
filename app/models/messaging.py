from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TelemetryOutbox(Base):
    __tablename__ = "telemetry_outbox"
    __table_args__ = (
        Index("ix_telemetry_outbox_pending", "created_at"),
        Index("ix_telemetry_outbox_aggregate", "aggregate_key", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    aggregate_key: Mapped[str] = mapped_column(String(200), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class TelemetryAutomationCursor(Base):
    __tablename__ = "telemetry_automation_cursors"

    endpoint_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    last_event_id: Mapped[str] = mapped_column(String(36), nullable=False)
    last_telemetry_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
