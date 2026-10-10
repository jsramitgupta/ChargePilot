import json
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_full_api_flow():
    # Health
    r = client.get("/health")
    assert r.status_code == 200
    r = client.get("/ready")
    assert r.status_code == 200

    # Login with default admin user created by ensure_default_admin_user
    resp = client.post("/login", data={"username": "admin", "password": "change-me"}, allow_redirects=False)
    assert resp.status_code == 303

    # Auth/me should now succeed
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 200
    body = r.json()
    assert body.get("username") == "admin"

    # Create a device
    device_payload = {
        "name": "Test Device",
        "device_id": "dev-1",
        "encrypted_local_key": "key",
        "ip_address": "192.0.2.1",
        "device_type": "plug",
        "protocol_version": "3.5",
        "enabled": True,
    }
    r = client.post("/api/v1/devices", json=device_payload)
    assert r.status_code == 201, r.text
    device = r.json()
    assert device["device_id"] == "dev-1"
    device_id = device["id"]

    # Create a device channel
    channel_payload = {"channel_index": 1, "name": "Channel 1", "dp_id": "1", "enabled": True}
    r = client.post(f"/api/v1/devices/{device_id}/channels", json=channel_payload)
    assert r.status_code == 201
    channel = r.json()
    channel_id = channel["id"]

    # List devices
    r = client.get("/api/v1/devices")
    assert r.status_code == 200
    devices = r.json()
    assert any(d["device_id"] == "dev-1" for d in devices)

    # Create an endpoint
    endpoint_payload = {"hostname": "host-1", "ip_address": "198.51.100.2", "battery_percentage": 50}
    r = client.post("/api/v1/endpoints", json=endpoint_payload)
    assert r.status_code == 201
    endpoint = r.json()
    endpoint_id = endpoint["id"]

    # Readings (empty list expected)
    r = client.get(f"/api/v1/endpoints/{endpoint_id}/readings")
    assert r.status_code == 200
    assert r.json().get("endpoint_id") == endpoint_id

    # Ensure agent-config by id works (no auth required)
    r = client.get(f"/api/v1/endpoints/{endpoint_id}/agent-config")
    assert r.status_code == 200
    assert r.json().get("endpoint_id") == endpoint_id

    # Create a mapping between endpoint and device
    mapping_payload = {
        "endpoint_id": endpoint_id,
        "device_id": device_id,
        "channel_id": channel_id,
        "enabled": True,
        "on_threshold": 30,
        "off_threshold": 90,
        "minimum_state_change_interval": 300,
    }
    r = client.post("/api/v1/mappings", json=mapping_payload)
    assert r.status_code == 201, r.text
    mapping = r.json()
    mapping_id = mapping["id"]

    # Duplicate mapping attempt should return 409
    r = client.post("/api/v1/mappings", json=mapping_payload)
    assert r.status_code == 409

    # List mappings and ensure our mapping is present
    r = client.get("/api/v1/mappings")
    assert r.status_code == 200
    mappings = r.json()
    assert any(m["id"] == mapping_id for m in mappings)

    # Get mapping by id
    r = client.get(f"/api/v1/mappings/{mapping_id}")
    assert r.status_code == 200

    # Update mapping (change thresholds)
    r = client.put(f"/api/v1/mappings/{mapping_id}", json={"on_threshold": 40, "off_threshold": 95})
    assert r.status_code == 200
    updated = r.json()
    assert updated["on_threshold"] == 40

    # Delete mapping
    r = client.delete(f"/api/v1/mappings/{mapping_id}")
    assert r.status_code == 204

    # Ensure mapping is deleted
    r = client.get(f"/api/v1/mappings/{mapping_id}")
    assert r.status_code == 404

    # Events list works
    r = client.get("/api/v1/events")
    assert r.status_code == 200
