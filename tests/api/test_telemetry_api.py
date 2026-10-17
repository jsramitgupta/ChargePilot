from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.models.endpoint import Endpoint
from app.main import app
from app.models.messaging import TelemetryOutbox


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
