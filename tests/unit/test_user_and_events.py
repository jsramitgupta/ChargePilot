from datetime import datetime, timezone

from sqlalchemy import inspect
from fastapi.testclient import TestClient

from app.core.database import SessionLocal, engine
from app.main import app, generate_agent_token
from app.models.endpoint import Endpoint
from app.models.event import AutomationEvent
from app.models.telemetry import BatteryReading
from app.models.user import User

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
    assert "timezoneSelect" in content


def test_profile_timezone_is_persisted_for_user():
    register = client.post(
        "/register",
        data={"username": "dave", "password": "secret123"},
        follow_redirects=False,
    )
    assert register.status_code in (200, 302, 303)

    login = client.post(
        "/login",
        data={"username": "dave", "password": "secret123"},
        follow_redirects=False,
    )
    assert login.status_code in (200, 302, 303)

    response = client.post(
        "/profile/timezone",
        data={"timezone": "Europe/London"},
        follow_redirects=False,
    )
    assert response.status_code in (200, 302, 303)

    with SessionLocal() as db:
        user = db.query(User).filter(User.username == "dave").first()
        assert user is not None
        assert user.timezone == "Europe/London"


def test_invalid_timezone_is_rejected_and_user_stays_on_default():
    register = client.post(
        "/register",
        data={"username": "frank", "password": "secret123"},
        follow_redirects=False,
    )
    assert register.status_code in (200, 302, 303)

    client.post(
        "/login",
        data={"username": "frank", "password": "secret123"},
        follow_redirects=False,
    )

    response = client.post(
        "/profile/timezone",
        data={"timezone": "Not/ARealZone"},
        follow_redirects=False,
    )
    assert response.status_code in (200, 302, 303)

    with SessionLocal() as db:
        user = db.query(User).filter(User.username == "frank").first()
        assert user is not None
        assert user.timezone == "UTC"


def test_new_user_defaults_to_utc_timezone():
    register = client.post(
        "/register",
        data={"username": "grace", "password": "secret123"},
        follow_redirects=False,
    )
    assert register.status_code in (200, 302, 303)

    with SessionLocal() as db:
        user = db.query(User).filter(User.username == "grace").first()
        assert user is not None
        assert user.timezone == "UTC"

    client.post(
        "/login",
        data={"username": "grace", "password": "secret123"},
        follow_redirects=False,
    )
    profile_response = client.get("/profile")
    assert profile_response.status_code == 200
    assert "timezoneSelect" in profile_response.text


def test_dashboard_uses_profile_timezone_for_server_rendered_timestamps():
    register = client.post(
        "/register",
        data={"username": "erin", "password": "secret123"},
        follow_redirects=False,
    )
    assert register.status_code in (200, 302, 303)

    login = client.post(
        "/login",
        data={"username": "erin", "password": "secret123"},
        follow_redirects=False,
    )
    assert login.status_code in (200, 302, 303)

    response = client.post(
        "/profile/timezone",
        data={"timezone": "Asia/Kolkata"},
        follow_redirects=False,
    )
    assert response.status_code in (200, 302, 303)

    with SessionLocal() as db:
        user = db.query(User).filter(User.username == "erin").first()
        assert user is not None
        db.add(
            Endpoint(
                hostname="timezone-check",
                ip_address="10.0.0.11",
                tenant_id=user.tenant_id,
                battery_percentage=72,
                charging=False,
                ac_connected=True,
                enabled=True,
                last_seen_at=datetime(2024, 1, 1, 8, 30, tzinfo=timezone.utc),
            )
        )
        db.commit()

    response = client.get("/")
    assert response.status_code == 200
    assert "2024-01-01 14:00:00 IST" in response.text or "2024-01-01T14:00:00+05:30" in response.text


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


def test_generate_agent_token_has_valid_format_and_length():
    token = generate_agent_token()
    assert len(token) == 32
    assert token.isalpha()
    assert all(character.isalpha() for character in token)


