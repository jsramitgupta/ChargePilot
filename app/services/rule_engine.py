from datetime import datetime, timedelta, timezone


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def evaluate_battery_action(
    *,
    battery: int,
    current_state: bool,
    on_threshold: int = 79,
    off_threshold: int = 99,
    minimum_interval_seconds: int = 300,
    last_state_change_at: datetime | None = None,
    now: datetime | None = None,
) -> str:
    if not 0 <= battery <= 100:
        raise ValueError("Battery percentage must be between 0 and 100.")

    if on_threshold >= off_threshold:
        effective_on_threshold = max(0, off_threshold - 20)
    else:
        effective_on_threshold = on_threshold

    now = _as_utc(now) if now is not None else datetime.now(timezone.utc)
    last_state_change_at = _as_utc(last_state_change_at)

    if (
        last_state_change_at is not None
        and now - last_state_change_at < timedelta(seconds=minimum_interval_seconds)
    ):
        return "NO_ACTION"

    if current_state:
        if battery >= off_threshold:
            return "TURN_OFF"
        return "NO_ACTION"

    if battery <= effective_on_threshold:
        return "TURN_ON"

    return "NO_ACTION"
