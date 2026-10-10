# Deployment Guide

## 1. Deployment model

The documented fresh deployment runs ChargePilot and PostgreSQL as Compose services. PostgreSQL data is persisted in a named volume; the app waits for the database health check before starting.

The app must be able to reach Tuya devices on the LAN for discovery and local control. A Docker bridge network may limit LAN broadcast discovery; if so, run the app with suitable host networking or deploy it directly on the LAN.

## 2. Prerequisites

- Python 3.12+ for local installs
- Docker Desktop or Docker Engine with Compose
- local network access to the Tuya device
- Windows laptop capable of running `agent/BatteryAgent.ps1`

## 3. Environment variables

Compose reads the root `.env` file for variable substitution. The app itself reads `CHARGEPILOT_` settings from its process environment.

Required Compose settings:

```env
CHARGEPILOT_SECRET_KEY=<unique-random-secret>
CHARGEPILOT_ENCRYPTION_KEY=<unique-random-value>
CHARGEPILOT_ADMIN_USERNAME=admin
CHARGEPILOT_ADMIN_PASSWORD=<unique-strong-password>
CHARGEPILOT_POSTGRES_DB=chargepilot
CHARGEPILOT_POSTGRES_USER=chargepilot
CHARGEPILOT_POSTGRES_PASSWORD=<url-safe-random-password>
```

Other supported settings include:

```env
CHARGEPILOT_TELEMETRY_RATE_LIMIT_PER_MINUTE=60
CHARGEPILOT_ENDPOINT_OFFLINE_TIMEOUT_SECONDS=600
```

Generate random values rather than using placeholders. Python's `secrets.token_urlsafe(32)` is suitable for the secret key and PostgreSQL password; keep the PostgreSQL password URL-safe because Compose embeds it in the SQLAlchemy URL. The `.env` file is ignored by Git and must remain private. `CHARGEPILOT_ENCRYPTION_KEY` is currently reserved configuration and is not yet used by the local-key storage implementation.

Compose sets `CHARGEPILOT_ENVIRONMENT=production`; startup rejects a non-PostgreSQL URL, default/short secret keys, and short admin passwords.

## 4. Fresh Docker Compose deployment

From the repository root, create and populate the ignored environment file:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
python -c "import secrets; print('CHARGEPILOT_SECRET_KEY=' + secrets.token_urlsafe(32)); print('CHARGEPILOT_ENCRYPTION_KEY=' + secrets.token_urlsafe(32)); print('CHARGEPILOT_POSTGRES_PASSWORD=' + secrets.token_urlsafe(32)); print('CHARGEPILOT_ADMIN_PASSWORD=' + secrets.token_urlsafe(24))"
```

Copy the generated values into `.env` and set the admin username. Save the admin password securely; it is used to sign in after initialization.

Validate configuration and start the deployment:

```bash
docker compose config
docker compose up --build -d
```

The Compose configuration defines PostgreSQL 16, a persistent volume, PostgreSQL health checking, and an app `/ready` health check. The app container runs as an unprivileged user. Check logs with `docker compose logs -f app`; stop services with `docker compose down`. This preserves the database volume. To permanently delete the database and all stored ChargePilot data, use `docker compose down -v`.

`/health` reports process liveness. `/ready` executes a database query and returns HTTP 503 while PostgreSQL is unavailable.

## 5. Local Python deployment

Install dependencies:

```bash
python -m pip install -e .[dev]
```

Configure `CHARGEPILOT_DATABASE_URL` to a reachable, existing PostgreSQL database, set strong secret/admin values, then run:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The app creates its schema and initial admin account at startup. The database role must own the application tables or have privileges to create and alter them.

## 6. Database initialization and upgrades

On a genuinely empty database, startup uses SQLAlchemy `Base.metadata.create_all()` followed by the compatibility column and foreign-key adjustments in `app/core/database.py`. The `users.created_at` column is PostgreSQL `TIMESTAMPTZ`, matching its server-side `now()` default.

The repository does not currently contain Alembic revision files. `create_all()` is not a versioned migration system and does not safely upgrade arbitrary existing schemas. Back up existing data and plan a dedicated schema migration before deploying schema-changing updates to an existing installation.

## 7. Windows laptop agent deployment

The PowerShell agent is located at `agent/BatteryAgent.ps1`.

```powershell
powershell -ExecutionPolicy Bypass -File .\agent\BatteryAgent.ps1 -ServerUrl "http://YOUR_SERVER:8000" -EndpointToken "YOUR_ENDPOINT_TOKEN" -AgentVersion "1.0.0"
```

Use `agent/CreateAgentScheduledTask.ps1` to register the recurring Windows task. The agent sends hostname, IP address, battery percentage, charging/AC state, switch state, timestamp, and agent version.

Agent tokens are generated randomly for new installations and can be viewed or rotated from the authenticated **Install Agent** page. Existing deployments initialized with the historical `test-endpoint-token` should rotate it after upgrading.

## 8. Device and mapping workflow

1. Register the Tuya device in the app or via database records.
2. Save its device ID, local key, IP, protocol version, and device type.
3. Create the endpoint and mapping records.
4. Ensure the mapping points to the intended device and channel.
5. Confirm the channel index and thresholds before enabling automation.

The default thresholds are `on_threshold = 79`, `off_threshold = 99`, and `minimum_state_change_interval = 300` seconds.

## 9. Operational checklist

- Keep `.env` and database backups private; do not commit secrets.
- Confirm `docker compose ps` shows both services healthy.
- Keep PostgreSQL storage in the named volume and back it up before updates.
- Verify the Tuya device is reachable on the LAN and accepts local commands.
- Confirm device protocol version and channel index.
- Inspect automation events after failed or unexpected state changes.

## 10. Validation commands

```bash
pytest tests/unit/test_rule_engine.py -q
pytest tests/api/test_device_mapping_crud.py -q
```

## 11. Important cautions

- The current authentication flow is intentionally simple and should not be treated as a complete production security boundary.
- Local device keys are not currently encrypted at rest despite the reserved encryption-key setting.
- `TinyTuya` payloads vary by device family; do not assume a flat boolean status.
- The app writes event rows for state transitions so failures remain diagnosable.
