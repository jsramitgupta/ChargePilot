import base64
import sys
from types import SimpleNamespace
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.api import onboarding
from app.core.database import SessionLocal
from app.main import app
from app.models.connector import SiteConnector
from app.models.user import User
from app.services.connector_service import finalize_command, hash_connector_token, queue_discovery_command
from app.services.smartlife_service import SmartLifeService
from conftest import register_tenant_admin


def _authenticated_client(username: str, root_path: str = "") -> TestClient:
    client = TestClient(app, root_path=root_path)
    register_tenant_admin(client, username, "secret12345678")
    return client


def test_lan_scan_defaults_to_chargepilot_server_network_and_redacts_local_keys(monkeypatch):
    client = TestClient(app)
    assert client.post("/devices/scan").status_code == 401
    client = _authenticated_client("lan_scan_user")

    class FakeTuyaService:
        async def discover(self):
            return [
                {
                    "name": "Server LAN plug",
                    "device_id": "server-lan-plug",
                    "ip_address": "192.168.1.25",
                    "protocol_version": "3.5",
                    "device_type": "switch",
                    "local_key": "must-not-be-returned",
                }
            ]

    monkeypatch.setattr(onboarding, "TuyaService", FakeTuyaService)
    response = client.post("/devices/scan", json={"source": "server"})

    assert response.status_code == 200, response.text
    assert response.json()["devices"] == [
        {
            "name": "Server LAN plug",
            "device_id": "server-lan-plug",
            "ip_address": "192.168.1.25",
            "protocol_version": "3.5",
            "device_type": "switch",
            "already_added": False,
        }
    ]
    connector_scan = client.post(
        "/devices/scan",
        json={"source": "connector", "connector_id": "missing-connector"},
    )
    assert connector_scan.status_code == 503
    assert "No active site connector is online" in connector_scan.json()["detail"]


def test_lan_scan_returns_connector_metadata_without_local_keys(monkeypatch):
    client = TestClient(app)
    register_tenant_admin(client, "lan_scan_connector_user", "lan-scan-connector-password", "LAN scan site")
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == "lan_scan_connector_user").one()
        connector = SiteConnector(
            tenant_id=user.tenant_id,
            name="LAN scan connector",
            token_hash=hash_connector_token("lan-scan-connector-token"),
            last_seen_at=datetime.now(UTC),
        )
        db.add(connector)
        db.commit()
        connector_id = connector.id

    original_queue = queue_discovery_command

    def complete_discovery(db, connector):
        command = original_queue(db, connector)
        finalize_command(
            db,
            command,
            success=True,
            result={
                "devices": [
                    {
                        "name": "LAN plug",
                        "device_id": "lan-plug-id",
                        "ip_address": "192.168.1.25",
                        "protocol_version": "3.5",
                        "device_type": "switch",
                        "local_key": "must-not-be-returned",
                    }
                ]
            },
        )
        return command

    monkeypatch.setattr(onboarding, "queue_discovery_command", complete_discovery)
    response = client.post(
        "/devices/scan",
        json={"source": "connector", "connector_id": connector_id},
    )

    assert response.status_code == 200, response.text
    assert response.json()["devices"] == [
        {
            "name": "LAN plug",
            "device_id": "lan-plug-id",
            "ip_address": "192.168.1.25",
            "protocol_version": "3.5",
            "device_type": "switch",
            "already_added": False,
        }
    ]


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


def test_device_wizard_route_redirects_to_react_and_scan_api_remains_available():
    client = _authenticated_client("wizard_blank_key_user")
    page = client.get("/devices", follow_redirects=False)
    assert page.status_code == 307
    assert page.headers["location"] == "/devices"
    scan = client.post("/devices/scan", json={"source": "connector"})
    assert scan.status_code == 503


def test_switches_and_channels_are_created_through_json_api():
    client = _authenticated_client("animated_switches_user")
    for name, device_id, channel_count in (
        ("Single switch", "single-switch", 1),
        ("Multi switch", "multi-switch", 4),
    ):
        response = client.post(
            "/api/v1/devices",
            json={
                "name": name,
                "device_id": device_id,
                "ip_address": "192.168.1.50",
                "device_type": "switch",
                "protocol_version": "3.5",
                "encrypted_local_key": "local-key",
            },
        )
        assert response.status_code == 201, response.text
        device = response.json()
        for channel_index in range(1, channel_count + 1):
            channel = client.post(
                f"/api/v1/devices/{device['id']}/channels",
                json={
                    "channel_index": channel_index,
                    "name": f"Channel {channel_index}",
                    "dp_id": str(channel_index),
                },
            )
            assert channel.status_code == 201, channel.text
        assert len(client.get(f"/api/v1/devices/{device['id']}/channels").json()) == channel_count


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
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == "smartlife_saved_code_user").one()
        assert user.smartlife_user_code == "account-code"
    _authenticated_client("smartlife_other_user")
    with SessionLocal() as db:
        other_user = db.query(User).filter(User.username == "smartlife_other_user").one()
        assert other_user.smartlife_user_code is None

    cleared = client.post(
        "/devices/smartlife/preferences",
        json={"user_code": "account-code", "remember": False},
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json() == {"saved": False}
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == "smartlife_saved_code_user").one()
        assert user.smartlife_user_code is None


def test_device_scan_url_respects_reverse_proxy_root_path():
    client = _authenticated_client("wizard_root_path_user", root_path="/chargepilot")
    page = client.get("/devices", follow_redirects=False)

    assert page.status_code == 307, page.text
    assert page.headers["location"] == "/devices"


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
