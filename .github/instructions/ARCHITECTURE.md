# Architecture Overview

## 1. Architectural style

ChargePilot is a modular monolith implemented in Python with FastAPI. The code is organized into API, core, models, schemas, services, and templates, but it remains a single deployable application. This keeps the project easy to reason about and easy to run in a home-lab or small-office environment.

The system is intentionally local-first. It is designed for a LAN-connected environment, not a cloud-managed fleet.

## 2. Runtime topology

```text
Windows laptop
  ↓
PowerShell telemetry agent
  ↓
POST /api/v1/telemetry
  ↓
FastAPI application
  ├─ validates endpoint token
  ├─ updates endpoint battery state
  ├─ resolves endpoint mappings
  ├─ evaluates battery rule engine
  ├─ calls local Tuya control layer
  ├─ persists automation events
  ├─ streams state changes via SSE
  └─ serves Jinja dashboard + wizard UI
  ↓
Local Tuya switch or plug
```

A second local onboarding path also exists:

```text
User in device wizard
  ↓
Generate SmartLife/Tuya QR
  ↓
Scan from SmartLife app
  ↓
Fetch linked devices
  ↓
Normalize and match device metadata
  ↓
Populate local key and IP for device creation or add flow
```

## 3. Current application modules

### 3.1 API layer

The main router modules are in `app/api/`:

- `health.py` — health checks
- `telemetry.py` — telemetry intake and rule execution
- `devices.py` — device CRUD and discovery flows
- `events.py` — event retrieval
- `mappings.py` — mapping logic
- `endpoints.py` — endpoint listing and management

The product is no longer limited to API calls; the wizard pages in `app/main.py` also drive the onboarding and SmartLife flow.

### 3.2 Core layer

Key runtime modules:

- `app/main.py` — app startup, template rendering, wizard routes, and UI handlers
- `app/core/config.py` — environment-backed settings using `CHARGEPILOT_`
- `app/core/database.py` — engine and schema creation
- `app/core/security.py` — security helpers for auth and token handling

### 3.3 Data model layer

The model set in `app/models/` includes:

- `Endpoint` — laptop telemetry source
- `Device` — local smart switch metadata and current state
- `DeviceChannel` — channel-specific state
- `Mapping` — endpoint-to-device threshold mapping
- `AutomationEvent` — event auditing
- `User` — site login and access

### 3.4 Service layer

Current services include:

- `app/services/rule_engine.py` — hysteresis logic and cooldown evaluation
- `app/services/tuya_service.py` — local device discovery and control
- `app/services/smartlife_service.py` — QR login, link polling, session persistence, and normalization
- `app/services/endpoint_service.py` — endpoint auth validation
- `app/services/broadcaster.py` — SSE event broadcasting

## 4. Request execution flow

### Telemetry request flow

1. The PowerShell agent posts battery and connection telemetry to `/api/v1/telemetry`.
2. `receive_telemetry()` validates the bearer token and timestamp freshness.
3. The endpoint is upserted or updated by hostname.
4. The app loads active mappings for that endpoint.
5. The app reads the current live state from the device via `TuyaService`.
6. The rule engine decides whether to turn the device on or off.
7. The action is sent through the local control layer.
8. The device state and automation event are persisted.
9. The UI updates via SSE if connected.

### Device wizard flow

1. The user enters a SmartLife user code and chooses a QR scheme.
2. The app starts a login and returns a QR image payload.
3. The user scans the QR in the SmartLife app.
4. The app polls for linked devices and normalizes them.
5. Matching local keys and IPs are filled into the device form automatically.
6. The user adds the switch to the database and the local control path is ready.

## 5. Data and control boundaries

### Local-only control boundary

The app assumes the device is reachable on the LAN and uses the IP, protocol version, and local key. Routine control is not cloud-dependent.

### SmartLife onboarding boundary

The SmartLife flow is a pairing and metadata retrieval step. It does not replace Tuya local control; it supplies the information required to operate the device locally.

### State and audit boundary

Every automation decision is persisted in `AutomationEvent` records with previous and new state, success, and reason metadata.

## 6. Database bootstrap and schema compatibility

The database bootstrap is still simple but needs to be resilient:

- `create_db_and_tables()` creates tables on startup
- compatibility checks add missing columns when needed
- the app expects fields like `current_state`, `last_state_change_at`, and channel metadata to exist

This keeps the system robust during active development and staged rollouts.

## 7. Key technical characteristics

### Battery rule

The rule engine uses hysteresis:

- if the device is on and the battery hits the off threshold, issue a turn-off
- if the device is off and the battery drops to the on threshold, issue a turn-on
- minimum state-change interval prevents chatter

Current default values are:

- `on_threshold = 79`
- `off_threshold = 99`
- `minimum_state_change_interval = 300`

### Tuya control

The local hardware layer supports:

- nested DPS extraction
- channel-aware state operations
- discovery over the LAN
- on/off and status operations across device families

### SmartLife integration

The SmartLife bridge handles:

- QR generation
- scheme-specific QR payloads
- session persistence and TTL handling
- linked-device polling and normalization
- automatic QR refresh when the provider responds with an invalid or expired result

## 8. Architectural decisions to preserve

- keep the app as a single deployable backend rather than a distributed platform
- keep Tuya-specific logic behind service abstractions
- preserve battery thresholds and event logging as core product behavior
- keep the SmartLife flow isolated from core automation logic
- keep the UI simple, local, and server-rendered when possible

## 9. Risks and operational concerns

- QR auth can expire unexpectedly; the current code handles this by refreshing the QR immediately
- local keys are sensitive and must never be committed to source control
- Tuya devices vary in firmware and DPS structure
- the current auth model is intentionally minimal and should be hardened before production exposure

## 10. Build-from-scratch guidance for Claude

If this project needs to be recreated from scratch, the safest path is:

1. Start with a FastAPI app and SQLAlchemy models.
2. Add the telemetry endpoint and endpoint mapping engine.
3. Add the Tuya control abstraction and LAN discovery layer.
4. Add the battery rule engine and event model.
5. Add the device wizard and SmartLife QR flow.
6. Add SSE updates and local UI refinements last.
7. Treat external device APIs and device variability as compatibility problems, not assumptions.

This preserves the original design and the current product behavior.
