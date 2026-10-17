# Current State Summary

This file is the short operational summary for the repository as it stands today.

## Product
ChargePilot is a cloud-capable, local-first battery automation platform for Windows laptops. It monitors laptop battery state and controls local Tuya switches through an outbound-HTTPS site connector on each device LAN. The system includes SmartLife/Tuya QR onboarding and connector-based LAN discovery.

## Core runtime stack
- FastAPI
- SQLAlchemy
- PostgreSQL for transactional state and outbox
- Apache Kafka for durable telemetry event transport
- React, TypeScript, Tailwind CSS, and Vite for the interactive frontend
- TinyTuya
- HTTPS-polling site connector with PostgreSQL-backed durable commands
- tuya-device-sharing-sdk
- Jinja2 templates remain in use for workflows that have not moved to React
- qrcode
- pytest

## Frontend and rendering
The frontend is a Vite-built React application in `frontend/`. It currently
provides sign-in/registration, dashboard, switches, mappings, endpoints,
events, connector administration, profile, user/tenant administration, agent
setup, and super-admin account pages. Authenticated in-app navigation stays
within React Router, with the dev server serving the SPA for direct page loads;
API-host downloads remain resource links rather than page navigation. React
admin pages use authenticated, tenant-scoped API data and preserve the existing
server-side authorization and business rules. The frontend shares the original
`app/static/style.css` design tokens and theme behavior; the authenticated top
navigation is left aligned. FastAPI continues to serve Jinja pages for the
remaining operational/admin workflows. Keep the React and Jinja experiences
consistent and avoid replacing real API behavior with fabricated frontend
state.

## Current primary workflows
1. PowerShell agent posts telemetry to `/api/v1/telemetry`.
2. API validates endpoint token and timestamp, then atomically stores the
   endpoint snapshot and a transactional outbox event in PostgreSQL.
3. The outbox relay publishes events to Kafka in endpoint-key order.
4. Automation consumers evaluate active mappings using battery hysteresis and
   cooldown rules; connector commands remain durable in PostgreSQL.
5. The assigned site connector controls the switch locally and acknowledges;
   resulting events/state are exposed in the UI.
6. Users can discover LAN devices through a connector and pair them through SmartLife/Tuya QR login.
7. SmartLife linked devices can be matched to connector discovery results to fill IP and local key fields.
8. The React frontend consumes the API and keeps session cookies; browser-facing
   API/frontend origins are provided by runtime `CHARGEPILOT_API_URL` and
   `CHARGEPILOT_FRONTEND_URL` configuration. Login and registration screens are
   served by the frontend; API-host `/login` and `/register` GET requests redirect
   to the frontend. Authenticated navigation and connector, profile, account,
   user, tenant, and agent setup workflows are React routes. Super admins can
   change their own password from the React account page using the authenticated
   auth API.

## Current important service modules
- app/services/rule_engine.py — threshold logic and hysteresis
- app/services/tuya_service.py — local device control / discovery
- app/services/smartlife_service.py — QR generation and linked-device polling
- app/services/broadcaster.py — SSE updates
- app/services/connector_service.py — connector identity, command queue, lease, and result handling
- app/services/automation_processor.py — asynchronous rule evaluation and command creation
- app/workers.py — transactional-outbox relay and Kafka automation consumer processes
- connector/chargepilot_connector.py — site-side TinyTuya runtime

## Service topology and scale status

The deployment now has separate API, outbox-relay, and automation-consumer
processes, a Kafka event log, PostgreSQL transactional state, and independently
deployed site connectors. The API and workers currently share the existing
PostgreSQL schema; domain-database ownership and horizontal database sharding
are not yet implemented. Redis is not enabled because token/rule caching has
not been shown to be a measured bottleneck.

The delivery pipeline is split between `.github/workflows/ci.yml` (Python
tests/lint and frontend lint/build) and
`.github/workflows/publish-deploy.yml` (multi-platform Docker Hub publish and
ArgoCD image-tag update after successful main CI). App images use the immutable
`endusercompute/chargepilot:sha-<full-commit-sha>` format. The k3s manifests
under `deploy/k3s/` configure Istio routes for `app.endusercompute.in` and
`api.endusercompute.in`; ArgoCD bootstrapping is under `deploy/argocd/`.
The checked-in k3s PostgreSQL and Kafka services are single-replica,
single-node starting components and are not highly available.

The capacity goal is 10 million registered endpoints and 1 million active
telemetry sources. The repository includes a guarded, temporary PostgreSQL
dataset test above 10 million rows and a configurable k6 live-ingestion
scenario. These are validation tools, not evidence that this checkout has
passed a 10-million-device production load test. Production capacity requires
measurement on representative, provisioned multi-node Kafka and horizontally
sharded PostgreSQL infrastructure before setting throughput or SLO claims.

## Current known implementation risks
- bearer-token validation remains intentionally minimal
- the database bootstrap uses `create_all()` plus compatibility SQL, not
  versioned Alembic revisions; schema changes need a reviewed migration plan
- device payloads vary by Tuya firmware and hardware model
- SmartLife QR tokens may expire or respond invalidly; the system refreshes QR automatically when needed
- local keys and session data are sensitive and should never be committed to source control
- keep `CHARGEPILOT_ENCRYPTION_KEY` stable and backed up; it protects stored device local keys
- the cloud server does not scan or route to private device LANs; use a healthy connector and explicit device assignment
- Kafka delivery is at-least-once. Event processing has a processed-event
  guard; validate retries, dead-letter handling, and physical command
  idempotency in staging before increasing worker concurrency.
- endpoint and automation data still use one PostgreSQL database. The current
  schema/index set is not a demonstrated 10-million-device deployment.
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
