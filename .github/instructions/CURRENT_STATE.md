# Current State Summary

This file is the short operational summary for the repository as it stands today.

## Product
ChargePilot is a cloud-capable, local-first battery automation platform for Windows laptops. It monitors laptop battery state and controls local Tuya switches through an outbound-HTTPS site connector on each device LAN. The system includes SmartLife/Tuya QR onboarding and connector-based LAN discovery.

## Core runtime stack
- FastAPI
- SQLAlchemy
- PostgreSQL
- React, TypeScript, Tailwind CSS, and Vite for the interactive frontend
- TinyTuya
- HTTPS-polling site connector with PostgreSQL-backed commands
- tuya-device-sharing-sdk
- Jinja2 templates remain in use for workflows that have not moved to React
- qrcode
- pytest

## Frontend and rendering
The frontend is a Vite-built React application in `frontend/`. It currently
provides sign-in/registration, dashboard, switches, mappings, endpoints, and
events pages. It shares the original `app/static/style.css` design tokens and
theme behavior; the authenticated top navigation is left aligned. FastAPI
continues to serve Jinja pages for the remaining operational/admin workflows.
Keep the React and Jinja experiences consistent and avoid replacing real API
behavior with fabricated frontend state.

## Current primary workflows
1. PowerShell agent posts telemetry to /api/v1/telemetry.
2. Server validates endpoint token and timestamp.
3. Active mappings are evaluated using battery thresholds and cooldown logic.
4. A durable desired-state command is routed to the switch's assigned connector.
5. The connector controls the device locally and acknowledges; resulting events/state are exposed in the UI.
6. Users can discover LAN devices through a connector and pair them through SmartLife/Tuya QR login.
7. SmartLife linked devices can be matched to connector discovery results to fill IP and local key fields.
8. The React frontend consumes the API and keeps session cookies; browser-facing
   API/frontend origins are provided by runtime `CHARGEPILOT_API_URL` and
   `CHARGEPILOT_FRONTEND_URL` configuration.

## Current important service modules
- app/services/rule_engine.py — threshold logic and hysteresis
- app/services/tuya_service.py — local device control / discovery
- app/services/smartlife_service.py — QR generation and linked-device polling
- app/services/broadcaster.py — SSE updates
- app/services/connector_service.py — connector identity, command queue, lease, and result handling
- connector/chargepilot_connector.py — site-side TinyTuya runtime

## Current known implementation risks
- bearer-token validation remains intentionally minimal
- the database bootstrap uses `create_all()` plus compatibility SQL, not
  versioned Alembic revisions; schema changes need a reviewed migration plan
- device payloads vary by Tuya firmware and hardware model
- SmartLife QR tokens may expire or respond invalidly; the system refreshes QR automatically when needed
- local keys and session data are sensitive and should never be committed to source control
- keep `CHARGEPILOT_ENCRYPTION_KEY` stable and backed up; it protects stored device local keys
- the cloud server does not scan or route to private device LANs; use a healthy connector and explicit device assignment
- PostgreSQL should stay private with no published host port. In a single
  Compose project the database hostname is the service name `db`; if Portainer
  deploys app and database as separate stacks, attach both to the same
  user-defined external network and give the database the `db` network alias.

The full connector design, operational contract, and deployment plan is
documented in [CLOUD_CONNECTOR_ARCHITECTURE.md](CLOUD_CONNECTOR_ARCHITECTURE.md).

## Persistent implementation guidance
- Preserve the ChargePilot product terminology, business rules, existing HTML
  templates, and shared stylesheet when extending the UI. Keep React pages
  responsive and aligned in both light and dark themes.
- Prefer concrete, repository-grounded changes with working backend
  integration; do not add mock data, dead-end controls, unrelated features, or
  a separate replacement backend.
- For deployment diagnosis, check the effective `CHARGEPILOT_DATABASE_URL`
  host without exposing its credentials, then verify DNS and PostgreSQL
  readiness from a temporary container on the app's Docker network. Never
  hardcode a container IP or publish PostgreSQL just to make the connection
  work.
- Pytest must always use its isolated SQLite database. `tests/conftest.py`
  intentionally overrides database settings before application imports so
  developer or production environment variables cannot send tests to a real
  database.
- Give operators safe, copyable commands and explain what each result means.
  Keep credentials and database URLs out of logs, screenshots, and shared
  diagnostics.

## Instructions for future AI builds
Use the special docs under .github/instructions as the canonical source of truth for product, technical design, architecture, and deployment contexts. When rebuilding, do not assume the app is only a battery rule engine; it has a SmartLife/Tuya onboarding architecture as well.
