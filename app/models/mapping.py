from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Mapping(Base):
    __tablename__ = "mappings"
    __table_args__ = (UniqueConstraint("endpoint_id", "device_id", name="uq_mapping_endpoint_device"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    tenant_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    endpoint_id: Mapped[str] = mapped_column(String(36), ForeignKey("endpoints.id", ondelete="CASCADE"), nullable=False)
    device_id: Mapped[str] = mapped_column(String(36), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    channel_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("device_channels.id", ondelete="SET NULL"), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    on_threshold: Mapped[int] = mapped_column(Integer, default=79)
    off_threshold: Mapped[int] = mapped_column(Integer, default=99)
    minimum_state_change_interval: Mapped[int] = mapped_column(Integer, default=300)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
