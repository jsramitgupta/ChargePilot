# ChargePilot — Claude Build Blueprint

This document is the rebuild guide for creating ChargePilot from scratch with Claude or similar AI coding agents. It reflects the current implementation state of the project and is meant to reduce ambiguity when re-building the system or extending it.

## 1. Product summary

ChargePilot is a local-first battery automation platform for Windows laptops.
When hosted in the cloud, a site connector on each Tuya LAN claims durable
desired-state commands over outbound HTTPS and performs local TinyTuya
discovery/control. The canonical design is in
`.github/instructions/CLOUD_CONNECTOR_ARCHITECTURE.md`.

The system has grown beyond the original battery-only flow and now includes:

- LAN scanning for local smart devices
- SmartLife/Tuya QR login for linked device discovery
- SmartLife local-key retrieval matched to LAN scan results
- AJAX-friendly wizard UX for device import
- SSE updates for device state changes
- tenant-scoped site connector enrollment and PostgreSQL-backed commands
- PostgreSQL transactional outbox, Kafka telemetry events, and independent
  automation workers
- a target of 10M registered endpoints and 1M active agents; this is not a
  measured production capacity claim

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
- Apache Kafka with `aiokafka`
- Pydantic + pydantic-settings
- TinyTuya
- tuya-device-sharing-sdk
- pytest
- Docker Compose
- qrcode

## 5. Recommended architecture

Use independently deployable runtime roles:

- app/main.py — management/API and HTML entrypoint
- app/api/ — management, telemetry-ingress, and connector HTTP routers
- app/workers.py — transactional-outbox relay and Kafka automation consumer
- app/services/automation_processor.py — asynchronous rules and command creation
- app/models/ — shared schema, including outbox/idempotency records
- connector/ — site-side TinyTuya runtime for cloud deployments
- agent/ — Windows agent for telemetry upload

The API, relay, and consumer still share one PostgreSQL schema. Do not call
the current database topology sharded or proven for 10M endpoints. Local
Compose Kafka is single-node development infrastructure; production needs
secured, replicated Kafka and a benchmarked database partitioning/sharding
strategy.

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
8. Add tenant-scoped connector enrollment and PostgreSQL-backed commands.
9. Run TinyTuya in the site connector; retain direct local-host behavior for existing deployments.
10. Persist automation events after connector results.
11. Commit endpoint snapshots and telemetry outbox records atomically; relay
    endpoint-keyed events to Kafka and process them idempotently.

### Phase 2 — local discovery and onboarding

1. Add device scan endpoint or local discovery flow.
2. Show discovered devices in a wizard UI.
3. Support manual add of local key, IP, protocol version, and channels.
4. Add a SmartLife/Tuya QR login route.
5. Persist QR scheme and session state.
6. Poll linked devices and normalize provider output.
7. Match SmartLife local keys to LAN scan results by device ID; populate the
   IP and other device details only from the LAN scan.

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

The backend uses the active mapping thresholds and live switch state to make
automation decisions. `switch_state` is retained for agent compatibility but
must not override those rules.

Cloud-hosted control must use outbound HTTPS from a connector on the same LAN
as the Tuya devices. Do not modify the current agent JSON or telemetry format.

### Rule engine behavior

Use hysteresis and a cooldown:

- if currently on and battery >= off_threshold → TURN_OFF
- if currently off and battery <= on_threshold → TURN_ON
- if below minimum interval → NO_ACTION

### Device control assumptions

- local network access is required on the site connector host
- the cloud server does not scan or route directly to private device LANs
- each device is assigned to one active connector in its tenant
- IP and local key are essential for reliable control
- commands use explicit desired state, leases, expiry, and bounded retries
- preserve existing PowerShell agent config and `CHARGEPILOT_` settings
- device payloads may vary by device family
- channel-aware logic is required for multi-channel devices

### SmartLife/Tuya flow assumptions

- `LoginControl().qr_code()` uses SDK schema `haauthorize`
- visible QR payload must use an app-specific scheme like `smartlife--qrLogin?token=`
- provider TTL may vary; refresh the QR automatically if the first fetch result appears expired or invalid
- the SmartLife session should be persisted locally and should not be committed to source control

## 9. Example build prompts for Claude

### Prompt A — full project build

"Build ChargePilot as a local-first Python service system with FastAPI, SQLAlchemy, Kafka, TinyTuya, and a Windows PowerShell telemetry agent. Implement a transactional telemetry outbox, keyed Kafka events, idempotent automation consumers, durable multi-connector commands, LAN discovery, SmartLife QR login, and tests for event delivery, tenant isolation, rules, and measured scale. Treat 10M registered / 1M active as an unproven target until staging benchmarks verify it."

### Prompt B — SmartLife bridge only

"Add a SmartLife/Tuya QR login service to a FastAPI app. Generate PNG-first QR images with SVG fallback, persist the session, poll for linked devices after scan, normalize linked device output, and auto-refresh when the provider signals expiration. Return JSON payloads for AJAX clients and keep the logic isolated in a service module."

### Prompt C — telemetry automation path

"Implement the battery telemetry ingestion route for a local-first automation app. Validate bearer tokens, reject stale telemetry, upsert endpoints by hostname, load active mappings, evaluate battery thresholds with hysteresis, and write automation event records when a device is toggled."

## 10. Suggested build order for Claude

1. Define bounded contexts, event contracts, and data ownership.
2. Implement telemetry ingestion and its transactional outbox.
3. Relay ordered events to Kafka and consume them idempotently.
4. Preserve battery rules and durable per-connector command delivery.
5. Package Compose development and secured Kubernetes production workloads.
6. Validate 10M synthetic rows and benchmark live load on staging hardware.
7. Keep discovery, SmartLife pairing, and connector LAN control isolated.
8. Update API, operations, deployment, and architecture documentation.

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
- match SmartLife local keys to LAN-scanned devices while taking all device details, including IP, from the scan
- record state change events and allow debugging
- durably acknowledge telemetry while rules run asynchronously
- build/query a temporary dataset above 10 million synthetic records
- publish measured, reproducible 1M-active staging results and limitations

This is the implementation baseline to preserve.
