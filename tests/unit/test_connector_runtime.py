import pytest

from connector import chargepilot_connector


def test_config_path_uses_explicit_container_mount(monkeypatch, tmp_path):
    configured_path = tmp_path / "persistent" / "connector-config.json"
    monkeypatch.setenv("CHARGEPILOT_CONNECTOR_CONFIG", str(configured_path))

    assert chargepilot_connector._config_path() == configured_path


class _FakeDevice:
    def __init__(self, state):
        self.state = state
        self.commanded_state = None

    def turn_on(self, *, switch):
        assert switch == 1
        self.commanded_state = True
        return {"success": True}

    def turn_off(self, *, switch):
        assert switch == 1
        self.commanded_state = False
        return {"success": True}

    def status(self, *, switch):
        assert switch == 1
        return {"dps": {"1": self.state}}


@pytest.mark.parametrize(
    ("value", "expected"),
    [(True, True), (False, False), ("ON", True), ("off", False), (1, True), (0, False)],
)
def test_switch_state_coerces_common_tuya_values(value, expected):
    assert chargepilot_connector._switch_state(value) is expected


def test_connector_reports_set_state_only_after_readback(monkeypatch):
    device = _FakeDevice("true")
    monkeypatch.setattr(chargepilot_connector, "OutletDevice", lambda *args, **kwargs: device)
    result = chargepilot_connector._execute_device_command(
        {
            "operation": "set_state",
            "desired_state": True,
            "device": {
                "device_id": "test-device",
                "ip_address": "192.168.1.2",
                "local_key": "secret",
            },
        }
    )

    assert device.commanded_state is True
    assert result == {"state": True}


def test_connector_fails_when_device_readback_does_not_match_desired_state(monkeypatch):
    device = _FakeDevice(False)
    monkeypatch.setattr(chargepilot_connector, "OutletDevice", lambda *args, **kwargs: device)

    with pytest.raises(RuntimeError, match="did not report the requested state"):
        chargepilot_connector._execute_device_command(
            {
                "operation": "set_state",
                "desired_state": True,
                "device": {
                    "device_id": "test-device",
                    "ip_address": "192.168.1.2",
                    "local_key": "secret",
                },
            }
        )


def test_connector_does_not_treat_another_channel_as_requested_channel():
    device = _FakeDevice(True)
    device.status = lambda *, switch: {"dps": {"1": True}}

    with pytest.raises(RuntimeError, match="unsupported channel state"):
        chargepilot_connector._read_device_state(device, 2)


@pytest.mark.parametrize(
    "url",
    ["https://chargepilot.example", "http://localhost:8000", "http://127.0.0.1:8000"],
)
def test_server_url_allows_https_and_loopback_development(url):
    assert chargepilot_connector._validate_server_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "http://chargepilot.example",
        "https://user:password@chargepilot.example",
        "https://chargepilot.example?token=secret",
    ],
)
def test_server_url_rejects_insecure_or_ambiguous_urls(url):
    with pytest.raises(ValueError):
        chargepilot_connector._validate_server_url(url)
