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


def test_enrollment_is_tenant_bound_reusable_across_platforms_and_returns_credentials_once():
    client = TestClient(app)
    register_tenant_admin(
        client,
        "mac-enrollment-admin",
        "mac-enrollment-admin-password",
        "Mac Enrollment Tenant",
    )

    created = client.post(
        "/api/v1/admin/endpoint-enrollments",
        json={},
    )
    assert created.status_code == 201, created.text
    assert created.headers["Cache-Control"] == "private, no-store"
    code = created.json()["enrollment_code"]
    expires_at = datetime.fromisoformat(created.json()["expires_at"])
    assert timedelta(hours=23, minutes=59) < expires_at - datetime.now(UTC) < timedelta(hours=24, minutes=1)

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
        assert enrollment.platform is None
        assert enrollment.used_at is None
        assert enrollment.enrollment_count == 1
        assert enrollment.last_used_at is not None
        assert enrollment.code_hash == hashlib.sha256(code.encode()).hexdigest()
        assert endpoint.tenant_id == tenant_id
        assert endpoint.automation_enabled is False
        assert endpoint.installation_id == installation_id
        assert endpoint.token_hash == hashlib.sha256(result["credential"].encode()).hexdigest()
        assert authenticate_endpoint_token(f"Bearer {result['credential']}", db) == (False, None)

    second_installation_id = str(uuid4())
    second_exchange = client.post(
        "/api/v1/endpoint-enrollment/exchange",
        json={
            "code": code,
            "platform": "windows",
            "installation_id": second_installation_id,
            "hostname": "Office Laptop",
            "device_class": "laptop",
        },
    )
    assert second_exchange.status_code == 201, second_exchange.text
    assert second_exchange.json()["platform"] == "windows"
    with SessionLocal() as db:
        assert db.query(EndpointEnrollment).one().enrollment_count == 2

    duplicate_installation = client.post(
        "/api/v1/endpoint-enrollment/exchange",
        json={
            "code": code,
            "platform": "macos",
            "installation_id": installation_id,
            "hostname": "Office Mac",
        },
    )
    assert duplicate_installation.status_code == 409


def test_existing_platform_scoped_enrollments_remain_single_use():
    client = TestClient(app)
    register_tenant_admin(
        client,
        "legacy-enrollment-admin",
        "legacy-enrollment-password",
        "Legacy Enrollment Tenant",
    )
    created = client.post("/api/v1/admin/endpoint-enrollments", json={})
    assert created.status_code == 201, created.text
    enrollment = created.json()

    with SessionLocal() as db:
        stored = db.get(EndpointEnrollment, enrollment["id"])
        stored.platform = "macos"
        db.commit()

    def exchange(platform: str, installation_id: str):
        return client.post(
            "/api/v1/endpoint-enrollment/exchange",
            json={
                "code": enrollment["enrollment_code"],
                "platform": platform,
                "installation_id": installation_id,
                "hostname": "Legacy Mac",
                "device_class": "laptop",
            },
        )

    mismatched_platform = exchange("windows", str(uuid4()))
    assert mismatched_platform.status_code == 422

    successful_exchange = exchange("macos", str(uuid4()))
    assert successful_exchange.status_code == 201, successful_exchange.text
    reused_token = exchange("macos", str(uuid4()))
    assert reused_token.status_code == 422

    with SessionLocal() as db:
        stored = db.get(EndpointEnrollment, enrollment["id"])
        assert stored.used_at is not None
        assert stored.enrollment_count == 1


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
        json={},
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
        json={},
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


