from datetime import UTC, datetime

import pytest

from app.models.device import Device
from app.services.tuya_energy import apply_meter_result, normalize_meter_value


def _device(**overrides) -> Device:
    values = {
        "name": "Metered plug",
        "device_id": "metered-plug",
        "encrypted_local_key": "encrypted",
        "power_dp_id": "cur_power",
        "power_multiplier": 1.0,
        "energy_dp_id": "add_ele",
        "energy_multiplier": 0.001,
        "energy_counter_type": "cumulative",
    }
    values.update(overrides)
    return Device(**values)


@pytest.mark.parametrize(
    ("value", "multiplier", "expected"),
    [
        ("1250", 0.001, 1.25),
        (2.5, 2, 5.0),
        (True, 1, None),
        ("NaN", 1, None),
        ("invalid", 1, None),
        (-1, 1, None),
        (1_000_000_000_001, 1, None),
        (None, 1, None),
    ],
)
def test_normalize_meter_value_accepts_finite_nonnegative_numbers(value, multiplier, expected):
    assert normalize_meter_value(value, multiplier) == expected


def test_cumulative_energy_accumulates_monthly_deltas_and_handles_counter_reset():
    device = _device()
    apply_meter_result(
        device,
        {"power_watts": "56.4", "energy_total_kwh": 12.0},
        observed_at=datetime(2026, 10, 2, 8, tzinfo=UTC),
    )
    assert device.meter_power_watts == 56.4
    assert device.meter_energy_month_kwh == 0

    apply_meter_result(
        device,
        {"power_watts": 60, "energy_total_kwh": 12.7},
        observed_at=datetime(2026, 10, 2, 9, tzinfo=UTC),
    )
    assert device.meter_energy_month_kwh == pytest.approx(0.7)

    apply_meter_result(
        device,
        {"energy_total_kwh": 0.2},
        observed_at=datetime(2026, 10, 2, 10, tzinfo=UTC),
    )
    assert device.meter_energy_month_kwh == pytest.approx(0.9)
    assert device.meter_energy_total_kwh == 0.2


def test_energy_counter_rolls_over_at_utc_month_boundary():
    device = _device()
    apply_meter_result(device, {"energy_total_kwh": 10}, observed_at=datetime(2026, 10, 31, 23, 59, tzinfo=UTC))
    apply_meter_result(device, {"energy_total_kwh": 10.4}, observed_at=datetime(2026, 11, 1, 0, 1, tzinfo=UTC))

    assert device.meter_month_key == "2026-11"
    assert device.meter_energy_month_kwh == 0
    assert device.meter_energy_total_kwh == 10.4
    assert device.meter_tracking_since == datetime(2026, 11, 1, 0, 1, tzinfo=UTC)


def test_monthly_counter_uses_device_reported_month_value():
    device = _device(energy_counter_type="monthly")
    apply_meter_result(device, {"energy_total_kwh": 4.75}, observed_at=datetime(2026, 10, 4, tzinfo=UTC))
    apply_meter_result(device, {"energy_total_kwh": 5.1}, observed_at=datetime(2026, 10, 5, tzinfo=UTC))

    assert device.meter_energy_month_kwh == pytest.approx(5.1)
    assert device.meter_tracking_since == datetime(2026, 10, 4, tzinfo=UTC)


def test_unconfigured_datapoints_do_not_accept_meter_values():
    device = _device(power_dp_id=None, energy_dp_id=None)
    apply_meter_result(
        device,
        {"power_watts": 100, "energy_total_kwh": 2},
        observed_at=datetime(2026, 10, 2, tzinfo=UTC),
    )

    assert device.meter_power_watts is None
    assert device.meter_energy_month_kwh is None
    assert device.meter_last_sample_at is None


def test_invalid_meter_sample_does_not_refresh_last_valid_reading_timestamps():
    device = _device()
    valid_time = datetime(2026, 10, 2, 8, tzinfo=UTC)
    invalid_time = datetime(2026, 10, 2, 9, tzinfo=UTC)
    apply_meter_result(
        device,
        {"power_watts": 25, "energy_total_kwh": 3},
        observed_at=valid_time,
    )

    apply_meter_result(
        device,
        {"power_watts": True, "energy_total_kwh": "unavailable"},
        observed_at=invalid_time,
    )

    assert device.meter_power_watts == 25
    assert device.meter_power_sample_at == valid_time
    assert device.meter_energy_sample_at == valid_time
    assert device.meter_last_sample_at == invalid_time
