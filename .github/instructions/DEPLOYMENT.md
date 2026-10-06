# Deployment Guide

## 1. Deployment model

The project is designed to run as a single Python app and a PostgreSQL database, with the database managed outside the app process. In the included `docker-compose.yml`, the application container exposes port `8000` and expects a PostgreSQL connection string in the environment.

The code assumes the following topology:

- PostgreSQL: external database service or containerized database
- ChargePilot app: FastAPI process running in Docker or locally
- Windows laptop agent: PowerShell sender using the app API
- Tuya switch: reachable over the local network

## 2. Prerequisites

- Python 3.12+
- Docker Desktop or Docker Engine
- PostgreSQL instance available to the app
- local network access to the Tuya device
- Windows laptop capable of running `agent/BatteryAgent.ps1`

## 3. Environment variables

The app loads values with the prefix `CHARGEPILOT_` from `.env` via `pydantic-settings`.

Minimum required values:

```env
CHARGEPILOT_SECRET_KEY=replace-me
CHARGEPILOT_DATABASE_URL=postgresql+psycopg://chargepilot:chargepilot@localhost:5432/chargepilot
CHARGEPILOT_ENCRYPTION_KEY=replace-with-32-byte-base64-key
CHARGEPILOT_ADMIN_USERNAME=admin
CHARGEPILOT_ADMIN_PASSWORD=change-me
```

Other supported settings:

```env
CHARGEPILOT_TELEMETRY_RATE_LIMIT_PER_MINUTE=60
CHARGEPILOT_ENDPOINT_OFFLINE_TIMEOUT_SECONDS=600
```

The compose file sets the app environment to read these values from `.env` and passes them into the container.

## 4. Docker Compose deployment

The repository includes the following container config:

```yaml
services:
  app:
    build:
      context: .
      dockerfile: docker/Dockerfile
    env_file:
      - .env
    environment:
      CHARGEPILOT_DATABASE_URL: ${CHARGEPILOT_DATABASE_URL:-postgresql+psycopg://chargepilot:chargepilot@host.docker.internal:5432/chargepilot}
    ports:
      - "8000:8000"
    command: >
      sh -c "python -c \"from app.core.database import create_db_and_tables; create_db_and_tables()\" && uvicorn app.main:app --host 0.0.0.0 --port 8000"
```

Start it with:

```bash
docker compose up --build -d
```

Check logs with:

```bash
docker compose logs -f app
```

Stop it with:

```bash
docker compose down
```

## 5. Local Python deployment

Install dependencies:

```bash
python -m pip install -e .[dev]
```

Then run:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The app calls `create_db_and_tables()` on startup, so the base schema should be created automatically when the database is reachable.

## 6. Database setup

The application expects a PostgreSQL database. The default development connection string is:

```env
CHARGEPILOT_DATABASE_URL=postgresql+psycopg://chargepilot:chargepilot@localhost:5432/chargepilot
```

If running inside Docker and PostgreSQL is on the host machine, use `host.docker.internal` in the connection string:

```env
CHARGEPILOT_DATABASE_URL=postgresql+psycopg://chargepilot:chargepilot@host.docker.internal:5432/chargepilot
```

The schema is created by `app.core.database.create_db_and_tables()` and `Base.metadata.create_all()`.

## 7. Windows laptop agent deployment

The PowerShell agent is located at `agent/BatteryAgent.ps1`.

Default usage:

```powershell
powershell -ExecutionPolicy Bypass -File .\agent\BatteryAgent.ps1 -ServerUrl "http://YOUR_SERVER:8000" -EndpointToken "YOUR_ENDPOINT_TOKEN" -AgentVersion "1.0.0"
```

Use the scheduled-task helper at `agent/CreateAgentScheduledTask.ps1` to register the recurring Windows task.

The agent sends:

- hostname
- ip_address
- battery_percentage
- charging
- ac_connected
- switch_state
- timestamp
- agent_version

## 8. Endpoint token setup

The bearer token flow is implemented in `app/services/endpoint_service.py` and `app/core/security.py`.

Current default compatibility value:

```text
test-endpoint-token
```

In production, this should be replaced with a strong secret and the auth logic should be hardened to avoid hard-coded values.

## 9. Device and mapping workflow

Once the laptop is reporting telemetry:

1. Register the Tuya device in the app or via database records.
2. Save the `device_id`, local key, IP, protocol version, and device type.
3. Create the endpoint and mapping records.
4. Ensure the mapping points to the intended device and channel.
5. Let the battery rule engine operate using the configured thresholds.

The default threshold values in the rule engine are:

- `on_threshold = 79`
- `off_threshold = 99`
- `minimum_state_change_interval = 300`

## 10. Operational checklist

- Keep secrets in `.env` or the environment, not in Git.
- Ensure the PostgreSQL database is reachable from the app container or local process.
- Verify the Tuya device is on the same LAN and accepts local commands.
- Confirm the device `protocol_version` and `device_type` are correct.
- Make sure the `channel_index` matches the actual switch channel.
- Check the automation event table after any failed or unexpected state change.

## 11. Validation commands

```bash
pytest tests/unit/test_rule_engine.py -q
pytest tests/api/test_device_mapping_crud.py -q
```

Manual app startup:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## 12. Important cautions

- The current auth flow is intentionally simple and should not be treated as production-grade security.
- `TinyTuya` payloads vary by device/family and must not be assumed to be a flat boolean.
- A no-op in the hardware layer can still appear as a successful app response if the target channel or protocol is wrong.
- The app writes event rows for state transitions so failures remain diagnosable.
