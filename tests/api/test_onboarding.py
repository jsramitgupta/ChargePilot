import base64
import sys
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.smartlife_service import SmartLifeService


def _authenticated_client(username: str, root_path: str = "") -> TestClient:
    client = TestClient(app, root_path=root_path)
    register = client.post(
        "/register",
        data={"username": username, "password": "secret123"},
        follow_redirects=False,
    )
    assert register.status_code in {200, 302, 303}, register.text
    login = client.post(
        "/login",
        data={"username": username, "password": "secret123"},
        follow_redirects=False,
    )
    assert login.status_code in {200, 302, 303}, login.text
    return client


def test_lan_scan_requires_login_and_never_returns_discovered_local_key(monkeypatch):
    client = TestClient(app)
    assert client.post("/devices/scan").status_code == 401

    class FakeTuyaService:
        async def discover(self):
            return [
                {
                    "name": "Kitchen Plug",
                    "device_id": "tuya-kitchen-001",
                    "ip_address": "192.168.1.40",
                    "local_key": "must-not-be-returned",
                    "protocol_version": "3.3",
                    "device_type": "switch",
                }
            ]

    monkeypatch.setattr("app.api.onboarding.TuyaService", FakeTuyaService)
    client = _authenticated_client("lan_scan_user")

    response = client.post("/devices/scan")
    assert response.status_code == 200, response.text
    assert response.json() == {
        "devices": [
            {
                "name": "Kitchen Plug",
                "device_id": "tuya-kitchen-001",
                "ip_address": "192.168.1.40",
                "protocol_version": "3.3",
                "device_type": "switch",
                "already_added": False,
            }
        ]
    }
    assert "must-not-be-returned" not in response.text


def test_smartlife_pairing_routes_require_login_and_keep_user_session_scoped(monkeypatch):
    client = TestClient(app)
    unauthenticated = client.post(
        "/devices/smartlife/start",
        json={"user_code": "account-code", "qr_scheme": "smartlife"},
    )
    assert unauthenticated.status_code == 401

    class FakeSmartLifeService:
        async def start_login(self, user_id, user_code, scheme):
            assert user_code == "account-code"
            assert scheme == "smartlife"
            return {"login_id": "login-1", "qr": "data:image/png;base64,ZmFrZQ=="}

        async def poll_login(self, user_id, login_id):
            assert login_id == "login-1"
            return {"status": "connected", "devices": []}

    monkeypatch.setattr("app.api.onboarding.smartlife_service", FakeSmartLifeService())
    client = _authenticated_client("smartlife_pairing_user")

    start = client.post(
        "/devices/smartlife/start",
        json={"user_code": "account-code", "qr_scheme": "smartlife"},
    )
    assert start.status_code == 200, start.text
    assert start.json()["login_id"] == "login-1"

    poll = client.get("/devices/smartlife/login-1")
    assert poll.status_code == 200, poll.text
    assert poll.json() == {"status": "connected", "devices": []}


def test_device_wizard_keeps_local_key_blank_until_user_provides_one():
    client = _authenticated_client("wizard_blank_key_user")
    page = client.get("/devices")

    assert page.status_code == 200, page.text
    assert 'id="wizard_local_key" type="password" name="encrypted_local_key" required placeholder="Blank until entered or retrieved"' in page.text
    assert "Scan local network" in page.text
    assert "Add switch manually" in page.text
    assert "Fetch with Smart Life" in page.text
    assert "Generate secure QR" in page.text
    assert "Remember this account ID on my ChargePilot account" in page.text
    assert "ChargePilot retrieves only local keys" in page.text
    assert 'data-scan-url="http://testserver/devices/scan"' in page.text
    assert "ajax.js?v=17" in page.text
    assert 'id="smartlife-modal"' in page.text
    assert page.text.index("Scan your local network") < page.text.index("Step 2 · Add")
    assert page.text.index("Step 2 · Add") < page.text.index("Configured switches")


