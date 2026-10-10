from unittest.mock import patch

import pytest

from app.services.tuya_service import TuyaService


@pytest.mark.asyncio
async def test_discover_retries_after_socket_address_in_use_error():
    calls = {"count": 0}

    def fake_device_scan(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise OSError(10048, "Only one usage of each socket address is normally permitted")
        return {
            "abc123": {
                "ip": "192.168.1.42",
                "device_id": "abc123",
                "localKey": "local-key-123",
                "version": 3.5,
                "name": "Bedroom Plug",
            }
        }

    with patch("app.services.tuya_service.deviceScan", side_effect=fake_device_scan):
        discovered = await TuyaService().discover()

    assert len(discovered) == 1
    assert discovered[0]["device_id"] == "abc123"
    assert calls["count"] == 2


@pytest.mark.asyncio
async def test_discover_surfaces_network_scan_failures():
    with patch(
        "app.services.tuya_service.deviceScan",
        side_effect=RuntimeError("network unavailable"),
    ):
        with pytest.raises(RuntimeError, match="TinyTuya local network scan failed"):
            await TuyaService().discover()
