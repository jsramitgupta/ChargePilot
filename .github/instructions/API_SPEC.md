# API Specification

## 1. Base URL and routing

The app is mounted under the FastAPI prefix configured in `app/core/config.py`:

```text
/api/v1
```

The root app is served by `app.main` and the main routes are registered as:

- `/health`
- `/ready`
- `/api/v1/telemetry`
- `/api/v1/endpoints`
- `/api/v1/devices`
- `/api/v1/connectors`
- `/api/v1/mappings`
- `/api/v1/events`

## 2. Authentication model

Telemetry ingestion requires a bearer token in the `Authorization` header.

Example:

```http
Authorization: Bearer <YOUR_AGENT_TOKEN>
```

The validation logic lives in `app/services/endpoint_service.py`. It accepts a tenant's configured agent token or the system-wide global token, which is generated randomly when the database is first initialized. Tenant tokens register and update endpoints for that tenant. The global token is for unassigned endpoints; use the tenant-specific token after assigning an endpoint to a tenant.

Browser authentication uses session cookies set by JSON requests to
`POST /api/v1/auth/login` and `POST /api/v1/auth/register`. The React frontend
is the only browser UI; legacy page GETs redirect to the configured frontend.
Standard-user signup requires a valid one-time tenant invite.

### 2.0 POST /api/v1/auth/login

Accepts JSON `{ "username": "...", "password": "..." }`, verifies the account,
sets the session cookie, and returns the signed-in user. Invalid credentials
return HTTP 401.

### 2.0.1 POST /api/v1/auth/register

Tenant creation request:

```json
{"account_type":"tenant","username":"owner","password":"a-long-password","tenant_name":"Operations"}
```

Creates a tenant and its first tenant-admin account, then signs the user in.
Standard-user request:

```json
{"account_type":"standard","username":"operator","password":"a-long-password","invite_code":"one-time-code"}
```

Standard registration requires a tenant admin/manager generated code. The
database stores only its hash; the invite is consumed in the account-creation
transaction, can be used once, and expires after seven days. The raw code is
returned only when created.

### 2.1 PUT /api/v1/auth/password

Changes the authenticated super admin's password. The current password must
match, and the new password must be at least 12 characters and no more than
72 UTF-8 bytes. Other roles receive HTTP 403.

Request:

```json
{
  "current_password": "current-password",
  "new_password": "a-new-password-with-12-characters"
}
```

The endpoint returns `{"message": "Password changed."}`. The signed-in
session remains active.

### 2.2 PUT /api/v1/auth/profile

Saves the authenticated user's display time zone. `timezone` must be a valid
IANA time-zone identifier (for example, `Asia/Kolkata` or `UTC`). The React
account page presents supported IANA zones in a region-grouped dropdown.

Request:

```json
{"timezone":"Asia/Kolkata"}
```

The response is `{"message":"Time zone saved.","timezone":"Asia/Kolkata"}`.

### 2.3 POST /api/v1/auth/logout

Clears the authenticated browser session and returns `{"status":"logged_out"}`.
React navigation then moves to the frontend login route without navigating the
browser to an API-host page.

### 2.4 GET /api/v1/admin/users

Lists user accounts visible to the signed-in Super Admin or tenant admin.
Passwords and password hashes are never returned. Tenant admins see only users
in their tenant.

### 2.5 GET /api/v1/admin/tenants

Lists tenants for Super Admin workflows. The response includes each tenant's
agent token, matching the existing Super Admin tenant-management screen. The
response is marked `private, no-store`.

### 2.6 Tenant invitations and administration

- `POST /api/v1/admin/invites` creates a seven-day, single-use tenant invite.
  Tenant admins/managers can issue codes for their tenant; Super Admins must
  select the tenant. The raw code is returned once.
- `GET /api/v1/admin/invites` lists status and expiry without code values.
- `DELETE /api/v1/admin/invites/{invite_id}` revokes an unused invite.
- `POST /api/v1/admin/users`, `PATCH /api/v1/admin/users/{user_id}`, and
  `DELETE /api/v1/admin/users/{user_id}` provide scoped account management
  while retaining at least one tenant administrator.
