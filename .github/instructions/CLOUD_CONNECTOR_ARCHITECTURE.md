# ChargePilot Cloud Connector Architecture

This is the canonical site-LAN control design for the ChargePilot distributed
control plane.

## Decision

Run one ChargePilot site connector on an always-on host on each physical LAN
that contains Tuya devices. The connector makes outbound HTTPS requests to the
ChargePilot control plane, receives only persisted and authorized work, and
performs TinyTuya operations on its local network.

Telemetry uses a PostgreSQL transactional outbox and Kafka; automation
consumers create desired-state commands in PostgreSQL. Site connectors keep an
outbound WebSocket open for command-available notifications, then claim the
durable command and submit results over authenticated HTTPS. PostgreSQL
`LISTEN`/`NOTIFY` fans committed-command wake-ups to each API process; Kafka is
not exposed to site connectors and does not replace durable command records,
tenant checks, leases, or result acknowledgement.

## Runtime topology

```text
Endpoint telemetry agent --> API --> PostgreSQL outbox --> Kafka
                                                    |
                                             automation workers
                                                    |
                                         PostgreSQL command records
                                                    |
                                 outbound WebSocket notification
                                   + HTTPS claim/result requests
                                                    |
                                         Site connector host
                                                    |
                                         TinyTuya over site LAN
                                                    |
                                               Tuya switch
```

The API, outbox relay, and automation workers are independently deployable
services. They currently share the ChargePilot PostgreSQL schema. The
connector is an additional deployment at each site, not a cloud-to-LAN tunnel.
It needs outbound HTTPS access to ChargePilot and local network access to its
assigned switches. The site does not expose an inbound Internet listener.
TinyTuya documents UDP discovery traffic on ports 6666, 6667, 7000 and TCP
6668; validate firewall behavior with the actual device family and installation.
Supported packages are a Linux amd64/arm64 Docker image and a self-contained
Windows executable installed as an automatically starting service. The Windows
service runs as LocalService; its credential file is ACL-protected for SYSTEM,
Administrators, and the service identity. Its executable is currently
unsigned, and updates are manual.

## Boundaries and identity

- A tenant may enroll multiple connectors. Each connector represents one
  reachable site LAN.
- Devices are explicitly assigned to one connector; a connector can only
  claim commands for its assigned devices.
- Connector enrollment is one-time and expires. It is exchanged for a
  revocable, connector-specific bearer credential. The database stores only
  hashes of enrollment and connector credentials.
- The connector API never accepts an arbitrary host, IP, port, or code
  execution request. Cloud-generated work addresses a registered device and
  channel only.
- Device local keys are encrypted at rest using the existing
  `CHARGEPILOT_ENCRYPTION_KEY` setting. The existing setting name and format
  are unchanged. A connector receives the key only when claiming authorized
  device work, over TLS; credentials must never be logged.
- Tenant/site authorization is applied to enrollment management, device
  assignment, command creation, claiming, and result submission.

## Command contract and delivery semantics

Commands are durable PostgreSQL rows and use desired-state operations, never
blind toggles. Each command has an ID, operation, device/channel identity,
desired state when applicable, creation and expiry times, attempt count, lease,
and result. The connector handles duplicate delivery idempotently by applying
the requested final state and reporting the same command ID.

Initial operations:

- `set_state`: set a registered channel explicitly on or off.
- `discover`: scan the connector's own LAN and return normalized device
  metadata. Discovery responses exclude local keys.
- `get_status`: read a registered device/channel state.

Lifecycle: `queued -> leased -> succeeded | failed | expired`. A lease permits
reclaim after connector loss. Use bounded retry and command expiry. Do not
report a successful UI action or update confirmed device state until a
successful connector result is recorded. Record terminal results and errors in
the automation event history.

