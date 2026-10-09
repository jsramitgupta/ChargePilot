# ChargePilot Project Reference Pack

This directory captures the current implementation state of the ChargePilot repository so a future developer or Claude-based agent can understand the product, architecture, runtime flow, and deployment constraints without reverse-engineering the codebase.

## Included reference documents

- [ARCHITECTURE.md](ARCHITECTURE.md) — architecture, runtime boundaries, and current module layout.
- [PRD.md](PRD.md) — product intent, user goals, functional requirements, and current scope.
- [TLD.md](TLD.md) — detailed technical design for the monolith, services, flows, and data model.
- [API_SPEC.md](API_SPEC.md) — the current API surface and payload contracts.
- [DEPLOYMENT.md](DEPLOYMENT.md) — environment, Docker, and runtime setup notes.
- [RUNBOOK.md](RUNBOOK.md) — debugging, validation, and operational checklist.

## What this codebase does now

The project is a local-first battery automation platform for Windows laptops and local Tuya devices. In its current form it includes:

- Windows laptop telemetry ingestion via a PowerShell agent
- endpoint-to-device mappings and automation rules
- local Tuya device discovery and state control over the LAN
- a SmartLife/Tuya QR login flow for linked-device recovery and local key matching
- a wizard-based device onboarding flow using AJAX and local session state
- SSE-driven UI updates and current-state refreshes

## Current implementation facts captured from the repo

- Runtime stack: Python 3.12, FastAPI, SQLAlchemy 2.x, PostgreSQL, TinyTuya, tuya-device-sharing-sdk, Jinja2, pytest.
- App entrypoint: `app/main.py` renders HTML dashboard pages and also hosts the wizard flow for SmartLife integration.
- Settings prefix: `CHARGEPILOT_` via `app/core/config.py`.
- Database bootstrap: `create_db_and_tables()` runs on startup and ensures missing columns are added.
- Telemetry auth: bearer token validation is still kept simple and should be hardened before production exposure.
- SmartLife flow: `app/services/smartlife_service.py` generates QR images, polls login results, saves session state, and refreshes QR on immediate expiry.
- Rule defaults: `on_threshold=79`, `off_threshold=99`, `minimum_state_change_interval=300`.
- Device discovery: `tinytuya` scan and local wizard form support auto-matching local key and IP fields.
- UI pattern: the app uses Jinja templates plus some AJAX and toast-based interactions rather than a separate frontend framework.

## File map relevant to AI understanding

```text
app/main.py                 # app bootstrap, HTML pages, wizard routes
app/api/*.py               # routers for telemetry, devices, events, and mappings
app/core/*.py              # settings, DB session, auth helpers
app/models/*.py            # ORM schema
app/services/*.py          # device logic, rule logic, SmartLife flow, SSE
app/templates/*.html       # dashboard and wizard pages
app/static/*.css           # styling
agent/BatteryAgent.ps1     # telemetry sender
agentv2/                  # alternate agent flow or future version
docker-compose.yml         # runtime config
tests/                    # validation cases
```

## Current status

The repository is a working local-first product prototype with an expanded onboarding flow. It is meant to be self-hosted and local-only, and the technical details in these documents should be treated as the authoritative implementation reference for this codebase.

## Claude rebuild guidance

If this project has to be rebuilt from scratch, the safe order is:

1. build the FastAPI app and core DB schema
2. add telemetry ingestion and mapping logic
3. add Tuya discovery and local device control abstraction
4. add battery rule engine and automation event logging
5. add SmartLife QR onboarding and local-key matching flow
6. add template-based UI and SSE for operational visibility

This order preserves the system's practical local-first architecture and minimizes unnecessary churn.
