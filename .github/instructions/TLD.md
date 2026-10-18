# Technical Design Level (TLD)

## 1. Scope

This document reflects the current implementation state of the repository. It covers the cloud app, site connector, runtime data flows, persistence model, SmartLife QR login bridge, local discovery workflow, and deployment constraints. The canonical cloud-to-site design is in [CLOUD_CONNECTOR_ARCHITECTURE.md](CLOUD_CONNECTOR_ARCHITECTURE.md).

## 2. Technology stack

The project currently uses:

- Python 3.12+
- FastAPI 0.134+
- SQLAlchemy 2.x
- PostgreSQL via psycopg
- Kafka via `aiokafka` for asynchronous telemetry delivery
- Pydantic + pydantic-settings
- TinyTuya for local control and discovery
- httpx-based outbound HTTPS connector runtime
- Fernet encryption for stored local keys, derived from the existing encryption setting
- Tuya sharing SDK for SmartLife linked-device flow
- React, TypeScript, Tailwind CSS, and Vite for the interactive frontend
- qrcode + Pillow-compatible support for QR generation
- pytest for automated validation
- Docker Compose for local deployment

## 3. Module-level responsibilities

### 3.1 `app/main.py`

This is the FastAPI application entrypoint. It currently handles:

- FastAPI startup and DB bootstrap
- JSON API route registration and frontend redirects
- wizard endpoints for SmartLife QR login, linked-device fetch, and match logic
- device CRUD and JSON operations for local discovery
- SSE-capable updates for device state changes

The file is no longer only a telemetry and dashboard app. It is also the UI controller for the local device onboarding workflow.

### 3.2 `app/core/config.py`

This contains the environment-backed settings model and the CHARGEPILOT_ prefix settings. It is still the main authority for database, secret, and auth configuration.

Key settings include:

- database URL
- secret key
- encryption key
- admin credentials
- telemetry and endpoint rules
- app environment metadata

### 3.3 `app/core/database.py`

This sets up the SQLAlchemy engine and creates tables. It also performs schema patching for fields expected by the app. This is still essential because the app evolves faster than the database schema when features are added.

### 3.4 `app/services/rule_engine.py`

This is the battery hysteresis module. It enforces:

- high and low threshold behavior
- minimum state-change interval before action
- explicit NO_ACTION logic when thresholds are not crossed

### 3.5 `app/services/tuya_service.py`

This module is the local device-control abstraction. The same TinyTuya operations
run at the site through `connector/chargepilot_connector.py` for cloud deployments.
It encapsulates:

- local discovery via `tinytuya.deviceScan()`
- device state fetch and channel-aware `set_state()` calls
- state reads through TinyTuya's parameterless `status()` call, followed by
  requested-channel selection from the returned DPS payload
- nested DPS extraction and payload normalization
- error logging and command orchestration

This layer remains the essential abstraction boundary and should not be bypassed by high-level logic.

### 3.6 `app/services/smartlife_service.py`

This is the new critical component for the current state of the product. It handles:

- QR creation and payload generation for SmartLife/Tuya app login
- smart scheme selection (`smartlife` vs `tuyaSmart`)
- persisted session data in `.smartlife_session.json`
- polling for linked devices using `LoginControl().login_result()`
- normalized mapping from provider objects to ChargePilot device dictionaries
- automatic refresh of QR when provider returns an immediate invalid/expired result

This service is effectively the onboarding bridge between mobile app pairing and local Tuya device control.

### 3.7 Telemetry API and workers

`app/api/telemetry.py` validates telemetry auth/freshness, updates the endpoint
snapshot, and writes a `TelemetryOutbox` record in the same PostgreSQL
transaction. `app/workers.py` runs two separate process roles: an outbox relay
publishes keyed records to Kafka, and a consumer group calls
`app/services/automation_processor.py` to evaluate rules and create
desired-state commands. A per-endpoint automation cursor prevents duplicate or
out-of-order telemetry from reapplying rules after at-least-once redelivery.
Direct LAN Tuya calls remain worker-side for devices
without a connector; connector-assigned commands remain durable PostgreSQL
records.

### 3.8 `app/services/connector_service.py` and `app/api/connectors.py`

These modules cover one-time enrollment, connector token validation, tenant and
device-scoped command claiming, leases, expiry, idempotency, result recording,
and connector heartbeat APIs. The site connector is a separate process and
receives device control details only when it claims authorized work.

## 4. Persistence model

### `Endpoint`

Represents a laptop or endpoint sending telemetry.

Key fields:

- hostname
- ip_address
- battery_percentage
- charging
- ac_connected
- last_seen_at
- agent_version
- enabled
- updated_at

### `Device`

Represents a local switch or plug.

Key fields:

- device_id
- encrypted_local_key
- ip_address
- device_type
- protocol_version
- enabled
- current_state
- last_state_change_at
- connector_id

### `DeviceChannel`

Represents per-channel state and metadata on multi-output devices.

Key fields:

- device_id
- channel_index
- name
- dp_id
- enabled
- current_state

### `Mapping`

Links an endpoint to a device or specific channel.

Key fields:

