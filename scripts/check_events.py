from app.core.database import SessionLocal
from app.models.event import AutomationEvent

s = SessionLocal()
try:
    total = s.query(AutomationEvent).count()
    print('automation_events count:', total)
    rows = s.query(AutomationEvent).order_by(AutomationEvent.created_at.desc()).limit(10).all()
    for r in rows:
        print(r.id, r.event_type, r.device_id, r.endpoint_id, getattr(r,'battery_percentage',None), r.success, r.created_at)
finally:
    s.close()
