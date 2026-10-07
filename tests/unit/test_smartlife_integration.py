from app.services.smartlife_service import SmartLifeService


def test_smartlife_device_mapping_uses_local_key_and_ip():
    raw_device = {
        "id": "abc123",
        "name": "Living Room Plug",
        "status": {"online": True},
        "local_key": "local-key-456",
        "ip": "192.168.1.22",
        "category": "cj",
        "model": "model-x",
        "product_id": "prod-1",
        "product_name": "Smart Plug",
        "protocol_version": "3.5",
    }

    device = SmartLifeService.normalize_device(raw_device)

    assert device["device_id"] == "abc123"
    assert device["name"] == "Living Room Plug"
    assert device["encrypted_local_key"] == "local-key-456"
    assert device["ip_address"] == "192.168.1.22"
    assert device["device_type"] == "switch"
    assert device["protocol_version"] == "3.5"
