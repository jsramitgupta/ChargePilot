from datetime import UTC, datetime
import math
from typing import Any

from app.models.device import Device

MAX_METER_READING = 1_000_000_000_000


def normalize_meter_value(value: Any, multiplier: float) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        normalized = float(value) * multiplier
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(normalized) or normalized < 0 or normalized > MAX_METER_READING:
        return None
    return normalized


def apply_meter_result(
    device: Device,
    result: dict[str, Any],
    *,
    observed_at: datetime,
) -> None:
    if device.power_dp_id is None and device.energy_dp_id is None:
        return
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=UTC)
    observed_at = observed_at.astimezone(UTC)
    device.meter_last_sample_at = observed_at

    power_watts = (
        normalize_meter_value(result.get("power_watts"), 1.0)
        if device.power_dp_id is not None
        else None
    )
    if power_watts is not None:
        device.meter_power_watts = power_watts
        device.meter_power_sample_at = observed_at

    energy_total_kwh = (
        normalize_meter_value(result.get("energy_total_kwh"), 1.0)
        if device.energy_dp_id is not None
        else None
    )
    if energy_total_kwh is None:
        return

    month_key = observed_at.strftime("%Y-%m")
    if device.energy_counter_type == "monthly":
        if device.meter_month_key != month_key:
            device.meter_tracking_since = observed_at
        device.meter_energy_month_kwh = energy_total_kwh
        device.meter_energy_sample_at = observed_at
        device.meter_month_key = month_key
        return

    if device.meter_month_key != month_key or device.meter_energy_month_kwh is None:
        device.meter_energy_month_kwh = 0.0
        device.meter_month_key = month_key
        device.meter_energy_total_kwh = energy_total_kwh
        device.meter_energy_sample_at = observed_at
        device.meter_tracking_since = observed_at
        return

    previous_total = device.meter_energy_total_kwh
    if previous_total is None:
        device.meter_tracking_since = observed_at
    else:
        # A device reset or counter rollover starts a new accumulation segment.
        delta = energy_total_kwh - previous_total
        device.meter_energy_month_kwh += delta if delta >= 0 else energy_total_kwh
    device.meter_energy_total_kwh = energy_total_kwh
    device.meter_energy_sample_at = observed_at
