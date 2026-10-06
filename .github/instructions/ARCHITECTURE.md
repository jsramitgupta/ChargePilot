# Architecture Overview

## 1. Architectural style

ChargePilot is implemented as a modular monolith in Python with a FastAPI application. The code is split into API, core, models, schemas, and services, but it remains a single deployable process.

This is a deliberate choice for a local-first hardware automation system: the app is simple to operate, easier to debug, and does not require a multi-service orchestrator for the first implementation.

## 2. Runtime topology

```text
Windows laptop
  ↓
Battery agent (PowerShell)
  ↓
POST /api/v1/telemetry
  ↓
FastAPI app
  ├─ validates endpoint bearer token
  ├─ loads or creates endpoint record
  ├─ resolves active mappings
  ├─ evaluates battery rule
  ├─ calls TinyTuya wrapper
  └─ persists automation event
  ↓
Local Tuya switch or plug
```

## 3. Application modules

### 3.1 API layer

The router modules are in `app/api/`:

- `health.py` — `/health` and `/ready`
- `telemetry.py` — battery telemetry intake and rule execution
- `endpoints.py` — endpoint listing
- `devices.py` — device CRUD and channel management
- `mappings.py` — endpoint-to-device mapping CRUD
- `events.py` — automation event retrieval

### 3.2 Core layer

The core modules manage environment and runtime initialization:

- `app/main.py` — app bootstrap, router registration, dashboard HTML pages
- `app/core/config.py` — `Settings` model and env prefix `CHARGEPILOT_`
- `app/core/database.py` — SQLAlchemy engine, schema creation, compatibility column checks
- `app/core/security.py` — bearer token extraction and helper functions for token hashing and verification

### 3.3 Data model layer

The ORM is defined in `app/models/`:

- `Endpoint` — laptop identity, battery telemetry, last-seen timestamp
- `Device` — Tuya switch metadata and aggregate state
- `DeviceChannel` — multi-gang / multi-switch channel metadata
- `Mapping` — endpoint-to-device and threshold configuration
- `AutomationEvent` — audit trail of actions and outcomes

### 3.4 Service layer

The service modules provide domain logic:

- `app/services/rule_engine.py` — hysteresis logic and cooldown evaluation
- `app/services/tuya_service.py` — TinyTuya encapsulation for status, discovery, and on/off calls
- `app/services/endpoint_service.py` — endpoint bearer-token validation

## 4. Request execution flow

### Telemetry request flow

1. The laptop agent sends `switch_state`, battery %, charge status, AC status, IP, hostname, and timestamp.
2. `receive_telemetry()` validates the `Authorization` header and rejects stale timestamps older than 10 minutes.
3. The endpoint record is inserted or updated by hostname.
4. All active `Mapping` rows for that endpoint are loaded.
5. A live current state is read from the local switch via `TuyaService.get_status()`.
6. If the request contains `switch_state`, it is treated as an explicit override. Otherwise the timed rule engine decides the action.
7. `TuyaService.set_state()` calls the correct on/off operation for the target channel.
8. The database updates the device state and writes an `AutomationEvent` row.

### Dashboard flow

`app/main.py` renders server-side pages using Jinja2:

- `/` dashboard overview
- `/endpoints` endpoint list
- `/devices` device catalog
- `/mappings` mapping configuration page
- `/events` event log

Those pages are not separate frontend apps; they are HTML templates served by the FastAPI app.

## 5. Data and control boundaries

### Local-only control boundary

The app assumes the Tuya device is reachable on the LAN and uses the local key, IP address, and protocol version. No cloud manager is used for routine control.

### Security boundary

Telemetry is only accepted when it includes a valid `Authorization: Bearer <token>` value. That validation is currently implemented as a static token comparison against `test-endpoint-token` in `validate_endpoint_auth()`.

### State and audit boundary

Every automation decision is persisted in the `automation_events` table with `previous_state`, `new_state`, `success`, and `error` when available.

## 6. Database bootstrap and schema compatibility

`app/core/database.py` does two things:

- creates the schema using `Base.metadata.create_all()`
- runs `_ensure_table_columns()` to add any missing columns that the app expects

This is important because the code expects fields like:

- `devices.current_state`
- `devices.last_state_change_at`
- `device_channels.enabled`
- `device_channels.current_state`
- `endpoints.updated_at`

This keeps the app resilient to schema drift during early-stage development.

## 7. Key technical characteristics

### Battery rule

`evaluate_battery_action()` uses hysteresis:

- if switch is on and battery reaches the off threshold, issue `TURN_OFF`
- if switch is off and battery drops to the on threshold, issue `TURN_ON`
- a minimum state change interval blocks rapid chatter

Default values:

- `on_threshold = 79`
- `off_threshold = 99`
- `minimum_interval_seconds = 300`

### Tuya device logic

`TuyaService` normalizes device types, extracts nested `dps` values, and supports per-channel operations.

Important implementation details:

- device state may be nested as `dps`, `data.dps`, or `status`
- switch indexing uses `channel` values such as `1`, `2`, etc.
- the app tries to avoid assuming every Tuya device uses a flat boolean state object

### Discovery behavior

`TuyaService.discover()` calls `tinytuya.deviceScan()` and normalizes the result into a list of discovered devices with fields such as:

- `name`
- `device_id`
- `ip_address`
- `local_key`
- `protocol_version`
- `device_type`

## 8. Architectural decisions to preserve

- keep a single app boundary for the first release
- isolate all device protocol logic behind `TuyaService`
- keep the automation rules explicit and threshold-based
- log request/response payloads during switch debugging
- record state transitions as durable events
- avoid cloud dependency for routine power decisions

## 9. Operational risks to watch

- bearer-token validation is intentionally minimal and not production-grade
- local keys and secrets must not be committed to source control
- hardware behavior differs across Tuya firmware and device families
- incorrect channel selection can look like a successful but no-op action