- `POST /api/v1/admin/tenants` creates a tenant; `DELETE
  /api/v1/admin/tenants/{tenant_id}` removes its tenant-scoped records.
- Tenant telemetry credentials can be rotated with
  `POST /api/v1/admin/tenants/{tenant_id}/rotate-agent-token` (Super Admin) or
  `PUT /api/v1/admin/tenant-agent-token` (tenant admin/manager).
- `PUT /api/v1/admin/global-agent-token` saves or regenerates the Super Admin
  global endpoint token.

### 2.7 GET /api/v1/agent/setup

Returns the authenticated user's agent install command and token for the React
agent setup page. Requires an assigned tenant, except for the Super Admin. A
Super Admin may pass `tenant_id` to select that tenant's token; the response
includes the system-wide token separately as `global_token`. The response is
marked `private, no-store`.

## 3. Endpoint reference

### 3.1 GET /health

Returns app health status.

Response:

```json
{"status": "ok"}
```

### 3.2 GET /ready

Returns readiness only after a database connectivity query succeeds. If PostgreSQL is unavailable, the endpoint returns HTTP 503 with a database-unavailable detail.

Response:

```json
{"status": "ready"}
```

### 3.3 POST /api/v1/telemetry

Receives battery telemetry from the Windows agent. The API commits the latest
endpoint snapshot and a durable outbox event in one PostgreSQL transaction;
rule evaluation and switch commands happen asynchronously in Kafka consumers.

Request schema (`app/schemas/telemetry.py`):

```json
{
  "hardware_uuid": "4b4b2b91-6c32-4d5b-8a9f-2a73b8e94d11",
  "hostname": "LAPTOP-01",
  "ip_address": "192.168.1.20",
  "battery_percentage": 82,
  "charging": false,
  "ac_connected": true,
  "switch_state": null,
  "timestamp": "2025-01-01T12:00:00Z",
  "agent_version": "1.0.0"
}
```

Validation rules:

- `hardware_uuid`: required to create a new endpoint; normalized as a UUID and
  unique across the installation. Existing legacy endpoints may omit it while
  matching their previously registered hostname.
- `hostname`: 1-160 chars
- `ip_address`: 7-64 chars
- `battery_percentage`: integer in range 0-100
- `timestamp`: valid datetime; telemetry older than seven days is rejected
- `agent_version`: 1-50 chars

Success response:

```json
{
  "status": "accepted",
  "hostname": "LAPTOP-01",
  "hardware_uuid": "4b4b2b91-6c32-4d5b-8a9f-2a73b8e94d11",
  "battery_percentage": 82,
  "message": "Telemetry accepted for asynchronous automation processing."
}
```

Behavior:

- validates bearer token
- rejects telemetry older than seven days
- atomically updates or creates the endpoint snapshot and `TelemetryOutbox`
  record; a successful response means this transaction committed
- identifies an endpoint by `hardware_uuid`, while capturing the current
  hostname as mutable display metadata; a hostname change updates the existing
  hardware record rather than creating another laptop
- links a legacy endpoint without a hardware UUID to its UUID on the first
  matching telemetry for that tenant and hostname; existing endpoint IDs,
  mappings, and history are preserved
- relays the event to the `chargepilot.telemetry.v1` Kafka topic using a
  tenant/endpoint ordering key
- automation workers evaluate active mappings with the existing threshold,
  hysteresis, and cooldown rules
- `switch_state` remains in the wire schema for agent compatibility and does
  not override backend rules
- creates a durable desired-state connector command for connector-assigned
  devices; local direct control remains available for unassigned local devices
- records processing outcomes and sends invalid/exhausted events to the
  `chargepilot.telemetry.dlq.v1` dead-letter topic

Processing is at-least-once. Consumers deduplicate by event ID; clients should
not infer that rule evaluation or device control completed from the HTTP
acceptance response. Monitor outbox age, Kafka consumer lag, dead-letter volume,
and command completion.

The PowerShell telemetry payload now includes `hardware_uuid`; its bearer-token
flow is unchanged.
Kafka-specific service settings use the `CHARGEPILOT_` prefix.

### 3.4 GET /api/v1/endpoints

