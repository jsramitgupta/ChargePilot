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

The validation logic lives in `app/services/endpoint_service.py`. It accepts a tenant's configured agent token or the system-wide global token, which is generated randomly when the database is first initialized.

Browser sign-in uses the session cookie set by `POST /login`. The API-host
`GET /login` and `GET /register` routes redirect to the configured frontend;
the login and registration screens are served by the React frontend.

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
  "battery_percentage": 82,
  "message": "Telemetry accepted for asynchronous automation processing."
}
```

Behavior:

- validates bearer token
- rejects telemetry older than seven days
- atomically updates or creates the endpoint snapshot and `TelemetryOutbox`
  record; a successful response means this transaction committed
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

The PowerShell telemetry payload and endpoint token flow are unchanged.
Kafka-specific service settings use the `CHARGEPILOT_` prefix.

### 3.4 GET /api/v1/endpoints

Lists endpoint records with battery and online/offline status.

Example response:

```json
[
  {
    "id": "...",
    "hostname": "LAPTOP-01",
    "ip_address": "192.168.1.20",
    "battery": 82,
    "status": "online",
    "mapped_device": "No mapped switch"
  }
]
```

## 4. Device API

### 4.1 GET /api/v1/devices

Returns all devices ordered by creation time.

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

Connector endpoints are mounted at `/api/v1/connectors`. Except for enrollment,
they use the connector-specific bearer credential rather than an endpoint
agent token. Command status reads require the signed-in ChargePilot session
and normal tenant authorization.

### POST /api/v1/connectors/enroll

Exchange a one-time enrollment code in the `Authorization: Bearer` header for a
connector ID and permanent credential. Codes expire after 15 minutes, are
single-use, and are returned only once.

Request: `{"version":"0.1.0"}`

Response:

```json
{"connector_id":"<uuid>","name":"Office LAN","token":"<secret-returned-once>"}
```

### POST /api/v1/connectors/heartbeat

Refreshes last-seen time and connector version. The connector sends its
credential and `{"version":"0.1.0"}`.

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

Creates a mapping.

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
- The API layer is intentionally simple and should be treated as a local admin interface, not a public production API by default.
