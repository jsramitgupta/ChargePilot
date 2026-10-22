from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Device(Base):
    __tablename__ = "devices"
    __table_args__ = (
        Index(
            "ix_devices_meter_poll",
            "connector_id",
            "meter_last_sample_at",
            postgresql_where=text("enabled IS TRUE AND (power_dp_id IS NOT NULL OR energy_dp_id IS NOT NULL)"),
            sqlite_where=text("enabled IS TRUE AND (power_dp_id IS NOT NULL OR energy_dp_id IS NOT NULL)"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    tenant_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    connector_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("site_connectors.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    device_id: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    encrypted_local_key: Mapped[str] = mapped_column(String(512), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    device_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    protocol_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    current_state: Mapped[bool] = mapped_column(Boolean, default=False)
    last_state_change_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    power_dp_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    power_multiplier: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    energy_dp_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    energy_multiplier: Mapped[float] = mapped_column(Float, default=0.001, nullable=False)
    energy_counter_type: Mapped[str] = mapped_column(String(16), default="cumulative", nullable=False)
    meter_power_watts: Mapped[float | None] = mapped_column(Float, nullable=True)
    meter_power_sample_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    meter_energy_month_kwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    meter_energy_sample_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    meter_energy_total_kwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    meter_month_key: Mapped[str | None] = mapped_column(String(7), nullable=True)
    meter_last_sample_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    meter_poll_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    meter_tracking_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    channels: Mapped[list["DeviceChannel"]] = relationship(back_populates="device")


class DeviceChannel(Base):
    __tablename__ = "device_channels"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    device_id: Mapped[str] = mapped_column(String(36), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    channel_index: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    dp_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    current_state: Mapped[bool] = mapped_column(Boolean, default=False)

    device: Mapped[Device] = relationship(back_populates="channels")