Lists visible endpoint records with tenant ID/name, battery, and online/offline
status. Tenant names are `null` for unassigned endpoints.

Example response:

```json
[
  {
    "id": "...",
    "hostname": "LAPTOP-01",
    "hardware_uuid": "4b4b2b91-6c32-4d5b-8a9f-2a73b8e94d11",
    "tenant_id": "...",
    "tenant_name": "Operations",
    "ip_address": "192.168.1.20",
    "battery": 82,
    "status": "online",
    "mapped_device": "No mapped switch"
  }
]
```

`hardware_uuid` is nullable for endpoints created before the hardware-identity
upgrade. A current agent fills the value on its first matching telemetry
request, keeping the existing endpoint ID and mappings.

### 3.5 PATCH /api/v1/endpoints/{endpoint_id}/tenant

Assigns an unassigned endpoint to an existing tenant. Super Admin only.
Endpoints already assigned to another tenant cannot be transferred through
this operation, and an endpoint with mappings cannot be assigned. After
assignment, reconfigure the laptop agent with the tenant-specific token.

`DELETE /api/v1/endpoints/{endpoint_id}` removes an endpoint and its mappings.

```json
{"tenant_id": "<tenant-uuid>"}
```

## 4. Device API

Authenticated JSON device operations:

- `POST /api/v1/devices/{device_id}/state` accepts `desired_state` and an
  optional `channel_id`. Connector-routed commands are queued durably; local
  devices retain direct LAN control.
- `PUT /api/v1/devices/{device_id}/connector` accepts a connector ID or `null`;
  only tenant administrators/managers can change assignments.
- `DELETE /api/v1/devices/{device_id}` removes the switch and its mappings and
  channels.

### 4.1 GET /api/v1/devices

Returns visible devices ordered by creation time, including `tenant_id` and
`tenant_name`.

### 4.2 POST /api/v1/devices

Creates a device record.

Required fields:

```json
{
  "name": "Living Room Plug",
  "device_id": "abc123",
  "ip_address": "192.168.1.42",
  "device_type": "default",
  "protocol_version": "3.5",
  "encrypted_local_key": "...",
  "enabled": true
}
```

### 4.3 GET /api/v1/devices/{device_id}

Retrieves one device by UUID.

### 4.4 GET /api/v1/devices/{device_id}/channels

Lists all channels for a device.

### 4.5 POST /api/v1/devices/{device_id}/channels

Creates a new device channel.

Example body:

```json
{
  "channel_index": 1,
  "name": "Channel 1",
  "dp_id": "1",
  "enabled": true
}
```

### 4.6 PUT /api/v1/devices/{device_id}

Updates device metadata.

### 4.7 DELETE /api/v1/devices/{device_id}

Deletes a device.

### 4.8 GET /api/v1/devices/channels/{channel_id}

Gets one channel.

### 4.9 PUT /api/v1/devices/channels/{channel_id}

Updates one channel.

### 4.10 DELETE /api/v1/devices/channels/{channel_id}

Deletes one channel.

## 5. Site connector API

Connector endpoints are mounted at `/api/v1/connectors`. Enrollment uses a
one-time enrollment code. Connector heartbeat and command routes use the
connector-specific bearer credential. User-facing management routes use the
signed-in ChargePilot session and normal tenant authorization.

### POST /api/v1/connectors/enroll

Exchange a one-time enrollment code in the `Authorization: Bearer` header for a
connector ID and permanent credential. Codes expire after 15 minutes, are
single-use, and are returned only once.

Request: `{"version":"0.1.1"}`

Response:

```json
{"connector_id":"<uuid>","name":"Office LAN","token":"<secret-returned-once>"}
```

### POST /api/v1/connectors/enrollment-codes

Creates a connector and returns its single-use enrollment code once. Requires
Super Admin or tenant admin/manager access. Tenant admins are scoped to their
own tenant; a Super Admin must provide `tenant_id`.

Request:

```json
{"name":"Office LAN","tenant_id":"<tenant-uuid>"}
```

The response includes `id`, `name`, `enrollment_code`, and `expires_at`. Codes
expire after 15 minutes and are stored only as hashes. The response is marked
`private, no-store`.

