# Architecture Overview

## 1. Architectural style

ChargePilot uses independently deployable API, outbox-relay, and automation
consumer processes. FastAPI serves the existing management/API surface;
PostgreSQL owns transactional application state and the telemetry outbox;
Kafka transports accepted telemetry to automation consumers. The API and
workers currently share a PostgreSQL schema, so database-per-service ownership
and horizontal database sharding remain future production-scale work. One site
connector runs per physical device LAN and executes LAN-bound TinyTuya
operations locally.

Device communication remains local-first even when the control plane is hosted
in the cloud. See [CLOUD_CONNECTOR_ARCHITECTURE.md](CLOUD_CONNECTOR_ARCHITECTURE.md)
for the canonical implementation design and deployment boundaries.

## 2. Runtime topology

```text
Windows laptop
  -> PowerShell telemetry agent
  -> POST /api/v1/telemetry
  -> API validates token, updates endpoint, writes transactional outbox event
  -> outbox-relay publishes keyed event to Kafka
  -> automation-consumer evaluates mapping/rules
  -> PostgreSQL persists a desired-state device command
  -> Site connector claims command over outbound HTTPS
  -> TinyTuya controls the assigned device on its LAN
  -> Connector acknowledges result; cloud updates state/event/SSE
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
Match local keys by device ID to LAN scan results
  ↓
Populate only the local key; device details and IP come from LAN scan
```

## 3. Current application modules

### 3.1 API layer

The HTTP API modules are in `app/api/`:

- `health.py` — liveness and database readiness
- `auth.py` — authenticated-user profile and super-admin password API
- `telemetry.py` — telemetry intake, rule execution, and SSE stream
- `devices.py` — device/channel CRUD and device control
- `onboarding.py` — LAN discovery and SmartLife pairing
- `connectors.py` — connector enrollment, heartbeat, command leases, and results
- `events.py` — tenant-scoped event retrieval and pagination
- `mappings.py` — mapping CRUD
- `endpoints.py` — endpoint management, agent config, and readings

`app/main.py` retains server-rendered operational and administrative routes not
yet represented in React, along with form-based sign-in and onboarding
workflows. The authenticated React shell owns its dashboard, switch, mapping,
endpoint, event, connector, profile, user, tenant, agent setup, and account
navigation. API-host GET routes for login and registration redirect to the
configured frontend origin.

### 3.2 Core layer

Key runtime modules:

- `app/main.py` — app startup, template rendering, wizard routes, and UI handlers
- `app/core/config.py` — environment-backed settings using `CHARGEPILOT_`
- `app/core/database.py` — engine and schema creation
- `app/core/security.py` — security helpers for auth and token handling

### 3.3 Data model layer

The model set in `app/models/` includes:

- `Endpoint` — laptop telemetry source, uniquely identified by its hardware
  UUID; hostname is captured separately and may change
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
- `app/services/automation_processor.py` — idempotent asynchronous rule processing
- `app/workers.py` — horizontally deployable outbox relay and Kafka consumer

## 4. Request execution flow

### Telemetry request flow

1. The PowerShell agent posts hardware UUID, hostname, battery, and connection telemetry to `/api/v1/telemetry`.
2. `receive_telemetry()` validates the bearer token, hardware UUID, and timestamp freshness.
3. The API upserts by hardware UUID; a UUID-less legacy endpoint can be matched
   by tenant and hostname once to preserve its existing ID and mappings.
4. Endpoint snapshot and telemetry outbox event commit in one transaction.
5. One or more outbox relays publish records to Kafka, retaining per-endpoint
   ordering and allowing safe relay concurrency across distinct endpoints.
6. A consumer group processes the event, checks its idempotency record, loads
   mappings, and applies battery hysteresis/cooldown.
7. Connector-assigned switches receive durable desired-state commands;
   unassigned local devices use the existing direct TinyTuya path.
8. The processor records state and audit outcomes. Kafka acknowledgements
   follow database processing; repeated delivery is guarded by event ID.
9. The UI reads updated state through the API and receives SSE where subscribed.

### Device wizard flow

1. The user enters a SmartLife user code and chooses a QR scheme.
2. The app starts a login and returns a QR image payload.
3. The user scans the QR in the SmartLife app.
4. The app polls for linked local keys and device IDs only.
5. The local key is matched to the selected LAN scan result by device ID; all
   other fields, including the local IP address, come from the scan.
