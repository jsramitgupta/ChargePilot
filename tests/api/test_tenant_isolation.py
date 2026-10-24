from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.database import SessionLocal, _backfill_tenant_ownership
from app.core.security import hash_password
from app.main import app, generate_unique_agent_token
from app.models.device import Device
from app.models.endpoint import Endpoint
from app.models.event import AutomationEvent
from app.models.mapping import Mapping
from app.models.tenant import Tenant
from app.models.user import User
from conftest import api_login


def _login(username: str, password: str = "tenant-password") -> TestClient:
    client = TestClient(app)
    api_login(client, username, password)
    return client


def _create_tenant_account(db, label: str) -> tuple[Tenant, User]:
    suffix = uuid4().hex[:10]
    tenant = Tenant(
        name=f"{label} tenant",
        slug=f"{label.lower()}-{suffix}",
        agent_token=generate_unique_agent_token(db),
    )
    db.add(tenant)
    db.flush()
    user = User(
        username=f"{label.lower()}-{suffix}",
        password_hash=hash_password("tenant-password"),
        tenant_id=tenant.id,
        role="tenant_admin",
        is_admin=True,
    )
    db.add(user)
    db.flush()
    return tenant, user


def test_super_admin_can_assign_new_admin_to_a_tenant():
    client = _login("admin", "change-me")
    tenant_name = f"Assigned tenant {uuid4().hex[:8]}"
    created_tenant = client.post("/api/v1/admin/tenants", json={"name": tenant_name})
    assert created_tenant.status_code == 201, created_tenant.text

    username = f"assigned-admin-{uuid4().hex[:8]}"
    with SessionLocal() as db:
        tenant_id = created_tenant.json()["id"]

    created_user = client.post(
        "/api/v1/admin/users",
        json={
            "username": username,
            "password": "tenant-password",
            "role": "tenant_admin",
            "tenant_id": tenant_id,
        },
    )
    assert created_user.status_code == 201, created_user.text

    with SessionLocal() as db:
        user = db.query(User).filter(User.username == username).one()
        assert user.tenant_id == tenant_id
        assert user.role == "tenant_admin"
        assert user.is_admin is True

    users = client.get("/api/v1/admin/users")
    assert username in [account["username"] for account in users.json()]
    assert client.get("/users", follow_redirects=False).status_code == 307


