from fastapi.testclient import TestClient

from app.main import app
from app.models.endpoint import Endpoint
from app.models.event import AutomationEvent
from app.models.user import User
from app.core.database import SessionLocal
from app.main import generate_agent_token

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


def test_generate_agent_token_has_valid_format_and_length():
    token = generate_agent_token()
    assert len(token) == 32
    assert token.isalpha()
    assert all(character.isalpha() for character in token)


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
