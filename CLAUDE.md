# ChargePilot — Claude Build Blueprint

This document is the rebuild guide for creating ChargePilot from scratch with Claude or similar AI coding agents. It reflects the current implementation state of the project and is meant to reduce ambiguity when re-building the system or extending it.

## 1. Product summary

ChargePilot is a local-first battery automation platform for Windows laptops. It receives telemetry from a PowerShell agent, stores endpoint state, evaluates battery thresholds, and toggles local Tuya devices on the same LAN.

The system has grown beyond the original battery-only flow and now includes:

- LAN scanning for local smart devices
- SmartLife/Tuya QR login for linked device discovery
- local key + IP matching for onboarding
- AJAX-friendly wizard UX for device import
- SSE updates for device state changes

## 2. Core product goals

- detect and maintain laptop battery telemetry
- map endpoints to local smart switches or plugs
- trigger switch actions based on battery thresholds
- support local smart-device discovery and onboarding
- support QR-based SmartLife/Tuya linked-device import
- keep the system local-first and self-hosted

## 3. Non-goals

- fully managed SaaS hosting
- multi-region distributed orchestration
- mobile-native app or separate frontend app
- cloud-first automation

## 4. Recommended stack

- Python 3.12+
- FastAPI
- SQLAlchemy 2.x
- PostgreSQL
- Pydantic + pydantic-settings
- TinyTuya
- tuya-device-sharing-sdk
- Jinja2 templates
- pytest
- Docker Compose
- qrcode

## 5. Recommended architecture

Use a modular monolith:

- app/main.py — entrypoint, HTML rendering, wizard routes
- app/api/ — API routers
- app/core/ — config and start-up bootstrapping
- app/models/ — ORM models
- app/schemas/ — request/response validation
- app/services/ — business logic and protocol adapters
- app/templates/ — server-rendered UI pages
- app/static/ — CSS and UI assets
- agent/ — Windows agent for telemetry upload

## 6. Core domain model

### Endpoint
Represents a battery-monitoring laptop or device.

Fields to include:
- hostname
- ip_address
- battery_percentage
- charging
- ac_connected
- last_seen_at
- agent_version
- enabled
- updated_at

### Device
Represents a local switch or plug.

Fields to include:
- device_id
- encrypted_local_key
- ip_address
- device_type
- protocol_version
- enabled
- current_state
- last_state_change_at

### DeviceChannel
Represents multi-channel switch state and metadata.

Fields to include:
- device_id
- channel_index
- name
- dp_id
- enabled
- current_state

### Mapping
Links an endpoint to a device or channel.

Fields to include:
- endpoint_id
- device_id
- channel_id
- on_threshold
- off_threshold
- minimum_state_change_interval
- enabled

### AutomationEvent
Audit trail for state changes and failures.

Fields to include:
- event_type
- reason
- previous_state
- new_state
- success
- error

## 7. Core feature sequence for a fresh build

### Phase 1 — core automation foundation

1. Set up FastAPI app and SQLAlchemy session management.
2. Add environment config with CHARGEPILOT_ prefix.
3. Create endpoint, device, mapping, and event models.
4. Implement telemetry route for PowerShell agent uploads.
5. Validate bearer token and timestamp freshness.
6. Save endpoint state and load active mappings.
7. Implement battery rule engine with hysteresis and cooldown.
8. Implement local device control via TinyTuya.
9. Persist automation events.

### Phase 2 — local discovery and onboarding

1. Add device scan endpoint or local discovery flow.
2. Show discovered devices in a wizard UI.
3. Support manual add of local key, IP, protocol version, and channels.
4. Add a SmartLife/Tuya QR login route.
5. Persist QR scheme and session state.
6. Poll linked devices and normalize provider output.
7. Auto-fill local key and IP when a linked device matches a discovery item.

### Phase 3 — operational UX

1. Add a device onboarding wizard.
2. Add AJAX-based QR generation and fetch endpoints.
3. Add toast feedback instead of blocking browser alerts.
4. Add visual matching highlighting for auto-filled device rows.
5. Add SSE or lightweight polling for runtime state updates.

## 8. Important implementation details to keep

### Telemetry agent contract

The PowerShell agent sends:
- hostname
- ip_address
- battery_percentage
- charging
- ac_connected
- switch_state
- timestamp
- agent_version

### Rule engine behavior

Use hysteresis and a cooldown:

- if currently on and battery >= off_threshold → TURN_OFF
- if currently off and battery <= on_threshold → TURN_ON
- if below minimum interval → NO_ACTION

### Device control assumptions

- local network access is required
- IP and local key are essential for reliable control
- device payloads may vary by device family
- channel-aware logic is required for multi-channel devices

### SmartLife/Tuya flow assumptions

- `LoginControl().qr_code()` uses SDK schema `haauthorize`
- visible QR payload must use an app-specific scheme like `smartlife--qrLogin?token=`
- provider TTL may vary; refresh the QR automatically if the first fetch result appears expired or invalid
- the SmartLife session should be persisted locally and should not be committed to source control

## 9. Example build prompts for Claude

### Prompt A — full project build

"Build ChargePilot from scratch as a local-first Python monolith with FastAPI, SQLAlchemy, TinyTuya, and a Windows PowerShell telemetry agent. Implement battery threshold automation, local device discovery, SmartLife QR login flow, and a wizard that can discover local devices and auto-fill local key / IP from linked SmartLife devices. Keep the architecture modular and self-hosted, with tests for the rule engine and API behavior."

### Prompt B — SmartLife bridge only

"Add a SmartLife/Tuya QR login service to a FastAPI app. Generate PNG-first QR images with SVG fallback, persist the session, poll for linked devices after scan, normalize linked device output, and auto-refresh when the provider signals expiration. Return JSON payloads for AJAX clients and keep the logic isolated in a service module."

### Prompt C — telemetry automation path

"Implement the battery telemetry ingestion route for a local-first automation app. Validate bearer tokens, reject stale telemetry, upsert endpoints by hostname, load active mappings, evaluate battery thresholds with hysteresis, and write automation event records when a device is toggled."

## 10. Suggested build order for Claude

1. Scaffold app structure and config.
2. Add database models.
3. Implement telemetry endpoint and mappings.
4. Add local Tuya abstraction and state controls.
5. Add rule engine and event persistence.
6. Add device wizard and local discovery pages.
7. Add SmartLife QR service and linked-device fetch.
8. Add AJAX and toast-based UX polish.
9. Add tests and catch edge cases around QR expiry, device metadata, and channel logic.

## 11. Critical pitfalls to avoid

- storing local keys in source control
- assuming every device follows the same DPS structure
- treating SmartLife QR login as a direct local control path
- calling control actions without checking live state or mapping
- mixing battery logic into the UI layer
- building a cloud-first architecture for a LAN-first problem

## 12. Success criteria for a rebuild

A recreated version should be considered correct if it can:

- receive telemetry from the Windows agent
- update endpoint and mapping state
- turn a local device on/off based on battery thresholds
- discover local devices on the LAN
- add devices via the wizard or SmartLife flow
- fetch linked devices from SmartLife after QR scan
- auto-match local keys and IPs for device registration
- record state change events and allow debugging

This is the implementation baseline to preserve.
