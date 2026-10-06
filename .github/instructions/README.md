# ChargePilot Project Reference Pack

This directory captures the actual implementation state of the ChargePilot repository so an AI agent or future developer can understand the product, architecture, runtime flow, and deployment constraints without reverse-engineering the codebase.

## Included reference documents

- [ARCHITECTURE.md](ARCHITECTURE.md) — runtime architecture, module boundaries, startup flow, and operational model.
- [PRD.md](PRD.md) — product intent, user goals, requirements, and constraints as implemented in the codebase.
- [TLD.md](TLD.md) — detailed technical design for the monolith, data model, and service boundaries.
- [API_SPEC.md](API_SPEC.md) — exact route surface and payload contracts for the API.
- [DEPLOYMENT.md](DEPLOYMENT.md) — environment variables, compose setup, and deployment steps.
- [RUNBOOK.md](RUNBOOK.md) — local setup, debugging checklist, and operational guidance.

## What this codebase does

The project is a local battery-automation system for Windows laptops:

- a laptop agent sends battery telemetry over HTTPS
- the backend verifies bearer-token access
- the app matches the laptop endpoint to a configured device mapping
- a rule engine decides whether a switch should be toggled
- TinyTuya issues the local LAN command to a smart switch or outlet
- automation events are stored for later inspection

## Implementation facts captured from the repo

- Runtime stack: Python 3.12, FastAPI, SQLAlchemy 2.x, PostgreSQL, TinyTuya, Jinja2, pytest.
- App entrypoint: `app/main.py` mounts static files, registers routers, and renders dashboard pages.
- Settings prefix: `CHARGEPILOT_` via `app/core/config.py`.
- Database bootstrap: `create_db_and_tables()` runs on app startup and ensures schema drift columns are added.
- Telemetry authentication: bearer token is parsed by `app/core/security.py` and compared against the static `test-endpoint-token`.
- Rule defaults: `on_threshold=79`, `off_threshold=99`, `minimum_state_change_interval=300`.
- Device state normalization: `TuyaService._extract_dps()` handles nested `dps`, `data.dps`, and `status` payloads.
- Agent contract: `agent/BatteryAgent.ps1` sends `switch_state`, `battery_percentage`, `charging`, `ac_connected`, and timestamp metadata.

## File map relevant to AI understanding

```text
app/main.py                 # app bootstrap and HTML views
app/api/*.py               # routers
app/core/*.py              # settings, DB, security
app/models/*.py            # database schema
app/services/*.py          # rule engine and TinyTuya service
app/schemas/*.py           # API models
agent/BatteryAgent.ps1     # telemetry sender
docker-compose.yml         # runtime container config
tests/                    # validation cases
```

## Current status

The repository is structured as a small local-first product prototype. It is meant to be self-hosted and local-only, and the technical details in these documents should be treated as the authoritative implementation reference for this codebase.