### POST /api/v1/connectors/heartbeat

Refreshes last-seen time and connector version. The connector sends its
credential and `{"version":"0.1.1"}`.

### POST /api/v1/connectors/commands/claim

Claims up to one command for that connector. Returns `{"command":null}` when no
work is waiting. State commands include metadata for a registered device
assigned to that connector; local keys are not returned from user-facing
device APIs.

Commands are persisted, leased, expire, and are eligible for bounded reclaim
after connection loss. Operations are allowlisted (`set_state`, `get_status`,
`discover`) and device commands are scoped to the authenticating connector.

### POST /api/v1/connectors/commands/{command_id}/result

Acknowledges a claimed operation:

```json
{"success":true,"result":{"state":true},"error":null}
```

Failures use `success: false`; discovery results contain normalized device
metadata and must not include local keys. Result bodies are size-limited.

### GET /api/v1/connectors/commands/{command_id}

Returns a tenant-scoped command status (`queued`, `leased`, `succeeded`,
`failed`, or `expired`) and sanitized result.

### POST /api/v1/connectors/{connector_id}/revoke

Revokes the connector credential and unassigns its devices. Available to
tenant administrators/managers and the Super Admin.

### DELETE /api/v1/connectors/{connector_id}

Permanently deletes a revoked connector and its command history. Active
connectors must be revoked first. This action is tenant-scoped.

The authenticated **Connectors** page creates enrollment codes, shows
heartbeat status, and serves the connector package. The **Switches** page
assigns devices. Its `POST /devices/scan` discovery endpoint accepts an
optional JSON body:

```json
{"source":"server"}
```

`source` is `server` (the default, scans from the ChargePilot app runtime's
network) or `connector` (delegates to an online site connector). For remote
scans, pass `connector_id` to select a specific connector:

```json
{"source":"connector","connector_id":"<connector-uuid>"}
```

Both paths return normalized switch metadata without local keys. The server
scan requires the app host/container to have LAN access and permit TinyTuya
discovery traffic.

## 6. Mapping API

### 5.1 GET /api/v1/mappings

Returns all endpoint-to-device mappings.

### 5.2 POST /api/v1/mappings

Creates a mapping only when the endpoint and switch belong to the same
tenant. `GET /api/v1/mappings` includes the mapping's tenant name.

Example body:

```json
{
  "endpoint_id": "<endpoint-uuid>",
  "device_id": "<device-uuid>",
  "channel_id": "<channel-uuid>",
  "enabled": true,
  "on_threshold": 79,
  "off_threshold": 99,
  "minimum_state_change_interval": 300
}
```

### 5.3 GET /api/v1/mappings/{mapping_id}

Gets one mapping.

### 5.4 PUT /api/v1/mappings/{mapping_id}

Updates one mapping.

### 5.5 DELETE /api/v1/mappings/{mapping_id}

Deletes one mapping.

## 6. Events API

### 6.1 GET /api/v1/events

Lists automation events ordered by newest first.

Example response:

```json
[
  {
    "id": "...",
    "event_type": "TURN_ON",
    "success": true,
    "reason": "battery 15% reached 79% rule",
    "endpoint_id": "...",
    "device_id": "...",
    "channel_id": "...",
    "previous_state": "false",
    "new_state": "true",
    "created_at": "2025-01-01T12:00:00Z"
  }
]
```

## 7. Data model notes

The main persisted models are:

- `Endpoint`
- `Device`
- `DeviceChannel`
- `Mapping`
- `AutomationEvent`

The app stores the last-seen timestamp, current switch state, last state change timestamp, and event reasons for later debugging.

## 8. Important implementation nuances

- `switch_state` may be explicit in the telemetry payload, but the service still applies rule evaluation when it is `null`.
- Device state is often nested under `dps` rather than a flat boolean field.
- Channel selection is required for multi-gang devices and directly affects the command sent to TinyTuya.
- Generic device labels (`switch`, `plug`, and `outlet`) are normalized to TinyTuya's `default` OutletDevice profile by both direct control and the site connector.
- The API layer is intentionally simple and should be treated as a local admin interface, not a public production API by default.