def test_tenant_admin_cannot_read_or_mutate_another_tenants_resources():
    with SessionLocal() as db:
        tenant_a, user_a = _create_tenant_account(db, "alpha")
        tenant_b, user_b = _create_tenant_account(db, "bravo")

        endpoint_a = Endpoint(hostname="alpha-endpoint", tenant_id=tenant_a.id)
        endpoint_b = Endpoint(hostname="bravo-endpoint", tenant_id=tenant_b.id)
        device_a = Device(
            owner_id=user_a.id,
            tenant_id=tenant_a.id,
            name="Alpha device",
            device_id="alpha-device",
            encrypted_local_key="alpha-key",
        )
        device_b = Device(
            owner_id=user_b.id,
            tenant_id=tenant_b.id,
            name="Bravo device",
            device_id="bravo-device",
            encrypted_local_key="bravo-key",
        )
        db.add_all([endpoint_a, endpoint_b, device_a, device_b])
        db.flush()
        mapping_a = Mapping(
            owner_id=user_a.id,
            tenant_id=tenant_a.id,
            endpoint_id=endpoint_a.id,
            device_id=device_a.id,
        )
        mapping_b = Mapping(
            owner_id=user_b.id,
            tenant_id=tenant_b.id,
            endpoint_id=endpoint_b.id,
            device_id=device_b.id,
        )
        event_a = AutomationEvent(
            tenant_id=tenant_a.id,
            endpoint_id=endpoint_a.id,
            device_id=device_a.id,
            event_type="TENANT_A_EVENT",
            reason="Alpha private event",
        )
        event_b = AutomationEvent(
            tenant_id=tenant_b.id,
            endpoint_id=endpoint_b.id,
            device_id=device_b.id,
            event_type="TENANT_B_EVENT",
            reason="Bravo private event",
        )
        db.add_all([mapping_a, mapping_b, event_a, event_b])
        db.commit()
        endpoint_b_id = endpoint_b.id
        device_b_id = device_b.id
        mapping_b_id = mapping_b.id
        tenant_b_id = tenant_b.id
        user_a_name = user_a.username
        user_b_name = user_b.username

    client_a = _login(user_a_name)
    client_b = _login(user_b_name)

    attempted_user = f"spoofed-assignment-{uuid4().hex[:8]}"
    create_other_tenant_user = client_a.post(
        "/api/v1/admin/users",
        json={
            "username": attempted_user,
            "password": "tenant-password",
            "role": "tenant_admin",
            "tenant_id": tenant_b_id,
        },
    )
    assert create_other_tenant_user.status_code == 201, create_other_tenant_user.text
    with SessionLocal() as db:
        created_user = db.query(User).filter(User.username == attempted_user).one()
        own_tenant_id = db.query(User).filter(User.username == user_a_name).one().tenant_id
        assert created_user.tenant_id == own_tenant_id
        assert created_user.tenant_id != tenant_b_id

    devices = client_a.get("/api/v1/devices")
    assert devices.status_code == 200
    assert [device["device_id"] for device in devices.json()] == ["alpha-device"]
    assert client_a.get("/devices", follow_redirects=False).status_code == 307
    assert [endpoint["hostname"] for endpoint in client_a.get("/api/v1/endpoints").json()] == [
        "alpha-endpoint"
    ]
    assert len(client_a.get("/api/v1/mappings").json()) == 1
    assert [device["device_id"] for device in client_b.get("/api/v1/devices").json()] == [
        "bravo-device"
    ]
    assert client_a.get(f"/api/v1/devices/{device_b_id}").status_code == 404
    assert client_a.get(f"/api/v1/endpoints/{endpoint_b_id}/readings").status_code == 404
    assert client_a.get(f"/api/v1/mappings/{mapping_b_id}").status_code == 404

    listed_events = client_a.get("/api/v1/events")
    assert listed_events.status_code == 200
    assert [event["event_type"] for event in listed_events.json()] == ["TENANT_A_EVENT"]
    paged_events = client_a.get("/api/v1/events/page")
    assert paged_events.status_code == 200
    assert [event["event_type"] for event in paged_events.json()["items"]] == ["TENANT_A_EVENT"]
    assert client_a.get("/events", follow_redirects=False).status_code == 307

    cross_tenant_mapping = client_a.post(
        "/api/v1/mappings",
        json={"endpoint_id": endpoint_b_id, "device_id": device_b_id},
    )
    assert cross_tenant_mapping.status_code == 404
    assert client_a.delete(f"/api/v1/devices/{device_b_id}").status_code == 404
    with SessionLocal() as db:
        assert db.query(Device).filter(Device.id == device_b_id).one_or_none() is not None
        assert db.query(Tenant).filter(Tenant.id == tenant_b_id).one_or_none() is not None


def test_tenant_agent_token_cannot_fetch_another_tenants_agent_config():
    with SessionLocal() as db:
        tenant_a, _ = _create_tenant_account(db, "config-a")
        tenant_b, _ = _create_tenant_account(db, "config-b")
        endpoint_b = Endpoint(hostname="private-agent", tenant_id=tenant_b.id)
        db.add(endpoint_b)
        db.commit()
        token_a = tenant_a.agent_token

    response = TestClient(app).get(
        "/api/v1/endpoints/agent-config",
        params={"hostname": "private-agent"},
        headers={"Authorization": "Bearer " + token_a},
    )
    assert response.status_code == 404