The connector WebSocket is only a wake-up channel. It carries no command
payload, device key, or provider credential. After connecting or receiving a
`commands_available` notification, the connector drains work through the
existing authenticated HTTPS claim/result routes. The server sends a
notification only after the transaction inserting a command commits. On
disconnect, the connector reconnects with exponential backoff and jitter,
immediately checks for queued work, and retains a periodic safety claim in case
a notification is missed. WebSocket pings and connector application
heartbeats detect stale connections; the existing heartbeat HTTP endpoint
remains available for older connector versions.

Each API process maintains one PostgreSQL notification listener and fans
connector-scoped notifications to only its own connected sockets. This allows
multiple API replicas to receive the same committed notification without
putting socket state in the command database. The notification is not durable;
the PostgreSQL command row, lease, retry bounds, and periodic safety claim
provide recovery. Keep the WebSocket protocol versioned and validate upgrades,
timeouts, and graceful reconnects through the production ingress.

## Automation path

1. Existing endpoint agents submit their platform-aware telemetry
   payload and token.
2. ChargePilot saves endpoint telemetry and validates that the endpoint and
   sample are eligible for automation. Direct-local switches are checked
   against live status before evaluating the mapping's hysteresis and cooldown
   rules; if status is offline or unrecognized, it skips the decision rather
   than using cached state. Automatic turn-on can be disabled
   independently of turn-off behavior. A separate charging-completion cutoff
   can turn an on switch off at its configured battery threshold only when
   telemetry reports `charging=true`; `ac_connected` alone is not sufficient.
3. For connector-assigned switches, telemetry requests a live `get_status`
   before making a battery decision. Successful status results are reconciled
   against the endpoint's latest fresh battery/charging sample and the same
   mapping rules; idle connector polling also checks enabled mapped switches
   about once per minute when their endpoints remain automation-eligible.
   Stale, disabled, or disallowed endpoint telemetry does not trigger status
   reconciliation or corrective commands.
4. If an action is required, ChargePilot creates a durable desired-state
   command for the device's assigned connector. Avoid duplicate outstanding
   commands for the same device/channel.
5. The connector claims authorized work, performs the local TinyTuya operation,
   verifies/report results, then acknowledges using the command ID.
6. ChargePilot updates device/channel state, creates the automation event,
   broadcasts the update, and exposes failures or pending work in the UI.

Successful status checks update the last-observed state. If a later check
finds a state change, that observation starts the existing device cooldown;
status polling must not bypass the mapping's hysteresis, turn-on setting,
charging cutoff, or minimum state-change interval.

Manual switch controls use the connector path for connector-assigned devices.
The connector normalizes generic `switch`, `plug`, and `outlet` labels to
TinyTuya's `default` OutletDevice profile, matching direct local control.
LAN discovery can scan directly from the ChargePilot server's network or be
explicitly delegated to an online site connector for a remote LAN. Server-side
discovery requires the app process (including its container, if used) to have
LAN reachability and TinyTuya discovery traffic. A device without an assigned,
active connector cannot be remotely controlled from cloud hosting; the UI must
say what is missing.

## Optional Tuya meter telemetry

Energy monitoring is opt-in per switch. Users configure the power and energy
datapoint IDs and raw-value conversion multipliers from the Switches page;
ChargePilot never assumes a universal Tuya DPS layout. A connector at the
assigned site polls configured meters through ordinary `get_status` work when
no other command is waiting, with a nominal 60-second per-device cadence.
It sends only configured readings normalized as watts and kWh, not the full
device status map.

The API stores the latest power sample and current UTC-calendar-month energy.
For cumulative energy counters, it derives monthly increments from observed
counter deltas; the first sample in a month establishes a baseline, so a total
collected after the month begins is necessarily partial. For monthly counters,
the API uses the device-reported month value. Unsupported or invalid datapoints
remain unavailable (`null`) rather than being represented as zero. The Overview
includes only power samples no older than five minutes and clearly reports the
number of contributing meters. Power and energy keep separate valid-sample
timestamps so a missing datapoint cannot make the other measurement look fresh.