def test_fresh_database_creates_all_model_tables():
    inspector = inspect(engine)
    assert inspector.has_table("battery_readings")
    assert inspector.has_table("devices")
    assert inspector.has_table("device_channels")
    assert inspector.has_table("endpoints")
    assert inspector.has_table("mappings")
    assert inspector.has_table("automation_events")
    assert inspector.has_table("tenants")
    assert inspector.has_table("users")

    with SessionLocal() as db:
        assert db.query(BatteryReading).count() == 0


def test_tenant_admin_is_isolated_from_other_tenants():
    register = client.post(
        "/register",
        data={"username": "tenant_a", "password": "secret123", "account_type": "tenant", "tenant_name": "Tenant A"},
        follow_redirects=False,
    )
    assert register.status_code in (200, 302, 303)

    client.post(
        "/login",
        data={"username": "tenant_a", "password": "secret123"},
        follow_redirects=False,
    )

    with SessionLocal() as db:
        tenant_a = db.query(User).filter(User.username == "tenant_a").first()
        assert tenant_a is not None
        tenant_a_id = tenant_a.tenant_id
        db.add(Endpoint(hostname="alpha-endpoint", ip_address="10.0.0.10", tenant_id=tenant_a_id, battery_percentage=50, enabled=True))
        db.commit()

    register_b = client.post(
        "/register",
        data={"username": "tenant_b", "password": "secret123", "account_type": "tenant", "tenant_name": "Tenant B"},
        follow_redirects=False,
    )
    assert register_b.status_code in (200, 302, 303)

    client.post(
        "/login",
        data={"username": "tenant_b", "password": "secret123"},
        follow_redirects=False,
    )

    with SessionLocal() as db:
        tenant_b = db.query(User).filter(User.username == "tenant_b").first()
        assert tenant_b is not None
        tenant_b_id = tenant_b.tenant_id
        db.add(Endpoint(hostname="beta-endpoint", ip_address="10.0.0.11", tenant_id=tenant_b_id, battery_percentage=90, enabled=True))
        db.commit()

    client.post(
        "/login",
        data={"username": "tenant_a", "password": "secret123"},
        follow_redirects=False,
    )

    response = client.get("/endpoints")
    assert response.status_code == 200
    body = response.text
    assert "alpha-endpoint" in body
    assert "beta-endpoint" not in body


def test_super_admin_has_global_tenant_management():
    with SessionLocal() as db:
        admin = db.query(User).filter(User.username == "admin").first()
        assert admin is not None
        assert admin.is_admin is True

    login = client.post(
        "/login",
        data={"username": "admin", "password": "change-me"},
        follow_redirects=False,
    )
    assert login.status_code in (200, 302, 303)

    response = client.get("/tenants")
    assert response.status_code == 200


def test_admin_can_rotate_tenant_agent_token():
    register = client.post(
        "/register",
        data={"username": "erin", "password": "secret123", "account_type": "tenant", "tenant_name": "Erin Co"},
        follow_redirects=False,
    )
    assert register.status_code in (200, 302, 303)

    login = client.post(
        "/login",
        data={"username": "erin", "password": "secret123"},
        follow_redirects=False,
    )
    assert login.status_code in (200, 302, 303)

    with SessionLocal() as db:
        user = db.query(User).filter(User.username == "erin").first()
        assert user is not None
        assert user.tenant_id is not None
        original = user.tenant_id
        tenant = db.query(__import__('app.models.tenant', fromlist=['Tenant']).Tenant).filter_by(id=original).first()
        assert tenant is not None
        old_token = tenant.agent_token

    rotate = client.post("/tenant/rotate-agent-token", follow_redirects=False)
    assert rotate.status_code in (200, 302, 303)

    with SessionLocal() as db:
        user = db.query(User).filter(User.username == "erin").first()
        assert user is not None
        tenant = db.query(__import__('app.models.tenant', fromlist=['Tenant']).Tenant).filter_by(id=user.tenant_id).first()
        assert tenant is not None
        assert tenant.agent_token != old_token
        assert len(tenant.agent_token) == 32
        assert tenant.agent_token.isalpha()
