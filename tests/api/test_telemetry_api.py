from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app


def test_telemetry_route_accepts_valid_endpoint():
    client = TestClient(app)
    response = client.post(
        "/api/v1/telemetry",
        json={
            "hostname": "LAPTOP-001",
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


def test_telemetry_stream_injects_request_without_query_parameter():
    operation = app.openapi()["paths"]["/api/v1/telemetry/stream"]["get"]

    assert operation.get("parameters", []) == []
