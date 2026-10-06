# Operations and Debugging Runbook

## 1. Local startup checklist

1. Create a Python 3.12+ environment.
2. Install dependencies:

```bash
python -m pip install -e .[dev]
```

3. Create a `.env` file with the environment variables expected by `app/core/config.py`.
4. Ensure PostgreSQL is available and the database URL is valid.
5. Start the app:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

6. Optionally validate with Docker:

```bash
docker compose up --build -d
```

## 2. Important environment variables

From `app/core/config.py`:

- `CHARGEPILOT_SECRET_KEY`
- `CHARGEPILOT_DATABASE_URL`
- `CHARGEPILOT_ENCRYPTION_KEY`
- `CHARGEPILOT_ADMIN_USERNAME`
- `CHARGEPILOT_ADMIN_PASSWORD`
- `CHARGEPILOT_TELEMETRY_RATE_LIMIT_PER_MINUTE`
- `CHARGEPILOT_ENDPOINT_OFFLINE_TIMEOUT_SECONDS`

The app uses the prefix `CHARGEPILOT_` and ignores extra keys.

## 3. Health and readiness checks

The app exposes:

- `GET /health` → `{"status": "ok"}`
- `GET /ready` → `{"status": "ready"}`

These endpoints help confirm the server is listening and has finished startup initialization.

## 4. Telemetry verification flow

A valid telemetry request must include:

```http
Authorization: Bearer test-endpoint-token
```

The app rejects stale payloads older than 10 minutes and accepts only a valid timestamp plus a bearer token.

The telemetry posting flow is implemented in `app/api/telemetry.py` and can be checked with a request such as:

```bash
curl -X POST http://localhost:8000/api/v1/telemetry \
  -H "Authorization: Bearer test-endpoint-token" \
  -H "Content-Type: application/json" \
  -d '{
    "hostname": "LAPTOP-01",
    "ip_address": "192.168.1.20",
    "battery_percentage": 82,
    "charging": false,
    "ac_connected": true,
    "switch_state": null,
    "timestamp": "2026-10-06T12:00:00Z",
    "agent_version": "1.0.0"
  }'
```

## 5. Debugging TinyTuya issues

When a switch command fails or appears to do nothing, check the following in order:

1. Confirm the device can be reached on the same LAN.
2. Confirm the `ip_address` and `encrypted_local_key` are correct.
3. Confirm the `protocol_version` is valid for the target device.
4. Confirm `channel_index` is correct for multi-gang devices.
5. Confirm the app reads state from `dps`/`data.dps` rather than assuming a flat boolean.
6. Review the server logs for `TinyTuya` request and result payloads.

## 6. Real payload debugging facts from the codebase

The `TuyaService` code specifically normalizes nested DPS payloads, including patterns like:

```json
{"protocol": 4, "dps": {"1": true}}
{"protocol": 4, "dps": {"1": false}}
```

It also supports `status` and `data.dps` payloads when reading the current state.

## 7. Rule-engine debugging

The current rule logic is defined in `app/services/rule_engine.py`.

Defaults are:

- `on_threshold = 79`
- `off_threshold = 99`
- `minimum_state_change_interval = 300`

The rule intentionally uses a hysteresis window to prevent rapid toggling. If the switch is already on, the app will not turn it on again until the threshold and cooldown requirements permit a new action.

## 8. Database and event debugging

Check the following tables after runtime events:

- `endpoints`
- `devices`
- `device_channels`
- `mappings`
- `automation_events`

The most useful operational event data is in `automation_events`, which stores:

- `event_type`
- `reason`
- `previous_state`
- `new_state`
- `success`
- `error`

## 9. Common verification commands

```bash
pytest tests/unit/test_rule_engine.py -q
pytest tests/api/test_device_mapping_crud.py -q
```

To run the app locally:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8010
```

## 10. Known operational cautions

- The current endpoint auth check is intentionally static and should not be treated as hardened production authentication.
- Local keys and device secrets must stay out of source control.
- The dashboard is server-side HTML and may not reflect modern frontend conventions.
- Incorrect channel mapping can look like a successful API call while the wrong relay is switched.
- The app updates device state based on a live status read before deciding whether to send a command.

## 11. Recovery approach

If the app is behaving unexpectedly:

1. verify the bearer token matches the agent configuration
2. confirm the current battery telemetry is recent
3. inspect the related `Mapping` row for the endpoint
4. confirm the device and channel IDs are still valid
5. inspect the `automation_events` table for the last decision and failure message
6. validate the local Tuya device response payload and channel index