Meter setup can request an explicit, one-time `inspect_meter` command through
the assigned site connector. The connector returns up to 32 finite numeric
readings with their IDs, samples, and only recognized power/energy role hints;
it does not return the complete DPS map, booleans, nested values, or device
state. Candidates are scoped to the authenticated tenant and are not persisted
as meter settings. Unknown IDs and units require user selection rather than
guessing.

Regular meter polling requires connector version 0.1.3 or newer; guided
meter discovery requires connector version 0.1.4 or newer. The feature also
requires the
`20261022_tuya_energy_monitoring.sql` schema migration on existing PostgreSQL
installations. Back up the database before applying it. The rollback script
removes both configuration and collected meter history; use it only when
intentionally removing the feature and after preserving any required data.

## Proposal: multi-provider telemetry and control

This section is a target architecture, not a shipped API or supported
integration. No additional IoT vendor, protocol, or telemetry source is
currently implemented. Select and validate concrete providers before
implementing this proposal.

Telemetry-source integration and switch-control integration are separate
capabilities. A provider may supply measurements, control devices, do both, or
do neither. Do not model a new IoT source as an OS `Endpoint`: the existing
`/api/v1/telemetry` contract requires battery and charging fields and its
identity/enrollment rules are specific to installed endpoint agents.

The proposed telemetry path introduces a tenant-owned source identity and
provider enrollment, then accepts versioned observations with:

- a stable provider-scoped source ID, not an IP address or mutable display name
- a bounded set of typed measurements with canonical metric IDs, numeric
  values, explicit units, observed timestamps, and quality/availability
  state
- provider and schema versions for adapter evolution and replay
- per-source credentials that are revocable and stored as hashes where
  verification permits; provider secrets needed for polling are encrypted at
  rest and never exposed to browsers or logs

Normalize measurements at the provider boundary (for example power in watts
and energy in kWh), but preserve the distinction between unsupported, stale,
invalid, and valid zero values. Do not feed arbitrary provider JSON, raw
credentials, or unvalidated measurements into automation. Store observations
with tenant/source identity and enqueue them transactionally before
asynchronous rule evaluation. Battery rules remain endpoint-specific; rules
for power, temperature, or other measurements need explicit units, freshness,
quality, hysteresis, and safe action policies.

The proposed control path adds a provider adapter behind the existing durable
desired-state command contract. Its bounded interface should cover declared
capabilities, provider-side discovery, status reads, and idempotent
`set_state` operations. Persist provider identity and opaque device identity
separately from provider-specific configuration. Keep provider credentials in
encrypted storage, and send a connector only the minimum credential and
device configuration required for an authorized command. A provider driver
must never accept arbitrary hosts, URLs, scripts, or device IDs from a
telemetry payload.

Where a provider is reachable only from a site LAN, implement its driver in
the site connector and keep cloud-to-site traffic outbound HTTPS with tenant-
scoped enrollment, leases, expiry, retry bounds, and command-result
acknowledgement. Reuse the current `set_state` desired-state lifecycle, but
version and capability-check the connector command contract before dispatch.
Cloud APIs should not call vendor cloud APIs directly as an implicit fallback.

The implementation sequence is:

1. Select the first telemetry source and first control provider, including
   network location, authentication, rate limits, units, supported operations,
   and failure behavior.
2. Define separate source/device ownership, provider capability, and
   normalized observation/command contracts; keep existing endpoint and Tuya
   semantics intact.
3. Design a versioned PostgreSQL migration with reviewed backup and rollback
   steps. Do not use startup `create_all()` to upgrade production data.
4. Implement one provider adapter at a time behind the contracts, then add
   tenant isolation, credential lifecycle, freshness, idempotency, and
   provider-contract tests.
5. Add onboarding and UI only for operations supported end-to-end by that
   provider, and verify offline, partial-failure, and recovery behavior on
   non-critical devices.

## Deployment requirements

Cloud deployment:

- Run multiple API instances behind a TLS-terminating ingress as required.
- Run the outbox relay and Kafka automation consumer as separate workloads.
- Use a production Kafka cluster with TLS/SASL, replication, topic retention,
  monitoring, and a dead-letter topic. Local Compose Kafka is single-node only.
