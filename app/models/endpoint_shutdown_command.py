from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class EndpointShutdownCommand(Base):
    __tablename__ = "endpoint_shutdown_commands"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'claimed', 'scheduled', 'cancelled', 'failed', 'expired')",
            name="ck_endpoint_shutdown_status",
        ),
        UniqueConstraint(
            "endpoint_id",
            "mapping_id",
            "automation_event_id",
            name="uq_endpoint_shutdown_event",
        ),
        Index("ix_endpoint_shutdown_pending", "endpoint_id", "status", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    endpoint_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("endpoints.id", ondelete="CASCADE"), nullable=False
    )
    mapping_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("mappings.id", ondelete="CASCADE"), nullable=False
    )
    automation_event_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
