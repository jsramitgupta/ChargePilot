from sqlalchemy import inspect
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import SessionLocal, engine
from app.main import app, generate_agent_token
from app.models.endpoint import Endpoint
from app.models.event import AutomationEvent
from app.models.telemetry import BatteryReading
from app.models.tenant import Tenant
from app.models.user import User
from conftest import api_login, register_tenant_admin, verify_registered_email


def _tenant_client(username: str) -> TestClient:
    client = TestClient(app)
    register_tenant_admin(client, username, "unit-test-password")
    return client


def test_user_registration_and_login_flow():
    client = TestClient(app)
    registered = client.post(
        "/api/v1/auth/register",
        json={
            "account_type": "tenant",
            "username": "alice",
            "password": "alice-test-password",
            "email": "alice@example.test",
            "turnstile_token": "test-turnstile-token",
            "tenant_name": "Alice Site",
        },
    )
    assert registered.status_code == 202, registered.text
    verified = verify_registered_email(client, registered, "alice@example.test")
    assert verified.json()["user"]["role"] == "tenant_admin"
    assert client.get("/api/v1/auth/me").json()["username"] == "alice"
    client.post("/api/v1/auth/logout")
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "alice-test-password"},
    ).status_code == 200


def test_legacy_ui_paths_redirect_to_react_without_server_rendered_forms():
    client = TestClient(app)
    for path in ("/", "/login", "/register?account_type=tenant", "/devices", "/mappings"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 307
        assert response.headers["location"].endswith(path)
        assert "<form" not in response.text
    assert client.post("/login", data={"username": "x", "password": "x"}).status_code == 405


def test_authenticated_api_and_legacy_navigation_redirect():
    client = _tenant_client("nav-user")
    assert client.get("/api/v1/auth/me").json()["username"] == "nav-user"
    for path in ("/", "/mappings", "/devices", "/endpoints", "/events", "/users", "/tenants"):
        assert client.get(path, follow_redirects=False).status_code == 307


def test_events_api_includes_battery_percentage():
    client = _tenant_client("events-user")
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == "events-user").one()
        db.add(
            AutomationEvent(
                tenant_id=user.tenant_id,
                event_type="TURN_ON",
                reason="battery reached rule threshold",
                battery_percentage=82,
                endpoint_id="ep-1",
                device_id="dev-1",
                success=True,
            )
        )
        db.commit()

    response = client.get("/api/v1/events/page")
    assert response.status_code == 200
    assert response.json()["items"][0]["battery"] == "82%"


def test_profile_timezone_is_persisted_for_user():
    client = _tenant_client("timezone-user")
    response = client.put("/api/v1/auth/profile", json={"timezone": "Europe/London"})
    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == "timezone-user").one()
        assert user.timezone == "Europe/London"


def test_invalid_timezone_is_rejected_and_user_stays_on_default():
    client = _tenant_client("invalid-timezone-user")
    response = client.put("/api/v1/auth/profile", json={"timezone": "Not/ARealZone"})
    assert response.status_code == 422
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == "invalid-timezone-user").one()
        assert user.timezone == "UTC"


def test_new_user_defaults_to_utc_timezone():
    _tenant_client("utc-user")
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == "utc-user").one()
        assert user.timezone == "UTC"


def test_endpoint_api_preserves_profile_timezone_and_power_state_data():
    client = _tenant_client("endpoint-timezone-user")
    assert client.put(
        "/api/v1/auth/profile",
        json={"timezone": "Asia/Kolkata"},
    ).status_code == 200
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == "endpoint-timezone-user").one()
        endpoint = Endpoint(
            hostname="timezone-check",
            hardware_uuid="a19f1d84-0a2c-4a34-bf95-a61ff3231c41",
            ip_address="10.0.0.11",
            tenant_id=user.tenant_id,
            battery_percentage=72,
            charging=False,
            ac_connected=True,
            enabled=True,
        )
        db.add(endpoint)
        db.commit()
    endpoints = client.get("/api/v1/endpoints")
    assert endpoints.status_code == 200
    assert endpoints.json()[0]["ac_connected"] is True
    assert endpoints.json()[0]["battery"] == 72


def test_tenant_admin_is_isolated_from_other_tenants():
    client_a = _tenant_client("tenant-a")
    client_b = _tenant_client("tenant-b")
    with SessionLocal() as db:
        tenant_a = db.query(User).filter(User.username == "tenant-a").one().tenant_id
        tenant_b = db.query(User).filter(User.username == "tenant-b").one().tenant_id
        db.add_all(
            [
                Endpoint(hostname="alpha-endpoint", tenant_id=tenant_a, battery_percentage=50),
                Endpoint(hostname="beta-endpoint", tenant_id=tenant_b, battery_percentage=90),
            ]
        )
        db.commit()

    endpoints_a = client_a.get("/api/v1/endpoints")
    assert endpoints_a.status_code == 200
    assert [endpoint["hostname"] for endpoint in endpoints_a.json()] == ["alpha-endpoint"]
    endpoints_b = client_b.get("/api/v1/endpoints")
    assert [endpoint["hostname"] for endpoint in endpoints_b.json()] == ["beta-endpoint"]


def test_super_admin_has_global_tenant_management():
    client = TestClient(app)
    api_login(client, settings.admin_username, settings.admin_password)
    tenants = client.get("/api/v1/admin/tenants")
    assert tenants.status_code == 200
    created = client.post("/api/v1/admin/tenants", json={"name": "Admin-created tenant"})
    assert created.status_code == 201, created.text
    assert created.json()["name"] == "Admin-created tenant"


def test_admin_can_rotate_tenant_agent_token():
    client = _tenant_client("token-rotation-admin")
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == "token-rotation-admin").one()
        tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).one()
        old_token = tenant.agent_token

    rotated = client.put("/api/v1/admin/tenant-agent-token")
    assert rotated.status_code == 200, rotated.text
    assert rotated.json()["agent_token"] != old_token
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == "token-rotation-admin").one()
        tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).one()
        assert tenant.agent_token == rotated.json()["agent_token"]
        assert len(tenant.agent_token) == 32
        assert tenant.agent_token.isalpha()


def test_generate_agent_token_has_valid_format_and_length():
    token = generate_agent_token()
    assert len(token) == 32
    assert token.isalpha()


def test_fresh_database_creates_all_model_tables():
    inspector = inspect(engine)
    assert inspector.has_table("battery_readings")
    assert inspector.has_table("devices")
    assert inspector.has_table("device_channels")
    assert inspector.has_table("endpoints")
    assert inspector.has_table("mappings")
    assert inspector.has_table("automation_events")
    assert inspector.has_table("tenants")
    assert inspector.has_table("tenant_invites")
    assert inspector.has_table("users")
    with SessionLocal() as db:
        assert db.query(BatteryReading).count() == 0