- endpoint_id
- device_id
- channel_id
- on_threshold
- off_threshold
- minimum_state_change_interval
- enabled

### `AutomationEvent`

Stores state transitions and failures for audit and debugging.

Key fields:

- event_type
- reason
- previous_state
- new_state
- success
- error

### `SiteConnector` and `DeviceCommand`

Connectors are tenant-scoped and represent a single reachable site LAN.
Commands record operation, assigned connector/device/channel, desired state,
attempt count, timestamps, expiry, lease, status, and sanitized result. Command
state progresses from `queued` through `leased` to a terminal outcome.

### SmartLife session state

The mobile pairing flow stores state in a JSON file at `.smartlife_session.json`.

Important fields:

- `user_code`
- `token`
- `qr_scheme`
- `qr_data_url`
- `status`
- `created_at`
- `expires_at`
- `session_data`
- `devices`

This is effectively a lightweight session cache and is not a replacement for the SQL database.

## 5. Current runtime flows

### A. Telemetry lifecycle

```text
PowerShell agent
  -> POST /api/v1/telemetry
  -> validate bearer token
  -> validate timestamp freshness
  -> upsert Endpoint and write TelemetryOutbox in one DB transaction
  -> outbox-relay publishes ordered endpoint-keyed record to Kafka
  -> automation-consumer deduplicates by event ID
  -> load active mappings and evaluate battery rule
  -> persist desired-state command for assigned connector
  -> connector claims and executes locally
  -> acknowledge success/failure
  -> update device state and record AutomationEvent
  -> publish SSE update
```

### B. Device wizard / SmartLife onboarding lifecycle

```text
User enters SmartLife user code
  -> POST /devices/wizard/smartlife/login
  -> SmartLifeService.start_login()
  -> generate QR payload
  -> save session + expiry metadata
  -> return qr_data_url to client
User scans QR in SmartLife app
  -> POST /devices/wizard/smartlife/fetch
  -> SmartLifeService.fetch_linked_devices()
  -> poll login_result()
  -> normalize linked devices
  -> session.devices receives matched local keys and IPs
  -> client auto-matches discovered devices
```

### C. LAN discovery and device registration

The user chooses an online connector. ChargePilot queues a discovery command
and waits for its bounded completion; the connector returns device metadata
without local keys. A scan timeout is reported clearly and does not imply
success.

```text
User clicks Run scan
  -> select active connector for LAN
  -> persist discovery command
  -> connector claims and scans locally
  -> connector posts normalized result
  -> list discovered devices
  -> choose device
  -> either manual add or SmartLife match fill-in
  -> persist new Device record
```

## 6. Concurrency and operational constraints

- Local LAN control and discovery must remain serial enough to avoid overlapping scan calls.
- SmartLife polling loops are bounded to a timeout window and may refresh QR if the token fails immediately.
- Device metadata can vary widely across Tuya firmware and device families.
- Kafka consumers use at-least-once delivery; keep event processing and
  explicit desired-state commands idempotent across worker restarts.
- The API and workers currently share one PostgreSQL schema. Database ownership,
  sharding, and 10-million-device performance are not yet validated.

## 7. Security and resilience notes

- Telemetry routes rely on bearer-token validation and a static token model in the current implementation.
- SmartLife session data lives in a local file and should never be committed to source control.
- Local keys must be treated as sensitive configuration and stored safely.
- Site connectors are tenant-scoped and their API tokens must be revocable;
  local keys are encrypted at rest with the existing encryption setting.
- QR generation must prefer PNG because QR readers are more reliable with PNG payloads than SVG in the wild.

## 8. Test strategy in the repo

The repo includes a small but important validation set:

- threshold behavior and hysteresis rules: `tests/unit/test_rule_engine.py`
- API and mapping CRUD behavior: `tests/api/test_device_mapping_crud.py`
- additional Tuya-related checks under `tests/unit`
- outbox persistence and duplicate-event processing: `tests/api/test_telemetry_api.py`
  and `tests/unit/test_automation_processor.py`
- a temporary PostgreSQL synthetic dataset above 10 million endpoint rows:
  `scripts/scale_test.py` (uses a dedicated database name ending `_scale_test`)
- configurable live telemetry traffic: `tests/scale_telemetry.js` (k6)

The 10M row and k6 tools are scale-test harnesses, not a claim that 10M live
devices have been benchmarked. Run them on provisioned staging infrastructure
and record the environment, throughput, percentiles, Kafka lag, and database
load before publishing capacity claims.

These tests are the baseline regression suite for the core automation path and should be preserved when rebuilding or refactoring.

## 9. Guidance for future rebuilds

- Preserve the separation between battery logic, Tuya control, and SmartLife pairing logic.
- Keep `SmartLifeService` isolated from the database layer if possible.
- Treat local key recovery and device discovery as first-class onboarding steps, not afterthoughts.
- Keep event logging and device state updates durable and visible.
- Kafka carries telemetry events only; PostgreSQL remains the command-of-record
  store and connectors still use outbound HTTPS polling.
- Redis is not a required runtime dependency; add it only for a measured,
  well-scoped cache/rate-limit need, not as a second source of truth.
