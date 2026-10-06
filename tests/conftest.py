import os

os.environ.setdefault("CHARGEPILOT_DATABASE_URL", "sqlite://")
os.environ.setdefault("CHARGEPILOT_ENVIRONMENT", "test")

import pytest

from app.core.database import Base, SessionLocal, engine
from app.models.device import Device, DeviceChannel
from app.models.endpoint import Endpoint
from app.models.event import AutomationEvent
from app.models.mapping import Mapping


@pytest.fixture(autouse=True)
def reset_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        for model in (AutomationEvent, Mapping, DeviceChannel, Endpoint, Device):
            db.query(model).delete()
        db.commit()
