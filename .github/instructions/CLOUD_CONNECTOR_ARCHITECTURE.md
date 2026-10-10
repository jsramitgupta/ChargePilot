# ChargePilot Cloud Connector Architecture

This is the canonical implementation and deployment design for controlling
Tuya devices on a private site LAN when ChargePilot itself runs in the cloud.

## Decision

Run one ChargePilot site connector on an always-on host on each physical LAN
that contains Tuya devices. The connector makes outbound HTTPS requests to the
existing ChargePilot server, receives only persisted and authorized work, and
performs TinyTuya operations on its local network.

The initial delivery mechanism is HTTPS polling backed by PostgreSQL. Do not
add a broker, Redis, an inbound site port, or a VPN requirement for the first
release. A later move to brokered messaging or persistent push must preserve the
command contract and tenant/device authorization.

## Runtime topology

```text
Windows laptop agent --existing telemetry API--> ChargePilot cloud
                                                     |
                                            rule engine + PostgreSQL
                                                     |
                                          outbound HTTPS polling
                                                     |
                                           Site connector host
                                                     |
                                          TinyTuya over site LAN
                                                     |
                                                Tuya switch
```

Cloud components remain the existing FastAPI app and PostgreSQL service. The
connector is an additional deployment at each site, not a new cloud server.
It needs outbound HTTPS access to ChargePilot and local network access to its
assigned switches. The site does not expose an inbound Internet listener.
TinyTuya documents UDP discovery traffic on ports 6666, 6667, 7000 and TCP
6668; validate firewall behavior with the actual device family and installation.

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

The initial poll interval should balance interactive latency with traffic (a
few seconds); use bounded exponential backoff while disconnected. Heartbeats
make online state explicit and use a server-side freshness window. Keep the
HTTP contract versioned for later connector upgrades.

## Automation path

1. The existing laptop agent continues to submit the existing telemetry
   payload and token.
2. ChargePilot saves endpoint telemetry and evaluates the existing mapping,
   threshold, hysteresis, and cooldown logic.
3. If an action is required, ChargePilot creates a durable command for the
   device's assigned connector. Avoid duplicate outstanding commands for the
   same device/channel.
4. The connector claims authorized work, performs the local TinyTuya operation,
   verifies/report results, then acknowledges using the command ID.
5. ChargePilot updates device/channel state, creates the automation event,
   broadcasts the update, and exposes failures or pending work in the UI.

Manual switch controls use the connector path for connector-assigned devices.
LAN discovery can scan directly from the ChargePilot server's network or be
explicitly delegated to an online site connector for a remote LAN. Server-side
discovery requires the app process (including its container, if used) to have
LAN reachability and TinyTuya discovery traffic. A device without an assigned,
active connector cannot be remotely controlled from cloud hosting; the UI must
say what is missing.

## Deployment requirements

Cloud deployment:

- Keep the current ChargePilot app and PostgreSQL services.
- Serve the connector API over HTTPS.
- Configure the reverse proxy/load balancer to allow normal HTTPS polling and
  request/response sizes expected for discovery.
- Persist connector state and command results in the existing PostgreSQL
  database. Do not rely on in-memory connection state.

Site deployment:

- Install one connector process/service per device LAN.
- Store the ChargePilot URL, connector credential, and connector ID in a
  separate connector-local configuration file; this does not alter the laptop
  agent configuration format.
- Run as a restricted OS account and restart on failure.
- Allow outbound HTTPS to ChargePilot and required local Tuya traffic only.
- Keep connector logs diagnostic but scrub credentials and local keys.

## Compatibility rules

Do not rename, remove, or change semantics for existing `CHARGEPILOT_`
environment settings, Compose variables, PowerShell agent `agent-config.json`,
telemetry fields, or endpoint token authentication. Connector configuration
and enrollment are separate interfaces.

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

## Scaling decision

PostgreSQL remains the initial durable queue. Add MQTT/NATS/Redis only after
measured load or multi-instance operation demonstrates a need. If moving to
WebSockets or a broker, preserve durable command storage, idempotency, tenant
scoping, explicit desired state, expiry, leases, and terminal audit events.
