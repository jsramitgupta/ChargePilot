from datetime import datetime, timedelta, timezone

from app.services.rule_engine import evaluate_battery_action


def test_battery_turns_on_when_below_threshold_and_switch_is_off():
    action = evaluate_battery_action(
        battery=15,
        current_state=False,
        on_threshold=20,
        off_threshold=99,
        minimum_interval_seconds=300,
        last_state_change_at=None,
    )

    assert action == "TURN_ON"


def test_battery_turns_off_when_above_threshold_and_switch_is_on():
    action = evaluate_battery_action(
        battery=99,
        current_state=True,
        on_threshold=20,
        off_threshold=99,
        minimum_interval_seconds=300,
        last_state_change_at=None,
    )

    assert action == "TURN_OFF"


def test_rule_engine_is_idempotent_and_respects_hysteresis():
    action = evaluate_battery_action(
        battery=50,
        current_state=False,
        on_threshold=20,
        off_threshold=99,
        minimum_interval_seconds=300,
        last_state_change_at=None,
    )

    assert action == "NO_ACTION"

    recent_change = datetime.now(timezone.utc) - timedelta(minutes=2)
    action = evaluate_battery_action(
        battery=15,
        current_state=False,
        on_threshold=20,
        off_threshold=99,
        minimum_interval_seconds=300,
        last_state_change_at=recent_change,
    )

    assert action == "NO_ACTION"


def test_turn_on_can_be_disabled_without_disabling_turn_off():
    assert evaluate_battery_action(
        battery=10,
        current_state=False,
        turn_on_enabled=False,
        on_threshold=20,
        off_threshold=99,
    ) == "NO_ACTION"
    assert evaluate_battery_action(
        battery=99,
        current_state=True,
        turn_on_enabled=False,
        on_threshold=20,
        off_threshold=99,
    ) == "TURN_OFF"


def test_charging_completion_cutoff_requires_charging_and_respects_cooldown():
    options = {
        "battery": 85,
        "current_state": True,
        "turn_off_when_charging_enabled": True,
        "charging_off_threshold": 85,
        "off_threshold": 99,
    }
    assert evaluate_battery_action(**options, is_charging=False) == "NO_ACTION"
    assert evaluate_battery_action(**options, is_charging=True) == "TURN_OFF"
    assert evaluate_battery_action(
        **options,
        is_charging=True,
        last_state_change_at=datetime.now(timezone.utc) - timedelta(seconds=30),
        minimum_interval_seconds=300,
    ) == "NO_ACTION"


def test_disabled_charging_completion_cutoff_keeps_existing_off_threshold():
    assert evaluate_battery_action(
        battery=85,
        current_state=True,
        turn_off_when_charging_enabled=False,
        charging_off_threshold=85,
        off_threshold=99,
        is_charging=True,
    ) == "NO_ACTION"
    assert evaluate_battery_action(
        battery=99,
        current_state=True,
        turn_off_when_charging_enabled=False,
        charging_off_threshold=85,
        off_threshold=99,
        is_charging=False,
    ) == "TURN_OFF"
