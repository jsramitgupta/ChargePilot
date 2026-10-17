from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.event import AutomationEvent
from app.models.user import User
from conftest import register_tenant_admin


def test_events_page_supports_selectable_server_side_page_sizes():
    client = TestClient(app)
    register_tenant_admin(client, "events-pagination-user", "secret12345678")

    with SessionLocal() as db:
        user = db.query(User).filter(User.username == "events-pagination-user").one()
        now = datetime.now(UTC)
        db.add_all(
            [
                AutomationEvent(
                    tenant_id=user.tenant_id,
                    event_type="PAGINATION_TEST",
                    reason=f"pagination-row-{index:03}",
                    created_at=now - timedelta(minutes=index),
                )
                for index in range(55)
            ]
        )
        db.commit()

    assert client.get("/events", follow_redirects=False).status_code == 307

    api_first_page = client.get("/api/v1/events/page?per_page=50")
    assert api_first_page.status_code == 200
    assert api_first_page.json()["total_events"] == 55
    assert api_first_page.json()["page"] == 1
    assert len(api_first_page.json()["items"]) == 50
    assert api_first_page.json()["items"][0]["reason"] == "pagination-row-000"

    api_second_page = client.get("/api/v1/events/page?page=2&per_page=50")
    assert api_second_page.status_code == 200
    assert api_second_page.json()["first_row"] == 51
    assert api_second_page.json()["last_row"] == 55
    assert len(api_second_page.json()["items"]) == 5
    assert client.get("/api/v1/events/page?per_page=25").status_code == 422
