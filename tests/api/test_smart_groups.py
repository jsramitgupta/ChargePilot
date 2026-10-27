from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.smart_group import SensorExecution
from conftest import register_tenant_admin


def enroll_endpoint(
    client: TestClient, platform: str, hostname: str
) -> tuple[str, str]:
    enrollment = client.post("/api/v1/admin/endpoint-enrollments", json={})
    assert enrollment.status_code == 201, enrollment.text
    installation_id = str(uuid4())
    exchanged = client.post(
        "/api/v1/endpoint-enrollment/exchange",
        json={
            "code": enrollment.json()["enrollment_code"],
            "platform": platform,
            "installation_id": installation_id,
            "hostname": hostname,
            "device_class": "laptop",
        },
    )
    assert exchanged.status_code == 201, exchanged.text
    endpoint_id = exchanged.json()["endpoint_id"]
    telemetry = client.post(
        "/api/v1/telemetry",
        json={
            "hostname": hostname,
            "installation_id": installation_id,
            "platform": platform,
            "device_class": "laptop",
            "battery_percentage": 42,
            "charging": False,
            "timestamp": datetime.now(UTC).isoformat(),
            "agent_version": "0.1.0",
        },
        headers={"Authorization": f"Bearer {exchanged.json()['credential']}"},
    )
    assert telemetry.status_code == 200, telemetry.text
    return endpoint_id, exchanged.json()["credential"]


def test_smart_group_runs_fixed_sensors_and_records_typed_results():
    client = TestClient(app)
    register_tenant_admin(client, "sensor-run-admin", "sensor-run-admin-password")
    windows_id, windows_credential = enroll_endpoint(client, "windows", "sensor-win")
    enroll_endpoint(client, "macos", "sensor-mac")

    created = client.post(
        "/api/v1/smart-groups",
        json={
            "name": "Laptop checks",
            "criteria": {"platforms": ["windows", "macos"], "battery_min": 20},
            "sensor_ids": ["os_version", "uptime_seconds"],
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["matching_endpoint_count"] == 2
    explicit = client.post(
        "/api/v1/smart-groups",
        json={
            "name": "Selected Windows endpoint",
            "criteria": {"platforms": ["windows"], "endpoint_ids": [windows_id]},
            "sensor_ids": ["uptime_seconds"],
        },
    )
    assert explicit.status_code == 201, explicit.text
    assert explicit.json()["matching_endpoint_count"] == 1

    queued = client.post(f"/api/v1/smart-groups/{created.json()['id']}/run")
    assert queued.status_code == 200, queued.text
    assert queued.json() == {"queued_endpoints": 2, "queued_sensors": 4}
    repeated = client.post(f"/api/v1/smart-groups/{created.json()['id']}/run")
    assert repeated.status_code == 200, repeated.text
    assert repeated.json() == {"queued_endpoints": 0, "queued_sensors": 0}

    headers = {"Authorization": f"Bearer {windows_credential}"}
    claimed = client.post("/api/v1/endpoint-sensors/claim", headers=headers)
    assert claimed.status_code == 200, claimed.text
    sensor = claimed.json()["sensor"]
    assert sensor["sensor_id"] in {"os_version", "uptime_seconds"}

    value = "Windows Test" if sensor["sensor_id"] == "os_version" else 321
    invalid_value = 321 if sensor["sensor_id"] == "os_version" else "not an integer"
    invalid_shape = client.post(
        f"/api/v1/endpoint-sensors/{sensor['id']}/report",
        headers=headers,
        json={
            "claim_token": sensor["claim_token"],
            "value": {"command": "not supported"},
        },
    )
    assert invalid_shape.status_code == 422
    invalid_report = client.post(
        f"/api/v1/endpoint-sensors/{sensor['id']}/report",
        headers=headers,
        json={"claim_token": sensor["claim_token"], "value": invalid_value},
    )
    assert invalid_report.status_code == 422
    reported = client.post(
        f"/api/v1/endpoint-sensors/{sensor['id']}/report",
        headers=headers,
        json={"claim_token": sensor["claim_token"], "value": value},
    )
    assert reported.status_code == 200, reported.text
    assert reported.json() == {"status": "completed"}

    listed = client.get("/api/v1/smart-groups")
    assert listed.status_code == 200, listed.text
    group_row = next(row for row in listed.json() if row["id"] == created.json()["id"])
    result = next(
        run for run in group_row["recent_executions"] if run["id"] == sensor["id"]
    )
    assert result["result"] == {"value": value}
    assert result["status"] == "completed"


def test_smart_group_rejects_unapproved_sensor_and_cross_tenant_endpoint():
    client = TestClient(app)
    register_tenant_admin(client, "sensor-scope-admin", "sensor-scope-admin-password")
    other_client = TestClient(app)
    register_tenant_admin(
        other_client, "sensor-other-admin", "sensor-other-admin-password"
    )
    other_endpoint_id, _ = enroll_endpoint(other_client, "windows", "other-workspace")

    payload = {
        "name": "Invalid target",
        "criteria": {"platforms": ["windows"], "endpoint_ids": [other_endpoint_id]},
        "sensor_ids": ["os_version"],
    }
    cross_tenant = client.post("/api/v1/smart-groups", json=payload)
    assert cross_tenant.status_code == 422

    payload["criteria"] = {"platforms": ["windows"]}
    payload["sensor_ids"] = ["powershell"]
    unsupported_sensor = client.post("/api/v1/smart-groups", json=payload)
    assert unsupported_sensor.status_code == 422

    assert client.get("/api/v1/smart-groups").json() == []


def test_sensor_claim_token_fences_expired_claims():
    client = TestClient(app)
    register_tenant_admin(client, "sensor-lease-admin", "sensor-lease-admin-password")
    _, credential = enroll_endpoint(client, "windows", "lease-win")
    created = client.post(
        "/api/v1/smart-groups",
        json={
            "name": "Lease checks",
            "criteria": {"platforms": ["windows"]},
            "sensor_ids": ["uptime_seconds"],
        },
    )
    assert created.status_code == 201, created.text
    assert (
        client.post(f"/api/v1/smart-groups/{created.json()['id']}/run").status_code
        == 200
    )
    headers = {"Authorization": f"Bearer {credential}"}
    first_claim = client.post("/api/v1/endpoint-sensors/claim", headers=headers).json()[
        "sensor"
    ]
    with SessionLocal() as db:
        execution = db.get(SensorExecution, first_claim["id"])
        execution.lease_expires_at = datetime(2000, 1, 1, tzinfo=UTC)
        db.commit()

    second_claim = client.post(
        "/api/v1/endpoint-sensors/claim", headers=headers
    ).json()["sensor"]
    assert second_claim["id"] == first_claim["id"]
    assert second_claim["claim_token"] != first_claim["claim_token"]
    stale_report = client.post(
        f"/api/v1/endpoint-sensors/{first_claim['id']}/report",
        headers=headers,
        json={"claim_token": first_claim["claim_token"], "value": 1},
    )
    assert stale_report.status_code == 409
    valid_report = client.post(
        f"/api/v1/endpoint-sensors/{second_claim['id']}/report",
        headers=headers,
        json={"claim_token": second_claim["claim_token"], "value": 1},
    )
    assert valid_report.status_code == 200, valid_report.text