def test_hardware_uuid_is_unique_across_tenants_and_config_remains_scoped():
    hardware_uuid = "a19f1d84-0a2c-4a34-bf95-a61ff3231c4a"
    with SessionLocal() as db:
        tenant_a, user_a = _create_tenant_account(db, "hardware-a")
        tenant_b, user_b = _create_tenant_account(db, "hardware-b")
        token_a = tenant_a.agent_token
        token_b = tenant_b.agent_token
        username_a = user_a.username
        username_b = user_b.username
        db.commit()

    payload = {
        "hostname": "HARDWARE-A-LAPTOP",
        "hardware_uuid": hardware_uuid,
        "ip_address": "192.168.1.20",
        "battery_percentage": 51,
        "charging": False,
        "ac_connected": False,
        "timestamp": datetime.now(UTC).isoformat(),
        "agent_version": "2.0.0",
    }
    register = TestClient(app).post(
        "/api/v1/telemetry",
        json=payload,
        headers={"Authorization": "Bearer " + token_a},
    )
    assert register.status_code == 200, register.text

    forbidden_config = TestClient(app).get(
        "/api/v1/endpoints/agent-config",
        params={"hardware_uuid": hardware_uuid, "hostname": payload["hostname"]},
        headers={"Authorization": "Bearer " + token_b},
    )
    assert forbidden_config.status_code == 404

    cross_tenant_registration = TestClient(app).post(
        "/api/v1/telemetry",
        json={**payload, "hostname": "HARDWARE-B-LAPTOP"},
        headers={"Authorization": "Bearer " + token_b},
    )
    assert cross_tenant_registration.status_code == 409

    with SessionLocal() as db:
        endpoint = db.query(Endpoint).filter(Endpoint.hardware_uuid == hardware_uuid).one()
        assert endpoint.hostname == payload["hostname"]
        assert endpoint.tenant_id is not None

    assert _login(username_a).get("/api/v1/endpoints").json()[0]["hostname"] == payload["hostname"]
    assert _login(username_b).get("/api/v1/endpoints").json() == []


def test_data_apis_require_a_user_session():
    client = TestClient(app)

    assert client.get("/api/v1/devices").status_code == 401
    assert client.get("/api/v1/mappings").status_code == 401
    assert client.get("/api/v1/events").status_code == 401
    assert client.get("/api/v1/telemetry/stream").status_code == 401


def test_tenantless_admin_role_does_not_grant_super_admin_access():
    with SessionLocal() as db:
        tenant, owner = _create_tenant_account(db, "scoped")
        db.add(
            Device(
                owner_id=owner.id,
                tenant_id=tenant.id,
                name="Private device",
                device_id="private-device",
                encrypted_local_key="private-key",
            )
        )
        orphan_admin = User(
            username=f"orphan-admin-{uuid4().hex[:8]}",
            password_hash=hash_password("tenant-password"),
            tenant_id=None,
            role="manager",
            is_admin=True,
        )
        db.add(orphan_admin)
        username = orphan_admin.username
        db.commit()

    response = _login(username).get("/api/v1/devices")
    assert response.status_code == 200
    assert response.json() == []


def test_existing_owned_rows_are_backfilled_to_their_tenant():
    with SessionLocal() as db:
        tenant, user = _create_tenant_account(db, "legacy")
        endpoint = Endpoint(hostname="legacy-endpoint", owner_id=user.id)
        device = Device(
            owner_id=user.id,
            name="Legacy device",
            device_id="legacy-device",
            encrypted_local_key="legacy-key",
        )
        db.add_all([endpoint, device])
        db.flush()
        mapping = Mapping(endpoint_id=endpoint.id, device_id=device.id)
        event = AutomationEvent(
            endpoint_id=endpoint.id,
            device_id=device.id,
            event_type="LEGACY_EVENT",
        )
        db.add_all([mapping, event])
        db.commit()
        endpoint_id = endpoint.id
        device_id = device.id
        mapping_id = mapping.id
        event_id = event.id
        tenant_id = tenant.id

    _backfill_tenant_ownership()

    with SessionLocal() as db:
        assert db.query(Endpoint).filter(Endpoint.id == endpoint_id).one().tenant_id == tenant_id
        assert db.query(Device).filter(Device.id == device_id).one().tenant_id == tenant_id
        assert db.query(Mapping).filter(Mapping.id == mapping_id).one().tenant_id == tenant_id
        assert db.query(AutomationEvent).filter(AutomationEvent.id == event_id).one().tenant_id == tenant_id


