from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BatteryReading(Base):
    __tablename__ = "battery_readings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    endpoint_id: Mapped[str] = mapped_column(String(36), nullable=False)
    battery_percentage: Mapped[int] = mapped_column(Integer, nullable=False)
    charging: Mapped[bool] = mapped_column(default=False)
    ac_connected: Mapped[bool] = mapped_column(default=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
