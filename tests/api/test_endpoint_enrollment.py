import hashlib
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.endpoint import Endpoint
from app.models.endpoint_enrollment import EndpointEnrollment
from app.services.endpoint_service import authenticate_endpoint_token
from conftest import register_tenant_admin


def test_enrollment_is_tenant_bound_single_use_and_returns_installation_credential_once():
    client = TestClient(app)
    register_tenant_admin(
        client,
        "mac-enrollment-admin",
        "mac-enrollment-admin-password",
        "Mac Enrollment Tenant",
    )

    created = client.post(
        "/api/v1/admin/endpoint-enrollments",
        json={"platform": "macos"},
    )
    assert created.status_code == 201, created.text
    assert created.headers["Cache-Control"] == "private, no-store"
    code = created.json()["enrollment_code"]

    installation_id = str(uuid4())
    exchanged = client.post(
        "/api/v1/endpoint-enrollment/exchange",
        json={
            "code": code,
            "platform": "macos",
            "installation_id": installation_id,
            "hostname": "Office Mac",
            "device_class": "laptop",
        },
    )
    assert exchanged.status_code == 201, exchanged.text
    assert exchanged.headers["Cache-Control"] == "private, no-store"
    result = exchanged.json()
    assert result["installation_id"] == installation_id
    assert result["platform"] == "macos"

    with SessionLocal() as db:
        enrollment = db.query(EndpointEnrollment).one()
        tenant_id = enrollment.tenant_id
        endpoint = db.query(Endpoint).one()
        assert enrollment.tenant_id == tenant_id
        assert enrollment.used_at is not None
        assert enrollment.code_hash == hashlib.sha256(code.encode()).hexdigest()
        assert endpoint.tenant_id == tenant_id
        assert endpoint.automation_enabled is False
        assert endpoint.installation_id == installation_id
        assert endpoint.token_hash == hashlib.sha256(result["credential"].encode()).hexdigest()
        assert authenticate_endpoint_token(f"Bearer {result['credential']}", db) == (False, None)

    replay = client.post(
        "/api/v1/endpoint-enrollment/exchange",
        json={
            "code": code,
            "platform": "macos",
            "installation_id": installation_id,
            "hostname": "Office Mac",
        },
    )
    assert replay.status_code == 422


