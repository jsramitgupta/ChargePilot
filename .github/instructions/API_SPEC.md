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
- `/api/v1/mappings`
- `/api/v1/events`

## 2. Authentication model

Telemetry ingestion requires a bearer token in the `Authorization` header.

Example:

```http
Authorization: Bearer <YOUR_AGENT_TOKEN>
```

The validation logic lives in `app/services/endpoint_service.py`. It accepts a tenant's configured agent token or the system-wide global token, which is generated randomly when the database is first initialized.

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

Receives battery telemetry from the Windows agent and may trigger a switch action based on the mapping rule.

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
- `timestamp`: valid datetime, must be less than 10 minutes old
- `agent_version`: 1-50 chars

Success response:

```json
{
  "status": "accepted",
  "hostname": "LAPTOP-01",
  "battery_percentage": 82,
  "message": "Telemetry accepted and endpoint updated."
}
```

Behavior:

- validates bearer token
- rejects stale telemetry over 600 seconds old
- updates or creates the endpoint record
- loads all active mappings for that endpoint
- reads live switch state via TinyTuya
- applies explicit `switch_state` override when present
- otherwise calls the battery rule engine
- writes an automation event record

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

## 5. Mapping API

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
