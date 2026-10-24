from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.models.endpoint import Endpoint
from app.main import app
from app.models.messaging import TelemetryOutbox
from conftest import TEST_GLOBAL_AGENT_TOKEN


def test_telemetry_route_accepts_valid_endpoint():
    client = TestClient(app)
    response = client.post(
        "/api/v1/telemetry",
        json={
            "hostname": "LAPTOP-001",
            "hardware_uuid": "b19f1d84-0a2c-4a34-bf95-a61ff3231c46",
            "ip_address": "192.168.0.51",
            "battery_percentage": 18,
            "charging": False,
            "ac_connected": False,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_version": "1.0.0",
        },
        headers={"Authorization": "Bearer test-endpoint-token"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"


def test_telemetry_is_durably_queued_with_endpoint_snapshot():
    client = TestClient(app)
    response = client.post(
        "/api/v1/telemetry",
        json={
            "hostname": "OUTBOX-LAPTOP",
            "hardware_uuid": "b19f1d84-0a2c-4a34-bf95-a61ff3231c47",
            "ip_address": "192.168.0.52",
            "battery_percentage": 18,
            "charging": False,
            "ac_connected": False,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_version": "1.0.0",
        },
        headers={"Authorization": "Bearer test-endpoint-token"},
    )

    assert response.status_code == 200
    assert "asynchronous" in response.json()["message"]
    with SessionLocal() as db:
        event = db.query(TelemetryOutbox).one()
        assert event.aggregate_key
        assert '"hostname":"OUTBOX-LAPTOP"' in event.payload_json
        assert '"hardware_uuid":"b19f1d84-0a2c-4a34-bf95-a61ff3231c47"' in event.payload_json


def test_telemetry_accepts_system_metrics_and_returns_workspace_interval():
    from app.models.telemetry import BatteryReading
    from app.models.tenant import Tenant

    with SessionLocal() as db:
        tenant = Tenant(name="Metrics tenant", slug="metrics-tenant", agent_token="metrics-test-token")
        db.add(tenant)
        db.commit()
        tenant.telemetry_interval_minutes = 30
        db.commit()
        tenant_id = tenant.id

    hardware_uuid = "b19f1d84-0a2c-4a34-bf95-a61ff3231c72"
    client = TestClient(app)
    response = client.post(
        "/api/v1/telemetry",
        json={
            "hostname": "METRICS-LAPTOP",
            "hardware_uuid": hardware_uuid,
            "battery_percentage": 71,
            "charging": False,
            "ac_connected": False,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_version": "2.0.0",
            "system_metrics": {
                "cpu_usage_percent": 42.5,
                "gpu_usage_percent": 21.0,
                "memory_used_bytes": 4_000_000_000,
                "memory_total_bytes": 8_000_000_000,
                "disks": [{"name": "C:", "used_bytes": 20_000, "total_bytes": 40_000}],
            },
        },
        headers={"Authorization": "Bearer metrics-test-token"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["reporting_interval_seconds"] == 1800
    with SessionLocal() as db:
        endpoint = db.query(Endpoint).filter_by(hardware_uuid=hardware_uuid).one()
        assert endpoint.tenant_id == tenant_id
        reading = db.query(BatteryReading).filter_by(endpoint_id=endpoint.id).one()
        assert '"cpu_usage_percent":42.5' in reading.system_metrics_json
        assert '"name":"C:"' in reading.system_metrics_json


def test_telemetry_rejects_invalid_system_metric_ranges():
    client = TestClient(app)
    headers = {"Authorization": "******"}
    metrics_samples = [
        {"cpu_usage_percent": 101},
        {"memory_used_bytes": 2_000, "memory_total_bytes": 1_000},
        {"disks": [{"name": "C:", "used_bytes": 2_000, "total_bytes": 1_000}]},
    ]

    for index, system_metrics in enumerate(metrics_samples):
        response = client.post(
            "/api/v1/telemetry",
            json={
                "hostname": f"INVALID-METRICS-{index}",
                "hardware_uuid": f"b19f1d84-0a2c-4a34-bf95-a61ff3231c{80 + index}",
                "battery_percentage": 50,
                "charging": False,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "agent_version": "2.0.0",
                "system_metrics": system_metrics,
            },
            headers=headers,
        )

        assert response.status_code == 422, response.text


def test_telemetry_rejects_new_endpoint_without_hardware_uuid():
    client = TestClient(app)
    response = client.post(
        "/api/v1/telemetry",
        json={
            "hostname": "UUID-REQUIRED-LAPTOP",
            "ip_address": "192.168.0.53",
            "battery_percentage": 50,
            "charging": False,
            "ac_connected": False,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_version": "1.0.0",
        },
        headers={"Authorization": "Bearer test-endpoint-token"},
    )

    assert response.status_code == 422
    assert "hardware_uuid is required" in response.json()["detail"]


def test_telemetry_rejects_far_future_timestamp():
    response = TestClient(app).post(
        "/api/v1/telemetry",
        json={
            "hostname": "FUTURE-TIMESTAMP",
            "hardware_uuid": "b19f1d84-0a2c-4a34-bf95-a61ff3231c60",
            "ip_address": "192.168.0.57",
            "battery_percentage": 50,
            "charging": False,
            "ac_connected": False,
            "timestamp": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
            "agent_version": "1.0.0",
        },
        headers={"Authorization": f"Bearer {TEST_GLOBAL_AGENT_TOKEN}"},
    )

    assert response.status_code == 400
    assert "future" in response.json()["detail"]


def test_out_of_order_telemetry_does_not_regress_endpoint_snapshot():
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {TEST_GLOBAL_AGENT_TOKEN}"}
    hardware_uuid = "b19f1d84-0a2c-4a34-bf95-a61ff3231c61"
    newest = datetime.now(timezone.utc)
    common = {
        "hostname": "ORDERED-LAPTOP",
        "hardware_uuid": hardware_uuid,
        "ip_address": "192.168.0.58",
        "charging": False,
        "ac_connected": False,
        "agent_version": "1.0.0",
    }

    first = client.post(
        "/api/v1/telemetry",
        json={**common, "battery_percentage": 31, "timestamp": newest.isoformat()},
        headers=headers,
    )
    delayed = client.post(
        "/api/v1/telemetry",
        json={
            **common,
            "battery_percentage": 84,
            "timestamp": (newest - timedelta(seconds=30)).isoformat(),
        },
        headers=headers,
    )

    assert first.status_code == 200
    assert delayed.status_code == 200
    with SessionLocal() as db:
        endpoint = db.query(Endpoint).filter_by(hardware_uuid=hardware_uuid).one()
        assert endpoint.battery_percentage == 31


def test_placeholder_hardware_uuid_is_rejected():
    client = TestClient(app)
    response = client.post(
        "/api/v1/telemetry",
        json={
            "hostname": "INVALID-UUID-LAPTOP",
            "hardware_uuid": "00000000-0000-0000-0000-000000000000",
            "ip_address": "192.168.0.54",
            "battery_percentage": 50,
            "charging": False,
            "ac_connected": False,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_version": "1.0.0",
        },
        headers={"Authorization": "Bearer test-endpoint-token"},
    )

    assert response.status_code == 422


def test_hardware_uuid_is_identity_and_hostname_can_change():
    client = TestClient(app)
    headers = {"Authorization": "Bearer test-endpoint-token"}
    hardware_uuid = "b19f1d84-0a2c-4a34-bf95-a61ff3231c48"

    for hostname in ("LAPTOP-BEFORE-RENAME", "LAPTOP-AFTER-RENAME"):
        response = client.post(
            "/api/v1/telemetry",
            json={
                "hostname": hostname,
                "hardware_uuid": hardware_uuid.upper(),
                "ip_address": "192.168.0.55",
                "battery_percentage": 50,
                "charging": False,
                "ac_connected": False,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "agent_version": "1.0.0",
            },
            headers=headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["hardware_uuid"] == hardware_uuid

    with SessionLocal() as db:
        endpoints = db.query(Endpoint).filter(Endpoint.hardware_uuid == hardware_uuid).all()
        assert len(endpoints) == 1
        assert endpoints[0].hostname == "LAPTOP-AFTER-RENAME"

    config = client.get(
        "/api/v1/endpoints/agent-config",
        params={"hardware_uuid": hardware_uuid},
        headers=headers,
    )
    assert config.status_code == 200, config.text
    assert config.json()["hostname"] == "LAPTOP-AFTER-RENAME"
    assert config.json()["hardware_uuid"] == hardware_uuid


def test_telemetry_assigns_uuid_to_existing_legacy_endpoint():
    from app.models.system_setting import SystemSetting

    with SessionLocal() as db:
        global_token = db.query(SystemSetting.value).filter(
            SystemSetting.key == "global_agent_token"
        ).scalar()
        endpoint = Endpoint(hostname="LEGACY-HOST", tenant_id=None)
        db.add(endpoint)
        db.commit()
        endpoint_id = endpoint.id

    response = TestClient(app).post(
        "/api/v1/telemetry",
        json={
            "hostname": "LEGACY-HOST",
            "hardware_uuid": "b19f1d84-0a2c-4a34-bf95-a61ff3231c49",
            "ip_address": "192.168.0.56",
            "battery_percentage": 50,
            "charging": False,
            "ac_connected": False,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_version": "2.0.0",
        },
        headers={"Authorization": "Bearer " + global_token},
    )
    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        endpoint = db.get(Endpoint, endpoint_id)
        assert endpoint is not None
        assert endpoint.hardware_uuid == "b19f1d84-0a2c-4a34-bf95-a61ff3231c49"
        assert endpoint.hostname == "LEGACY-HOST"


def test_telemetry_stream_injects_request_without_query_parameter():
    operation = app.openapi()["paths"]["/api/v1/telemetry/stream"]["get"]

    assert operation.get("parameters", []) == []
