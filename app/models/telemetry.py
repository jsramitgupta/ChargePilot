from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BatteryReading(Base):
    __tablename__ = "battery_readings"
    __table_args__ = (Index("ix_battery_readings_endpoint_timestamp", "endpoint_id", "timestamp"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    endpoint_id: Mapped[str] = mapped_column(String(36), nullable=False)
    battery_percentage: Mapped[int] = mapped_column(Integer, nullable=False)
    charging: Mapped[bool] = mapped_column(default=False)
    ac_connected: Mapped[bool] = mapped_column(default=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    system_metrics_json: Mapped[str | None] = mapped_column(Text, nullable=True)
