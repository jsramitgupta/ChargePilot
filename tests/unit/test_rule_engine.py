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