- Keep connector APIs reachable over HTTPS and allow request/response sizes
  needed for discovery.
- Persist connector state and command results in PostgreSQL; Kafka is the
  telemetry event log, not the command-of-record store.

Site deployment:

- Install one connector process/service per device LAN.
- Store the ChargePilot URL, connector credential, and connector ID in a
  separate connector-local configuration file; this does not alter endpoint
  agent configuration formats.
- Run as a restricted OS account and restart on failure.
- Allow outbound HTTPS to ChargePilot and required local Tuya traffic only.
- Keep connector logs diagnostic but scrub credentials and local keys.

## Compatibility rules

Do not rename, remove, or break semantics for existing `CHARGEPILOT_`
environment settings, Compose variables, PowerShell agent `agent-config.json`,
Windows telemetry fields, or legacy Windows endpoint token authentication.
Cross-platform telemetry adds platform fields and per-install enrollment
without replacing the Windows contract. Connector configuration and
enrollment are separate interfaces.

Windows PowerShell, the enrolled macOS SwiftUI menu-bar app with CLI
diagnostics, Android Kotlin/Compose, and iOS SwiftUI clients are implemented.
Android has a debug APK build and emulator smoke test; physical-device
validation remains pending. iOS has an unsigned device IPA build and simulator
smoke test; physical-device validation remains pending. All agents submit
telemetry to the control plane; the site connector remains the only component
responsible for LAN-bound Tuya discovery and control. The shared identity,
enrollment, and payload contract is documented in
`platform-agents/SERVER_SIDE_CONFIG.md`.

## Schema and rollout

Connector, device assignment, and command tables/columns require a deliberate
schema upgrade on existing deployments. New installs may use metadata
initialization, but production upgrades must apply an explicit, versioned
database migration after backup. Do not treat `create_all()` as an upgrade
mechanism.

Deploy in this order:

1. Apply and verify the database schema migration.
2. Deploy the cloud app with connector APIs and management UI.
3. Enroll one test connector and assign a non-critical device.
4. Validate discovery, status, manual control, telemetry automation, offline
   recovery, and revocation.
5. Roll out per site and monitor command age, failures, connector freshness,
   and event outcomes.

## Operational and security acceptance criteria

- A tenant cannot enroll, view, revoke, assign, or issue commands across
  another tenant's connector/device.
- Invalid, expired, reused, or revoked enrollment/connector credentials fail
  closed.
- A missing connector, expired command, lost connection, failed local call, or
  invalid device key is surfaced as pending/failure, never success.
- Duplicate/reclaimed commands do not toggle devices unexpectedly.
- Discovery cannot import local keys or silently replace saved device identity.
- Local keys are encrypted at rest, never returned by user APIs, and scrubbed
  from logs.
- Existing telemetry clients and configuration continue to work without edits.
- Multiple app processes do not double-claim a PostgreSQL command.

## Capacity target and scale gate

The target is 10 million registered endpoints and 1 million active telemetry
sources. This is a target, not a measured guarantee. Kafka partitions and
consumer-group workers provide a scale-out path for automation; the current
API/workers still share one PostgreSQL schema and need an independently
reviewed partitioning/sharding strategy before a 10-million-endpoint launch.

Use `scripts/scale_test.py` for an isolated PostgreSQL temporary dataset above
10 million rows and `tests/scale_telemetry.js` for a configurable k6 live-load
test against a non-production tenant. Neither is a substitute for a benchmark
on sized staging infrastructure. Record active devices, telemetry cadence,
ingress rate, p50/p95/p99 latency, error rate, outbox age, Kafka consumer lag,
database CPU/IO/connections, and connector-command completion. Set capacity
claims only from reproducible results.

Redis is intentionally not required by this flow. Do not add it as a second
source of truth for telemetry or commands. Consider a cache only when staging
profiles identify a read-path bottleneck and invalidation/tenant isolation
have been designed.
