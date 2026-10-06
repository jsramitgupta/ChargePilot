# ChargePilot

ChargePilot is a self-hosted, local-first battery automation platform for Windows laptops. The app receives telemetry from laptop agents, evaluates battery thresholds, and turns local Tuya switches or plugs on or off without relying on the Tuya cloud for day-to-day automation.

## Project summary

The current codebase is a modular monolith built with FastAPI and SQLAlchemy. It contains:

- a battery telemetry ingestion API
- device, endpoint, mapping, and event models
- a hysteresis-based battery rule engine
- TinyTuya wrappers for local switch discovery and control
- Jinja-rendered dashboard pages for operational supervision
- a PowerShell laptop agent that sends runtime battery data

## Runtime stack

- Python 3.12+
- FastAPI 0.115.0
- SQLAlchemy 2.0.32
- PostgreSQL / psycopg
- Pydantic + pydantic-settings
- TinyTuya 1.20.0
- Jinja2 templates
- pytest for automated checks

## Repository layout

```text
.
├── app/
│   ├── api/                 # REST routers for health, telemetry, devices, mappings, events
│   ├── core/                # settings, DB session, startup bootstrap, security helpers
│   ├── models/              # SQLAlchemy ORM models
│   ├── schemas/             # Pydantic request/response contracts
│   ├── services/            # battery rule logic and Tuya abstraction
│   ├── static/              # CSS assets
│   ├── templates/           # Jinja dashboard and admin HTML pages
│   └── main.py              # FastAPI app setup and HTML routes
├── agent/
│   ├── BatteryAgent.ps1               # Windows laptop telemetry sender
│   └── CreateAgentScheduledTask.ps1   # creates the recurring Windows task
├── docker/
│   └── Dockerfile
├── tests/
│   ├── api/
│   ├── integration/
│   └── unit/
├── docker-compose.yml
├── pyproject.toml
├── README.md
├── .github/instructions/
│   ├── README.md
│   ├── ARCHITECTURE.md
│   ├── API_SPEC.md
│   ├── PRD.md
│   ├── DEPLOYMENT.md
│   ├── RUNBOOK.md
│   ├── TLD.md
│   └── ...
└── alembic.ini
```

## Core runtime behavior

### Telemetry ingestion

The battery agent posts JSON telemetry to the service at `/api/v1/telemetry`.

Expected payload:

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

The request is authenticated with a bearer token passed in the `Authorization` header. The current implementation validates a static value from `validate_endpoint_auth()` and compares it to `test-endpoint-token`.

### Automation rule

Battery decisions are evaluated in `app/services/rule_engine.py` and apply hysteresis with a minimum interval:

- default `on_threshold = 79`
- default `off_threshold = 99`
- default `minimum_state_change_interval = 300` seconds

The app prevents rapid toggling and only fires if the battery crosses threshold values with enough time since the last state change.

### Local switch control

`app/services/tuya_service.py` encapsulates TinyTuya interactions:

- local discovery via `deviceScan()`
- request normalization for nested `dps` payloads
- channel-specific state checks and toggles
- structured logging of device commands and results

This service is intentionally isolated so the rest of the app avoids direct TinyTuya dependency leakage.

## Environment configuration

The application reads settings using `pydantic-settings` with the environment prefix `CHARGEPILOT_`.

Important variables:

```env
CHARGEPILOT_SECRET_KEY=...
CHARGEPILOT_DATABASE_URL=postgresql+psycopg://user:pass@host:5432/chargepilot
CHARGEPILOT_ENCRYPTION_KEY=...
CHARGEPILOT_ADMIN_USERNAME=admin
CHARGEPILOT_ADMIN_PASSWORD=...
CHARGEPILOT_TELEMETRY_RATE_LIMIT_PER_MINUTE=60
CHARGEPILOT_ENDPOINT_OFFLINE_TIMEOUT_SECONDS=600
```

## Quick start

1. Create a Python environment (3.12+).
2. Install dependencies:

```bash
python -m pip install -e .[dev]
```

3. Configure `.env` with the values above.
4. Start the app:

```bash
uvicorn app.main:app --reload
```

5. Optionally run with Docker Compose:

```bash
docker compose up --build -d
```

## Docker deployment notes

The project includes a Compose file that exposes port `8000` and starts the app with:

```bash
python -c "from app.core.database import create_db_and_tables; create_db_and_tables()"
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The app creates its schema automatically when it boots, using `create_db_and_tables()` from `app/core/database.py`.

## Operational observations from the codebase

- The app treats endpoint telemetry as the source of truth for device state and mapping decisions.
- Device commands are routed by `device_id` and `channel` index, not just a flat boolean.
- A device can expose its state under `dps`, `data.dps`, or `status` payloads.
- The dashboard is server-rendered via Jinja templates, not a separate frontend application.
- Authentication is intentionally minimal in the current implementation and should be hardened before production use.

## Documentation pack

This repo includes a deeper reference pack in [.github/instructions/README.md](.github/instructions/README.md) covering architecture, API contracts, deployment, runbook, and technical design.

## Validation and testing

The project includes automated checks under `tests/` for the rule engine and API-level behaviors.

Examples:

```bash
pytest tests/unit/test_rule_engine.py -q
pytest tests/api/test_device_mapping_crud.py -q
```

## Notes for AI agents and future maintainers

This codebase is a compact local automation system, not a distributed SaaS product. The most important design constraints are:

- local network access is required for Tuya control
- telemetry auth is currently a bearer token check with a test token
- device actions depend on the actual switch payload format
- the rule engine uses hysteresis and a cooldown window to avoid chatter
- all automation outcomes are persisted in the database as events

The technical docs in [.github/instructions](.github/instructions) are meant to serve as the implementation reference for future rebuilds and deeper automated analysis.
