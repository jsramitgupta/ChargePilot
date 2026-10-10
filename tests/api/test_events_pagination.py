from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.event import AutomationEvent


def test_events_page_supports_selectable_server_side_page_sizes():
    with SessionLocal() as db:
        now = datetime.now(UTC)
        db.add_all(
            [
                AutomationEvent(
                    event_type="PAGINATION_TEST",
                    reason=f"pagination-row-{index:03}",
                    created_at=now - timedelta(minutes=index),
                )
                for index in range(55)
            ]
        )
        db.commit()

    client = TestClient(app)
    register = client.post(
        "/register",
        data={"username": "events-pagination-user", "password": "secret123"},
        follow_redirects=False,
    )
    assert register.status_code == 303
    login = client.post(
        "/login",
        data={"username": "events-pagination-user", "password": "secret123"},
        follow_redirects=False,
    )
    assert login.status_code == 303

    first_page = client.get("/events?per_page=50")
    assert first_page.status_code == 200
    assert "Showing 1–50 of 55 events" in first_page.text
    assert 'value="500"' in first_page.text
    assert "500 lines" in first_page.text
    assert first_page.text.count("pagination-row-") == 50
    assert "pagination-row-000" in first_page.text
    assert "pagination-row-050" not in first_page.text
    assert 'href="/events?page=2&amp;per_page=50"' in first_page.text

    second_page = client.get("/events?page=2&per_page=50")
    assert second_page.status_code == 200
    assert "Showing 51–55 of 55 events" in second_page.text
    assert second_page.text.count("pagination-row-") == 5

    hundred_rows = client.get("/events?per_page=100")
    assert hundred_rows.status_code == 200
    assert "Showing 1–55 of 55 events" in hundred_rows.text
    assert hundred_rows.text.count("pagination-row-") == 55

    five_hundred_rows = client.get("/events?per_page=500")
    assert five_hundred_rows.status_code == 200
    assert "Showing 1–55 of 55 events" in five_hundred_rows.text
    assert five_hundred_rows.text.count("pagination-row-") == 55

    assert client.get("/events?per_page=25").status_code == 422
