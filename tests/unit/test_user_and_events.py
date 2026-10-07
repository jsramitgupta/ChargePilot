from fastapi.testclient import TestClient

from app.main import app
from app.models.endpoint import Endpoint
from app.models.event import AutomationEvent
from app.models.user import User
from app.core.database import SessionLocal

client = TestClient(app)


def test_user_registration_and_login_flow():
    response = client.post(
        "/register",
        data={"username": "alice", "password": "secret123"},
        follow_redirects=False,
    )
    assert response.status_code in (200, 302, 303)

    login = client.post(
        "/login",
        data={"username": "alice", "password": "secret123"},
        follow_redirects=False,
    )
    assert login.status_code in (200, 302, 303)


def test_events_include_battery_percentage():
    with SessionLocal() as db:
        db.add(
            AutomationEvent(
                event_type="TURN_ON",
                reason="battery 82% reached 79% rule",
                battery_percentage=82,
                endpoint_id="ep-1",
                device_id="dev-1",
                success=True,
            )
        )
        db.commit()

    register = client.post(
        "/register",
        data={"username": "bob", "password": "secret123"},
        follow_redirects=False,
    )
    assert register.status_code in (200, 302, 303)

    client.post(
        "/login",
        data={"username": "bob", "password": "secret123"},
        follow_redirects=False,
    )

    response = client.get("/events")
    assert response.status_code == 200
    content = response.text
    assert "82%" in content or "82" in content


def test_profile_page_shows_user_and_timezone_selector():
    register = client.post(
        "/register",
        data={"username": "charlie", "password": "secret123"},
        follow_redirects=False,
    )
    assert register.status_code in (200, 302, 303)

    client.post(
        "/login",
        data={"username": "charlie", "password": "secret123"},
        follow_redirects=False,
    )

    response = client.get("/profile")
    assert response.status_code == 200
    content = response.text
    assert "charlie" in content
    assert "Local time" in content
    assert "timezoneSelect" in content


def test_dashboard_renders_power_state_from_ac_connected():
    register = client.post(
        "/register",
        data={"username": "dana", "password": "secret123"},
        follow_redirects=False,
    )
    assert register.status_code in (200, 302, 303)

    login = client.post(
        "/login",
        data={"username": "dana", "password": "secret123"},
        follow_redirects=False,
    )
    assert login.status_code in (200, 302, 303)

    with SessionLocal() as db:
        user = db.query(User).filter(User.username == "dana").first()
        assert user is not None
        db.add(
            Endpoint(
                hostname="ac-test",
                ip_address="10.0.0.10",
                tenant_id=user.tenant_id,
                battery_percentage=91,
                charging=False,
                ac_connected=True,
                enabled=True,
            )
        )
        db.commit()

    response = client.get("/")
    assert response.status_code == 200
    content = response.text
    assert "On AC" in content