def test_switch_controls_render_as_animated_channel_switches():
    client = _authenticated_client("animated_switches_user")
    for name, device_id, channel_count in (
        ("Single switch", "single-switch", 1),
        ("Multi switch", "multi-switch", 4),
    ):
        response = client.post(
            "/devices",
            data={
                "name": name,
                "device_id": device_id,
                "ip_address": "192.168.1.50",
                "device_type": "switch",
                "protocol_version": "3.5",
                "encrypted_local_key": "local-key",
                "channel_count": channel_count,
            },
            follow_redirects=False,
        )
        assert response.status_code == 303, response.text

    page = client.get("/devices")
    assert page.status_code == 200, page.text
    assert 'class="switch-button switch-button-master"' not in page.text
    assert page.text.count('class="switch-button switch-button-channel"') == 5
    assert 'class="channel-toggle inline-flex' not in page.text
    assert 'class="channel-panel hidden' not in page.text
    assert page.text.count('class="channel-panel mt-4 space-y-2"') == 2
    assert page.text.count('class="switch-channel-row flex') == 5
    assert 'data-state="off"' in page.text


def test_smartlife_account_id_can_be_remembered_per_user():
    client = _authenticated_client("smartlife_saved_code_user")
    unauthenticated = TestClient(app).post(
        "/devices/smartlife/preferences",
        json={"user_code": "account-code", "remember": True},
    )
    assert unauthenticated.status_code == 401

    saved = client.post(
        "/devices/smartlife/preferences",
        json={"user_code": " account-code ", "remember": True},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json() == {"saved": True}

    page = client.get("/devices")
    assert 'id="smartlife_user_code" type="text" value="account-code"' in page.text
    assert 'id="smartlife_remember_user_code" type="checkbox" class="smartlife-remember-checkbox' in page.text
    another_user_page = _authenticated_client("smartlife_other_user").get("/devices")
    assert 'id="smartlife_user_code" type="text" value="account-code"' not in another_user_page.text

    cleared = client.post(
        "/devices/smartlife/preferences",
        json={"user_code": "account-code", "remember": False},
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json() == {"saved": False}
    page_without_saved_code = client.get("/devices")
    assert 'id="smartlife_user_code" type="text" value=""' in page_without_saved_code.text


def test_device_scan_url_respects_reverse_proxy_root_path():
    client = _authenticated_client("wizard_root_path_user", root_path="/chargepilot")
    page = client.get("/devices")

    assert page.status_code == 200, page.text
    assert 'data-scan-url="http://testserver/chargepilot/devices/scan"' in page.text


@pytest.mark.asyncio
async def test_smartlife_service_returns_linked_keys_only_after_qr_confirmation(monkeypatch):
    class FakeLoginControl:
        def qr_code(self, client_id, schema, user_code):
            assert schema == "haauthorize"
            return {"success": True, "result": {"qrcode": "qr-token"}}

        def login_result(self, token, client_id, user_code):
            assert (token, user_code) == ("qr-token", "account-code")
            return True, {
                "terminal_id": "terminal",
                "endpoint": "https://tuya.example",
                "access_token": "access",
                "refresh_token": "refresh",
            }

    class FakeManager:
        def __init__(self, *args):
            self.device_map = {
                "device-1": SimpleNamespace(
                    id="device-1",
                    name="Kitchen Plug",
                    ip="192.168.1.40",
                    local_key="retrieved-key",
                )
            }

        def update_device_cache(self):
            return None

    monkeypatch.setitem(
        sys.modules,
        "tuya_sharing",
        SimpleNamespace(LoginControl=FakeLoginControl, Manager=FakeManager),
    )
    service = SmartLifeService()

    started = await service.start_login("user-1", "account-code", "smartlife")
    assert started["qr"].startswith("data:image/png;base64,")
    png_bytes = base64.b64decode(started["qr"].split(",", maxsplit=1)[1])
    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")

    connected = await service.poll_login("user-1", started["login_id"])
    assert connected == {
        "status": "connected",
        "devices": [
            {
                "device_id": "device-1",
                "local_key": "retrieved-key",
            }
        ],
    }
    assert await service.poll_login("user-1", started["login_id"]) == connected
    with pytest.raises(KeyError):
        await service.poll_login("user-2", started["login_id"])