6. The user adds the switch to the database and the local control path is ready.

## 5. Data and control boundaries

### Local-only control boundary

The connector assumes the device is reachable on its LAN and uses the IP,
protocol version, and local key. Routine control is not Tuya-cloud-dependent.
The cloud stores pending work and never needs a network route to a device LAN.

### SmartLife onboarding boundary

The SmartLife flow is an opt-in local-key retrieval step. It does not replace
Tuya local control or supply device metadata. Device identity, name, IP address,
and protocol come from LAN scanning (or manual entry).

The Switches page exposes LAN discovery, manual-add, and connector assignment.
LAN discovery runs via the selected connector and intentionally excludes local
keys from results. Smart Life QR pairing is opt-in; it uses the
account user code and explicit QR confirmation, and keeps linked device IDs
and local keys in process memory for up to ten minutes. The wizard matches
keys to LAN scan results by device ID. The account ID can optionally be
remembered on the signed-in user's record; the provider session or local keys
must never be persisted to browser storage or source-controlled files.

### State and audit boundary

Every automation decision is persisted in `AutomationEvent` records with previous and new state, success, and reason metadata.

The Events page queries the event log with server-side pagination (50, 100, or
500 rows per page). Connector command outcomes become events when completed or
expired. A background retention task purges events older than 30 days
immediately at startup and then every 24 hours; retention applies across
tenants. Command rows use explicit queue/lease/completion states.

## 6. Database bootstrap and schema compatibility

The bootstrap creates the current schema, including telemetry outbox and
per-endpoint automation cursor tables. It remains `create_all()` plus compatibility SQL, not
a versioned production migration system. The new services still share the
existing PostgreSQL database; cross-service table ownership and independent
database scaling are not solved by adding Kafka.

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

- keep API, outbox relay, and automation consumers independently deployable;
  maintain explicit service boundaries and shared PostgreSQL ownership until
  per-domain stores are implemented
- keep Tuya-specific logic behind service abstractions
- preserve battery thresholds and event logging as core product behavior
- keep the SmartLife flow isolated from core automation logic
- keep the product local-first and the backend authoritative for business rules
- extend the existing React/TypeScript/Tailwind frontend for its supported
  pages, while preserving the Jinja workflows that are not yet migrated
- reuse `app/static/style.css` semantic tokens and retain coherent light/dark
  themes and the left-aligned authenticated top navigation

### Distributed runtime and capacity limits

The initial target is 10 million registered endpoints and 1 million active
telemetry sources. Kafka consumer groups can scale automation processing by
topic partitions; the local Compose broker is single-node development only.
The current PostgreSQL schema is shared and is not partitioned or sharded for
the target. The repository's scale harness verifies a temporary PostgreSQL
dataset above 10 million rows and k6 provides configurable live telemetry
traffic. Neither is a production-scale benchmark until run against sized,
multi-node staging infrastructure. Do not publish throughput or availability
claims without recording the hardware, active endpoint count, cadence, test
duration, Kafka lag, database utilization, and error/latency percentiles.

Redis is not included by default: event IDs, the outbox, Kafka, and database
constraints provide current durability/idempotency. Add a cache only after a
measured read-path bottleneck and explicit invalidation/security design.

### Shared UI theme and regression coverage

The web UI uses the semantic color tokens in `app/static/style.css` as its
source of truth. Light and dark themes must define the same semantic tokens
(`--bg`, `--panel`, `--soft`, `--muted`, `--line`, and `--primary`) so page
surfaces, text, borders, and controls change together. Use the shared
`.ui-page-hero`, `.ui-accent-surface`, and `.ui-modal-heading` classes for page
hero panels, highlighted sections, and wizard/modal headers. Blue is the
product accent; green, amber, and red are reserved for state and feedback.

When changing shared colors or adding a page/wizard surface, keep both themes
readable and add/update coverage in `tests/unit/test_ui_theme.py`. Avoid broad
dark-theme overrides on generic elements such as `div` and `span`; style
semantic components so utility text colors and status colors remain legible.
Configured switch cards and channel rows use the same panel surfaces in both
power states; show the live state with its indicator, label, and accent border
rather than changing the whole card background.

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
