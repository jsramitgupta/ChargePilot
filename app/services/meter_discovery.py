import math
import re
from typing import Any


_POWER_NAMES = {"activepower", "curpower", "power", "powerw", "watt", "watts"}
_ENERGY_NAMES = {
    "addele",
    "electricenergy",
    "electricity",
    "energy",
    "energykwh",
    "energytotal",
    "totalenergy",
}


def meter_candidates(dps: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for raw_id, raw_value in dps.items():
        dp_id = str(raw_id).strip()
        if not dp_id or len(dp_id) > 50 or isinstance(raw_value, bool):
            continue
        if not isinstance(raw_value, (int, float, str)):
            continue
        try:
            sample = float(raw_value)
        except (TypeError, ValueError, OverflowError):
            continue
        if not math.isfinite(sample) or sample < 0 or sample > 1_000_000_000_000:
            continue

        normalized_id = re.sub(r"[^a-z0-9]", "", dp_id.lower())
        role = (
            "power"
            if normalized_id in _POWER_NAMES
            else "energy"
            if normalized_id in _ENERGY_NAMES
            else None
        )
        candidates.append(
            {
                "id": dp_id,
                "label": "Power reading" if role == "power" else "Energy reading" if role == "energy" else "Other reading",
                "sample": sample,
                "suggested_role": role,
            }
        )
        if len(candidates) == 32:
            break
    return candidates
