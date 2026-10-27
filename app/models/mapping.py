from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Mapping(Base):
    __tablename__ = "mappings"
    __table_args__ = (
        UniqueConstraint("endpoint_id", "device_id", name="uq_mapping_endpoint_device"),
        CheckConstraint(
            "use_case IN ('battery_cycle', 'switch_off_only', 'switch_and_shutdown')",
            name="ck_mappings_use_case",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    tenant_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    endpoint_id: Mapped[str] = mapped_column(String(36), ForeignKey("endpoints.id", ondelete="CASCADE"), nullable=False)
    device_id: Mapped[str] = mapped_column(String(36), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    channel_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("device_channels.id", ondelete="SET NULL"), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    use_case: Mapped[str] = mapped_column(String(32), default="battery_cycle", server_default="battery_cycle")
    turn_on_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="TRUE")
    on_threshold: Mapped[int] = mapped_column(Integer, default=79)
    off_threshold: Mapped[int] = mapped_column(Integer, default=99)
    turn_off_when_charging_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="FALSE",
    )
    charging_off_threshold: Mapped[int] = mapped_column(Integer, default=99)
    minimum_state_change_interval: Mapped[int] = mapped_column(Integer, default=300)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