def test_universal_token_can_enroll_android_then_be_revoked():
    client = TestClient(app)
    register_tenant_admin(
        client,
        "platform-admin",
        "platform-admin-password",
        "Platform Tenant",
    )

    created = client.post(
        "/api/v1/admin/endpoint-enrollments",
        json={},
    )
    assert created.status_code == 201, created.text
    enrollment = created.json()
    installation_id = str(uuid4())
    exchange = client.post(
        "/api/v1/endpoint-enrollment/exchange",
        json={
            "code": enrollment["enrollment_code"],
            "platform": "android",
            "installation_id": installation_id,
            "hostname": "Android tablet",
            "device_class": "tablet",
        },
    )
    assert exchange.status_code == 201, exchange.text
    ios_exchange = client.post(
        "/api/v1/endpoint-enrollment/exchange",
        json={
            "code": enrollment["enrollment_code"],
            "platform": "ios",
            "installation_id": str(uuid4()),
            "hostname": "iOS phone",
            "device_class": "phone",
        },
    )
    assert ios_exchange.status_code == 201, ios_exchange.text
    mobile_automation = client.patch(
        f"/api/v1/endpoints/{exchange.json()['endpoint_id']}/automation",
        json={"enabled": True},
    )
    assert mobile_automation.status_code == 409
    revoked = client.delete(
        f"/api/v1/admin/endpoint-enrollments/{enrollment['id']}"
    )
    assert revoked.status_code == 204
    further_enrollment = client.post(
        "/api/v1/endpoint-enrollment/exchange",
        json={
            "code": enrollment["enrollment_code"],
            "platform": "ios",
            "installation_id": str(uuid4()),
            "hostname": "iOS phone",
            "device_class": "phone",
        },
    )
    assert further_enrollment.status_code == 422
    credential_revoked = client.post(
        f"/api/v1/endpoints/{exchange.json()['endpoint_id']}/credential/revoke"
    )
    assert credential_revoked.status_code == 200


def test_expired_universal_enrollment_token_cannot_be_exchanged():
    client = TestClient(app)
    register_tenant_admin(
        client,
        "expired-enrollment-admin",
        "expired-enrollment-password",
        "Expired Enrollment Tenant",
    )
    created = client.post("/api/v1/admin/endpoint-enrollments", json={})
    assert created.status_code == 201, created.text
    enrollment = created.json()

    with SessionLocal() as db:
        stored = db.get(EndpointEnrollment, enrollment["id"])
        stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()

    exchange = client.post(
        "/api/v1/endpoint-enrollment/exchange",
        json={
            "code": enrollment["enrollment_code"],
            "platform": "ios",
            "installation_id": str(uuid4()),
            "hostname": "Expired iPhone",
            "device_class": "phone",
        },
    )
    assert exchange.status_code == 422


def test_enrollment_listing_is_tenant_scoped_and_does_not_reveal_token():
    client = TestClient(app)
    register_tenant_admin(
        client,
        "enrollment-list-owner",
        "enrollment-list-password",
        "Enrollment List Tenant",
    )
    created = client.post("/api/v1/admin/endpoint-enrollments", json={})
    assert created.status_code == 201, created.text
    enrollment = created.json()

    listed = client.get("/api/v1/admin/endpoint-enrollments")
    assert listed.status_code == 200, listed.text
    assert listed.headers["cache-control"] == "private, no-store"
    assert listed.json() == [
        {
            "id": enrollment["id"],
            "tenant_name": "Enrollment List Tenant",
            "created_at": listed.json()[0]["created_at"],
            "expires_at": enrollment["expires_at"],
            "revoked_at": None,
            "enrollment_count": 0,
            "last_used_at": None,
        }
    ]
    assert "enrollment_code" not in listed.json()[0]
    assert "code_hash" not in listed.json()[0]

    other_client = TestClient(app)
    register_tenant_admin(
        other_client,
        "other-enrollment-list-owner",
        "other-enrollment-list-password",
        "Other Enrollment Tenant",
    )
    assert other_client.get("/api/v1/admin/endpoint-enrollments").json() == []
    assert other_client.delete(
        f"/api/v1/admin/endpoint-enrollments/{enrollment['id']}"
    ).status_code == 404