def test_enrolled_telemetry_accepts_optional_ip_and_revocation_stops_reports():
    client = TestClient(app)
    register_tenant_admin(
        client,
        "mac-report-admin",
        "mac-report-admin-password",
        "Mac Report Tenant",
    )
    enrollment = client.post(
        "/api/v1/admin/endpoint-enrollments",
        json={"platform": "macos"},
    ).json()
    installation_id = str(uuid4())
    credentials = client.post(
        "/api/v1/endpoint-enrollment/exchange",
        json={
            "code": enrollment["enrollment_code"],
            "platform": "macos",
            "installation_id": installation_id,
            "hostname": "Bedroom Mac",
            "device_class": "laptop",
        },
    ).json()
    telemetry = {
        "hostname": "Bedroom Mac",
        "installation_id": installation_id,
        "platform": "macos",
        "device_class": "laptop",
        "battery_percentage": 47,
        "charging": False,
        "ac_connected": None,
        "timestamp": datetime.now(UTC).isoformat(),
        "agent_version": "0.1.0",
    }

    accepted = client.post(
        "/api/v1/telemetry",
        json=telemetry,
        headers={"Authorization": f"Bearer {credentials['credential']}"},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["platform"] == "macos"

    endpoint_id = credentials["endpoint_id"]
    revoked = client.post(f"/api/v1/endpoints/{endpoint_id}/credential/revoke")
    assert revoked.status_code == 200

    rejected = client.post(
        "/api/v1/telemetry",
        json=telemetry,
        headers={"Authorization": f"Bearer {credentials['credential']}"},
    )
    assert rejected.status_code == 401


def test_enrollment_credentials_cannot_spoof_platform_or_installation():
    client = TestClient(app)
    register_tenant_admin(
        client,
        "mac-identity-admin",
        "mac-identity-admin-password",
        "Mac Identity Tenant",
    )
    enrollment = client.post(
        "/api/v1/admin/endpoint-enrollments",
        json={"platform": "macos"},
    ).json()
    installation_id = str(uuid4())
    credentials = client.post(
        "/api/v1/endpoint-enrollment/exchange",
        json={
            "code": enrollment["enrollment_code"],
            "platform": "macos",
            "installation_id": installation_id,
            "hostname": "Identity Mac",
        },
    ).json()
    payload = {
        "hostname": "Identity Mac",
        "installation_id": str(uuid4()),
        "platform": "macos",
        "battery_percentage": 50,
        "charging": False,
        "timestamp": datetime.now(UTC).isoformat(),
        "agent_version": "0.1.0",
    }

    response = client.post(
        "/api/v1/telemetry",
        json=payload,
        headers={"Authorization": f"Bearer {credentials['credential']}"},
    )
    assert response.status_code == 403


def test_android_enrollment_is_disabled_by_default_and_unused_codes_can_be_revoked():
    client = TestClient(app)
    register_tenant_admin(
        client,
        "platform-admin",
        "platform-admin-password",
        "Platform Tenant",
    )

    disabled = client.post(
        "/api/v1/admin/endpoint-enrollments",
        json={"platform": "android"},
    )
    assert disabled.status_code == 409

    enrollment = client.post(
        "/api/v1/admin/endpoint-enrollments",
        json={"platform": "macos"},
    ).json()
    revoked = client.delete(
        f"/api/v1/admin/endpoint-enrollments/{enrollment['id']}"
    )
    assert revoked.status_code == 204
    replay = client.post(
        "/api/v1/endpoint-enrollment/exchange",
        json={
            "code": enrollment["enrollment_code"],
            "platform": "macos",
            "installation_id": str(uuid4()),
            "hostname": "Unenrolled Mac",
        },
    )
    assert replay.status_code == 422


def test_automation_enable_requires_fresh_sample_and_enrolled_macos_endpoint():
    client = TestClient(app)
    register_tenant_admin(
        client,
        "mac-automation-admin",
        "mac-automation-admin-password",
        "Mac Automation Tenant",
    )
    enrollment = client.post(
        "/api/v1/admin/endpoint-enrollments",
        json={"platform": "macos"},
    ).json()
    installation_id = str(uuid4())
    credentials = client.post(
        "/api/v1/endpoint-enrollment/exchange",
        json={
            "code": enrollment["enrollment_code"],
            "platform": "macos",
            "installation_id": installation_id,
            "hostname": "Automation Mac",
        },
    ).json()
    endpoint_id = credentials["endpoint_id"]
    url = f"/api/v1/endpoints/{endpoint_id}/automation"

    before_sample = client.patch(url, json={"enabled": True})
    assert before_sample.status_code == 409

    sample = client.post(
        "/api/v1/telemetry",
        json={
            "hostname": "Automation Mac",
            "installation_id": installation_id,
            "platform": "macos",
            "battery_percentage": 72,
            "charging": False,
            "timestamp": datetime.now(UTC).isoformat(),
            "agent_version": "0.1.0",
        },
        headers={"Authorization": f"Bearer {credentials['credential']}"},
    )
    assert sample.status_code == 200
    enabled = client.patch(url, json={"enabled": True})
    assert enabled.status_code == 200, enabled.text
    assert enabled.json()["automation_enabled"] is True

    with SessionLocal() as db:
        endpoint = db.get(Endpoint, endpoint_id)
        endpoint.last_seen_at = datetime.now(UTC) - timedelta(hours=1)
        db.commit()

    stale_reenable = client.patch(url, json={"enabled": True})
    assert stale_reenable.status_code == 409
