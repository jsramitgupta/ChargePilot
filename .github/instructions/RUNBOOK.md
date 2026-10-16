# Operations and Debugging Runbook

## 1. Local startup checklist

1. Create a Python 3.12+ environment.
2. Install dependencies:

```bash
python -m pip install -e .[dev]
```

3. For Compose, copy `.env.example` to `.env` if needed and set unique secret, admin-password, and PostgreSQL-password values. For a manual deployment, configure the `CHARGEPILOT_DATABASE_URL` setting.
4. Ensure PostgreSQL is available and the database URL is valid. Compose also
   starts a private single-node Kafka broker for local development.
5. Start the API, relay, and automation consumer:

```bash
docker compose up --build -d
docker compose ps
```

6. For API-only local development, run:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

API-only mode stores telemetry in the outbox but requires the separate relay
and automation worker processes to publish/process it.

## 2. Important environment variables

From `app/core/config.py`:

- `CHARGEPILOT_SECRET_KEY`
- `CHARGEPILOT_DATABASE_URL`
- `CHARGEPILOT_ENCRYPTION_KEY`
- `CHARGEPILOT_ADMIN_USERNAME`
- `CHARGEPILOT_ADMIN_PASSWORD`
- `CHARGEPILOT_POSTGRES_DB`
- `CHARGEPILOT_POSTGRES_USER`
- `CHARGEPILOT_POSTGRES_PASSWORD`
- `CHARGEPILOT_TELEMETRY_RATE_LIMIT_PER_MINUTE`
- `CHARGEPILOT_ENDPOINT_OFFLINE_TIMEOUT_SECONDS`
- `CHARGEPILOT_KAFKA_BOOTSTRAP_SERVERS`
- `CHARGEPILOT_TELEMETRY_KAFKA_TOPIC`
- `CHARGEPILOT_TELEMETRY_DEAD_LETTER_TOPIC`
- `CHARGEPILOT_TELEMETRY_CONSUMER_GROUP`
- `CHARGEPILOT_KAFKA_SECURITY_PROTOCOL` and SASL/TLS settings for production

The app uses the prefix `CHARGEPILOT_` and ignores extra keys.

## 3. Health and readiness checks

The app exposes:

- `GET /health` → `{"status": "ok"}`
- `GET /ready` → `{"status": "ready"}` only when a database query succeeds; otherwise HTTP 503

These endpoints distinguish process liveness from database readiness.

## 4. Telemetry verification flow

A valid telemetry request must include:

```http
Authorization: Bearer <YOUR_AGENT_TOKEN>
```

The app rejects telemetry older than seven days and accepts only a valid
timestamp plus a bearer token. HTTP acceptance means the endpoint update and
outbox event committed; it does not mean automation or device control has
finished.

The ingress flow is implemented in `app/api/telemetry.py`. The outbox relay
publishes to Kafka; `app/services/automation_processor.py` is run by the
automation consumer.

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

## 5. Debugging connector and TinyTuya issues

When a switch command fails or remains pending, check the following in order:

1. Check `docker compose ps` and recent logs for `app`, `outbox-relay`, and
   `automation-worker`.
2. Check pending rows and age in `telemetry_outbox`; old rows indicate relay
   backlog or Kafka connectivity issues.
3. Inspect Kafka consumer lag and the `chargepilot.telemetry.dlq.v1` topic for
   exhausted/invalid events; do not copy telemetry or tokens into shared logs.
4. Confirm the switch is assigned to the connector physically on its LAN.
5. Check **Connectors** for an online heartbeat and expected connector version.
6. Confirm outbound HTTPS from the connector to ChargePilot and local LAN
   access from the connector to the Tuya switch.
7. Confirm device IP, protocol version, and channel index.
8. Inspect `device_commands` for status, attempts, expiry, and sanitized result.
9. Inspect `automation_events` for the final control outcome.
10. Review connector logs for failure details only; do not log local keys or
   bearer credentials.

The connector polls every few seconds. Commands expire after five minutes and
are leased with bounded retries. A queued or leased command is not a successful
device action. Enrollment codes are single-use and expire after 15 minutes.

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
- `site_connectors`
- `device_commands`

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

- The existing endpoint auth check is separate from connector credentials and
  should not be treated as a substitute for connector-specific authorization.
- Local keys and device secrets must stay out of source control.
- The React frontend and retained Jinja pages share backend sessions; keep
  their authentication redirects and API origins aligned.
- Incorrect channel mapping can look like a successful API call while the wrong relay is switched.
- Connector-assigned cloud devices use confirmed stored state for rule
  evaluation; devices without a connector retain the direct local-host path.
- `CHARGEPILOT_ENCRYPTION_KEY` must match the key used to encrypt stored local
  keys. Restore it with database backups.

### PostgreSQL container cannot be resolved

Keep PostgreSQL unexposed: do not publish its port to the host and do not
hardcode its container IP. With both services in one Compose project, use the
database service name (`db`) and internal port (`5432`) in the app's database
URL. Compose's default network is scoped to one project; separate Portainer
stacks must attach both containers to the same user-defined external Docker
network, with `db` configured as a database network alias.

Diagnose in this order:

1. Inspect the running app's effective `CHARGEPILOT_DATABASE_URL` while
   printing only its host and port; never print the full URL.
2. Compare the app and PostgreSQL container network names.
3. Run `nslookup db` and `pg_isready -h db -p 5432` from temporary containers
   attached to the app's network.
4. If those pass, inspect only recent app logs and verify the database name,
   username, and password configuration without sharing credentials.

Use the health/readiness routes to distinguish a running process from a
database-ready app. A successful `pg_isready` on a different network does not
prove that the app can resolve or reach the database.

## 11. Recovery approach

If the app is behaving unexpectedly:

1. verify the bearer token matches the agent configuration
2. confirm the current battery telemetry is recent
3. inspect the related `Mapping` row for the endpoint
4. confirm the device and channel IDs are still valid
5. inspect the `automation_events` table for the last decision and failure message
6. validate the local Tuya device response payload and channel index

## 12. Scale validation

Never run scale tests against production. For the synthetic PostgreSQL data
test, provision a disposable database whose name ends in `_scale_test`, set
`CHARGEPILOT_SCALE_DATABASE_URL`, and run:

```bash
python scripts/scale_test.py
```

It creates a temporary table with 10,000,001 rows, verifies an indexed
tenant/hostname lookup, prints insertion/query timings, and drops the table
when its connection closes. This validates a database operation, not full app
capacity.

For live load, use k6 against staging with a test tenant's token:

```bash
CHARGEPILOT_API_URL=https://staging.example.com \
CHARGEPILOT_ENDPOINT_TOKEN='<staging-agent-token>' \
ACTIVE_DEVICE_VUS=1000 \
TELEMETRY_CADENCE_SECONDS=60 \
TEST_DURATION=10m \
k6 run tests/scale_telemetry.js
```

Increase virtual users only as staging capacity permits. Record active
endpoints, request rate, latency percentiles, errors, outbox age, Kafka lag,
database utilization, and completed connector commands. A synthetic 10M-row
result does not prove 1M active-device throughput.