def test_admin_can_reveal_only_their_active_enrollment_token():
    client = TestClient(app)
    register_tenant_admin(
        client,
        "enrollment-reveal-owner",
        "enrollment-reveal-password",
        "Enrollment Reveal Tenant",
    )
    created = client.post("/api/v1/admin/endpoint-enrollments", json={})
    assert created.status_code == 201, created.text
    enrollment = created.json()

    revealed = client.get(f"/api/v1/admin/endpoint-enrollments/{enrollment['id']}/token")
    assert revealed.status_code == 200, revealed.text
    assert revealed.headers["cache-control"] == "private, no-store"
    assert revealed.json() == {
        "id": enrollment["id"],
        "enrollment_code": enrollment["enrollment_code"],
        "expires_at": enrollment["expires_at"],
    }

    with SessionLocal() as db:
        stored = db.get(EndpointEnrollment, enrollment["id"])
        assert stored.encrypted_code is not None
        assert stored.encrypted_code != enrollment["enrollment_code"]
        assert stored.code_hash == hashlib.sha256(enrollment["enrollment_code"].encode()).hexdigest()

    other_client = TestClient(app)
    register_tenant_admin(
        other_client,
        "enrollment-reveal-other",
        "enrollment-reveal-other-password",
        "Other Enrollment Reveal Tenant",
    )
    assert other_client.get(
        f"/api/v1/admin/endpoint-enrollments/{enrollment['id']}/token"
    ).status_code == 404


def test_admin_is_limited_to_five_active_tokens_and_revocation_frees_a_slot():
    client = TestClient(app)
    register_tenant_admin(
        client,
        "enrollment-limit-owner",
        "enrollment-limit-password",
        "Enrollment Limit Tenant",
    )
    enrollments = []
    for _ in range(5):
        created = client.post("/api/v1/admin/endpoint-enrollments", json={})
        assert created.status_code == 201, created.text
        enrollments.append(created.json())

    limited = client.post("/api/v1/admin/endpoint-enrollments", json={})
    assert limited.status_code == 409
    assert "5 active enrollment tokens" in limited.json()["detail"]
    assert len(client.get("/api/v1/admin/endpoint-enrollments").json()) == 5

    revoked = client.delete(
        f"/api/v1/admin/endpoint-enrollments/{enrollments[0]['id']}"
    )
    assert revoked.status_code == 204
    replacement = client.post("/api/v1/admin/endpoint-enrollments", json={})
    assert replacement.status_code == 201, replacement.text
    listed_ids = {
        enrollment["id"]
        for enrollment in client.get("/api/v1/admin/endpoint-enrollments").json()
    }
    assert len(listed_ids) == 5
    assert enrollments[0]["id"] not in listed_ids


def test_expired_enrollment_token_releases_active_token_quota():
    client = TestClient(app)
    register_tenant_admin(
        client,
        "enrollment-expired-quota-owner",
        "enrollment-expired-quota-password",
        "Enrollment Expired Quota Tenant",
    )
    enrollments = [
        client.post("/api/v1/admin/endpoint-enrollments", json={}).json()
        for _ in range(5)
    ]

    with SessionLocal() as db:
        stored = db.get(EndpointEnrollment, enrollments[0]["id"])
        stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()

    replacement = client.post("/api/v1/admin/endpoint-enrollments", json={})
    assert replacement.status_code == 201, replacement.text
    assert len(client.get("/api/v1/admin/endpoint-enrollments").json()) == 5


def test_expired_and_revoked_tokens_are_hidden_and_cannot_be_revealed():
    client = TestClient(app)
    register_tenant_admin(
        client,
        "enrollment-expiry-visibility",
        "enrollment-expiry-visibility-password",
        "Enrollment Expiry Visibility Tenant",
    )
    expired = client.post("/api/v1/admin/endpoint-enrollments", json={}).json()
    with SessionLocal() as db:
        stored = db.get(EndpointEnrollment, expired["id"])
        stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()

    assert client.get("/api/v1/admin/endpoint-enrollments").json() == []
    assert client.get(
        f"/api/v1/admin/endpoint-enrollments/{expired['id']}/token"
    ).status_code == 404

    active = client.post("/api/v1/admin/endpoint-enrollments", json={}).json()
    assert client.delete(
        f"/api/v1/admin/endpoint-enrollments/{active['id']}"
    ).status_code == 204
    assert client.get("/api/v1/admin/endpoint-enrollments").json() == []
    assert client.get(
        f"/api/v1/admin/endpoint-enrollments/{active['id']}/token"
    ).status_code == 404


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
        json={},
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
