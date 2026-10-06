# Technical Design Level (TLD)

## 1. Scope

This document captures the current code-level technical design of the repository. It describes the relevant modules, runtime flow, persistence model, and operational constraints that a future agent or maintainer must understand.

## 2. Technology stack

The repository currently uses:

- Python 3.12+
- FastAPI
- SQLAlchemy 2.x
- PostgreSQL via psycopg
- Pydantic + pydantic-settings
- TinyTuya
- Jinja2 templates
- pytest
- Docker Compose

## 3. Module-level responsibilities

### 3.1 `app/main.py`

This is the entrypoint of the app. It:

- creates the FastAPI application object
- calls `create_db_and_tables()` at import/startup time
- mounts static files from `app/static`
- registers the API routers under `/api/v1`
- serves the dashboard and list pages via Jinja templates

It is also the place where the app renders high-level HTML views for endpoints, device management, mappings, and events.

### 3.2 `app/core/config.py`

The settings object is built from `.env` values and env prefix `CHARGEPILOT_`.

Important fields in `Settings`:

- `app_name`
- `environment`
- `secret_key`
- `database_url`
- `encryption_key`
- `admin_username`
- `admin_password`
- `telemetry_rate_limit_per_minute`
- `endpoint_offline_timeout_seconds`
- `api_v1_prefix`

### 3.3 `app/core/database.py`

This module does the database bootstrap and session wiring:

- creates `engine`
- builds `SessionLocal`
- creates all tables on startup
- calls `_ensure_table_columns()` to patch schema drift for fields such as `current_state`, `updated_at`, and `enabled`

### 3.4 `app/services/rule_engine.py`

This module implements battery hysteresis and cooldown behavior.

Key logic:

```python
if current_state and battery >= off_threshold:
    TURN_OFF
elif not current_state and battery <= on_threshold:
    TURN_ON
else:
    NO_ACTION
```

The implementation also checks a minimum state-change interval before allowing a new state transition.

### 3.5 `app/services/tuya_service.py`

This is the device abstraction layer for the local hardware controller.

It provides:

- `discover()` using `tinytuya.deviceScan()`
- `_extract_dps()` to parse nested DPS payloads
- `get_status()` to read current state from a switch
- `turn_on()` / `turn_off()` / `set_state()` wrappers
- structured logging around device requests and responses

A key design choice is that the app does not assume a flat boolean state; it explicitly accounts for `dps`, `data.dps`, and `status` objects.

### 3.6 `app/api/telemetry.py`

This is the main automation route. It validates telemetry, updates the endpoint, resolves mappings, and chooses the action to take.

Important behaviors:

- rejects missing or invalid bearer token
- rejects telemetry older than 10 minutes
- upserts endpoint state by hostname
- loads active `Mapping` rows
- reads current device state bottom-up from Tuya
- applies `switch_state` override when present
- calls `evaluate_battery_action()` otherwise
- writes `AutomationEvent` records after a decision

## 4. Persistence model

### `Endpoint`

Represents a laptop or telemetry source.

Key fields:

- `hostname`
- `ip_address`
- `battery_percentage`
- `charging`
- `ac_connected`
- `last_seen_at`
- `agent_version`
- `enabled`
- `updated_at`

### `Device`

Represents a Tuya switch or outlet.

Key fields:

- `device_id`
- `encrypted_local_key`
- `ip_address`
- `device_type`
- `protocol_version`
- `enabled`
- `current_state`
- `last_state_change_at`

### `DeviceChannel`

Represents a channel or output index on a multi-gang device.

Key fields:

- `device_id`
- `channel_index`
- `name`
- `dp_id`
- `enabled`
- `current_state`

### `Mapping`

Links an endpoint to a device and optionally to a channel.

Key fields:

- `endpoint_id`
- `device_id`
- `channel_id`
- `on_threshold`
- `off_threshold`
- `minimum_state_change_interval`
- `enabled`

### `AutomationEvent`

Stores audit data about state changes and failures.

Key fields:

- `event_type`
- `reason`
- `previous_state`
- `new_state`
- `success`
- `error`

## 5. Request lifecycle

High-level lifecycle of the core automation path:

```text
PowerShell agent
  -> POST /api/v1/telemetry
  -> validate Authorization header
  -> validate timestamp freshness
  -> upsert Endpoint row
  -> load Mapping rows
  -> read current device state
  -> evaluate target state via rule_engine
  -> call TuyaService.set_state()
  -> persist device state
  -> persist AutomationEvent
```

## 6. Concurrency and operational constraints

- `TuyaService.discover()` uses an `asyncio.Lock` to serialize scan activity.
- Device control decisions are evaluated per endpoint mapping, not globally.
- The database is expected to be available at startup; schema creation is automated.
- Local device state is read before command execution to minimize repeated toggles and avoid stale assumptions.

## 7. Security and production-readiness notes

The current production posture is intentionally minimal:

- bearer-token validation is implemented as a static comparison against a known token value
- secrets are expected to be stored via environment variables
- local device keys are not sanitized in logs beyond hide markers in the Tuya service

This means the project is a functioning self-hosted prototype, but it should not be treated as fundamentally hardened against adversarial access.

## 8. Test strategy in the repo

The included tests focus on:

- battery threshold behavior
- hysteresis and cooldown logic
- CRUD flows for device mapping behavior

Notable test file:

- `tests/unit/test_rule_engine.py`

These tests validate the battery logic and should remain the canonical regression tests for threshold behavior.

## 9. Guidance for future rebuilds

- Keep the rule engine separate from the API layer.
- Keep all TinyTuya logic inside `TuyaService`.
- Preserve event auditing.
- Maintain explicit channel semantics for multi-gang devices.
- Treat live hardware payload structure as a compatibility concern, not a fixed assumption.