def test_reporting_schedule_and_endpoint_details_are_tenant_scoped():
    with SessionLocal() as db:
        tenant_a, user_a = _create_tenant_account(db, "schedule-a")
        tenant_b, user_b = _create_tenant_account(db, "schedule-b")
        endpoint = Endpoint(
            hostname="schedule-device",
            tenant_id=tenant_a.id,
            platform="windows",
            hardware_uuid=str(uuid4()),
            battery_percentage=63,
            last_seen_at=datetime.now(UTC),
        )
        db.add(endpoint)
        device = Device(
            tenant_id=tenant_a.id,
            name="schedule-switch",
            device_id=f"schedule-switch-{uuid4().hex}",
            encrypted_local_key="encrypted-key",
            power_dp_id="cur_power",
            energy_dp_id="add_ele",
            meter_power_watts=84.5,
            meter_power_sample_at=datetime.now(UTC),
            meter_energy_month_kwh=2.75,
            meter_energy_sample_at=datetime.now(UTC),
            meter_month_key=datetime.now(UTC).strftime("%Y-%m"),
        )
        db.add(device)
        db.flush()
        db.add(Mapping(
            tenant_id=tenant_a.id,
            endpoint_id=endpoint.id,
            device_id=device.id,
        ))
        db.commit()
        endpoint_id = endpoint.id
        tenant_a_id = tenant_a.id
        tenant_b_id = tenant_b.id
        username_a = user_a.username
        username_b = user_b.username

    tenant_client = _login(username_a)
    initial = tenant_client.get("/api/v1/admin/tenant-settings")
    assert initial.status_code == 200, initial.text
    assert initial.json()["telemetry_interval_minutes"] == 5

    changed = tenant_client.put(
        "/api/v1/admin/tenant-settings",
        json={"telemetry_interval_minutes": 30},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["telemetry_interval_minutes"] == 30

    response = tenant_client.get(f"/api/v1/endpoints/{endpoint_id}/details")
    assert response.status_code == 200, response.text
    assert response.json()["reporting_interval_minutes"] == 30
    assert response.json()["display_name"] == "schedule-device"
    mapped_switch = response.json()["mappings"][0]
    assert mapped_switch["name"] == "schedule-switch"
    assert mapped_switch["meter_power_watts"] == 84.5
    assert mapped_switch["meter_energy_month_kwh"] == 2.75
    assert mapped_switch["power_dp_id"] == "cur_power"
    assert mapped_switch["energy_dp_id"] == "add_ele"

    forbidden_read = tenant_client.get(
        "/api/v1/admin/tenant-settings",
        params={"tenant_id": tenant_b_id},
    )
    forbidden_write = tenant_client.put(
        "/api/v1/admin/tenant-settings",
        json={"tenant_id": tenant_b_id, "telemetry_interval_minutes": 60},
    )
    forbidden_detail = _login(username_b).get(
        f"/api/v1/endpoints/{endpoint_id}/details"
    )
    assert forbidden_read.status_code == 403
    assert forbidden_write.status_code == 403
    assert forbidden_detail.status_code == 404

    with SessionLocal() as db:
        assert db.get(Tenant, tenant_a_id).telemetry_interval_minutes == 30
        assert db.get(Tenant, tenant_b_id).telemetry_interval_minutes == 5


def test_reporting_schedule_rejects_out_of_range_values():
    with SessionLocal() as db:
        _, user = _create_tenant_account(db, "schedule-range")
        username = user.username
        db.commit()

    response = _login(username).put(
        "/api/v1/admin/tenant-settings",
        json={"telemetry_interval_minutes": 1441},
    )
    assert response.status_code == 422
