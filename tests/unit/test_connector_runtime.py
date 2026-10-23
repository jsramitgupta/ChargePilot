import asyncio
import sys

import pytest

from connector import chargepilot_connector


def test_config_path_uses_explicit_container_mount(monkeypatch, tmp_path):
    configured_path = tmp_path / "persistent" / "connector-config.json"
    monkeypatch.setenv("CHARGEPILOT_CONNECTOR_CONFIG", str(configured_path))

    assert chargepilot_connector._config_path() == configured_path


def test_main_reads_enrollment_code_from_environment(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setattr(
        chargepilot_connector,
        "run_connector",
        lambda server_url, enrollment_code, config_path: captured.update(
            server_url=server_url, enrollment_code=enrollment_code, config_path=config_path
        ),
    )
    monkeypatch.setattr(asyncio, "run", lambda coroutine: coroutine)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "chargepilot-connector",
            "--server-url",
            "https://chargepilot.example",
            "--config",
            str(tmp_path / "config.json"),
        ],
    )
    monkeypatch.setenv("CHARGEPILOT_CONNECTOR_ENROLLMENT_CODE", "one-time-code")

    chargepilot_connector.main()

    assert captured["enrollment_code"] == "one-time-code"
    assert captured["config_path"] == tmp_path / "config.json"
    assert "CHARGEPILOT_CONNECTOR_ENROLLMENT_CODE" not in chargepilot_connector.os.environ


def test_first_enrollment_without_environment_or_tty_fails_clearly(monkeypatch, tmp_path):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)

    with pytest.raises(ValueError, match="CHARGEPILOT_CONNECTOR_ENROLLMENT_CODE"):
        asyncio.run(
            chargepilot_connector.run_connector(
                "https://chargepilot.example",
                None,
                tmp_path / "config.json",
            )
        )


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

    def status(self):
        dps = self.state if isinstance(self.state, dict) else {"1": self.state}
        return {"dps": dps}


@pytest.mark.parametrize(
    ("value", "expected"),
    [(True, True), (False, False), ("ON", True), ("off", False), (1, True), (0, False)],
)
def test_switch_state_coerces_common_tuya_values(value, expected):
    assert chargepilot_connector._switch_state(value) is expected


def test_connector_reports_set_state_only_after_readback(monkeypatch):
    device = _FakeDevice("true")
    constructed_device_types = []

    def build_device(*args, **kwargs):
        constructed_device_types.append(args[3])
        return device

    monkeypatch.setattr(chargepilot_connector, "OutletDevice", build_device)
    result = chargepilot_connector._execute_device_command(
        {
            "operation": "set_state",
            "desired_state": True,
            "device": {
                "device_id": "test-device",
                "ip_address": "192.168.1.2",
                "local_key": "secret",
                "device_type": "switch",
            },
        }
    )

    assert constructed_device_types == ["default"]
    assert device.commanded_state is True
    assert result == {"state": True}


@pytest.mark.parametrize("device_type", ["switch", "plug", "outlet", "default", None, ""])
def test_connector_normalizes_generic_device_types(device_type):
    assert chargepilot_connector._normalize_device_type(device_type) == "default"


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

    with pytest.raises(RuntimeError, match="unsupported channel state"):
        chargepilot_connector._read_device_state(device, 2)


def test_connector_reads_selected_channel_from_unfiltered_status():
    device = _FakeDevice({"1": False, "2": True})

    assert chargepilot_connector._read_device_state(device, 2) is True


def test_connector_returns_only_configured_meter_datapoints(monkeypatch):
    device = _FakeDevice({"1": True, "cur_power": "845", "add_ele": "12500", "other": "secret"})
    monkeypatch.setattr(chargepilot_connector, "OutletDevice", lambda *args, **kwargs: device)

    result = chargepilot_connector._execute_device_command(
        {
            "operation": "get_status",
            "device": {
                "device_id": "metered-device",
                "ip_address": "192.168.1.15",
                "local_key": "not-returned",
                "power_dp_id": "cur_power",
                "power_multiplier": 0.1,
                "energy_dp_id": "add_ele",
                "energy_multiplier": 0.001,
            },
        }
    )

    assert result == {"state": True, "power_watts": 84.5, "energy_total_kwh": 12.5}


def test_connector_ignores_invalid_meter_datapoint_values(monkeypatch):
    device = _FakeDevice({"1": False, "cur_power": True, "add_ele": "not-numeric"})
    monkeypatch.setattr(chargepilot_connector, "OutletDevice", lambda *args, **kwargs: device)

    result = chargepilot_connector._execute_device_command(
        {
            "operation": "get_status",
            "device": {
                "device_id": "metered-device",
                "ip_address": "192.168.1.15",
                "local_key": "not-returned",
                "power_dp_id": "cur_power",
                "energy_dp_id": "add_ele",
            },
        }
    )

    assert result == {"state": False}


def test_connector_meter_inspection_returns_bounded_numeric_candidates(monkeypatch):
    device = _FakeDevice(
        {
            "1": True,
            "cur_power": "845",
            "add_ele": "12500",
            "other": 17,
            "private_text": "secret",
            "nested": {"value": 3},
            "bad_number": float("nan"),
        }
    )
    monkeypatch.setattr(chargepilot_connector, "OutletDevice", lambda *args, **kwargs: device)

    result = chargepilot_connector._execute_device_command(
        {
            "operation": "inspect_meter",
            "device": {
                "device_id": "metered-device",
                "ip_address": "192.168.1.15",
                "local_key": "not-returned",
            },
        }
    )

    assert result == {
        "candidates": [
            {"id": "cur_power", "label": "Power reading", "sample": 845.0, "suggested_role": "power"},
            {"id": "add_ele", "label": "Energy reading", "sample": 12500.0, "suggested_role": "energy"},
            {"id": "other", "label": "Other reading", "sample": 17.0, "suggested_role": None},
        ]
    }


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
