# ChargePilot Project Reference Pack

This directory captures the current implementation state of the ChargePilot repository so a future developer or Claude-based agent can understand the product, architecture, runtime flow, and deployment constraints without reverse-engineering the codebase.

## Included reference documents

- [CURRENT_STATE.md](CURRENT_STATE.md) — current implementation and persistent project guidance.
- [ARCHITECTURE.md](ARCHITECTURE.md) — architecture, runtime boundaries, and current module layout.
- [FRONTEND_DESIGN.md](FRONTEND_DESIGN.md) — browser routes, visual decisions, typography, theme behavior, and UI change checklist.
- [CLOUD_CONNECTOR_ARCHITECTURE.md](CLOUD_CONNECTOR_ARCHITECTURE.md) — canonical cloud-to-site control architecture and rollout design.
- [PRD.md](PRD.md) — product intent, user goals, functional requirements, and current scope.
- [TLD.md](TLD.md) — technical design for service roles, event flows, data, and scale-test boundaries.
- [API_SPEC.md](API_SPEC.md) — the current API surface and payload contracts.
- [DEPLOYMENT.md](DEPLOYMENT.md) — environment, Docker, and runtime setup notes.
- [RUNBOOK.md](RUNBOOK.md) — debugging, validation, and operational checklist.

## What this codebase does now

The project is a cloud-capable, local-first battery automation platform for Windows laptops and local Tuya devices. It includes:

- Windows laptop telemetry ingestion via a PowerShell agent
- endpoint-to-device mappings and automation rules
- connector-based Tuya discovery and state control over the LAN
- PostgreSQL transactional outbox and command delivery, Kafka telemetry events,
  and tenant-scoped connector enrollment
- a SmartLife/Tuya QR login flow for linked-device recovery and local key matching
- a wizard-based device onboarding flow using AJAX and local session state
- SSE-driven UI updates and current-state refreshes

## Current implementation facts captured from the repo

- Runtime stack: Python 3.12, FastAPI, SQLAlchemy 2.x, PostgreSQL, Kafka/aiokafka,
  TinyTuya, tuya-device-sharing-sdk, pytest.
- App entrypoint: `app/main.py` registers JSON APIs, serves public agent/connector source downloads and bootstrap scripts, and redirects legacy page paths to React routes.
- Settings prefix: `CHARGEPILOT_` via `app/core/config.py`.
- Database bootstrap: `create_db_and_tables()` runs on startup and ensures missing columns are added.
- Telemetry auth: bearer token validation is still kept simple and should be
  hardened before production exposure. Accepted events use a PostgreSQL outbox
  and Kafka before asynchronous rule processing.
- API, outbox relay, and automation consumer are separate deployment roles but
  still share the PostgreSQL schema; database sharding is not implemented.
- Scale target: 10 million registered and 1 million active telemetry sources.
  `scripts/scale_test.py` and `tests/scale_telemetry.js` are test harnesses, not
  proof of target-scale throughput.
- SmartLife flow: `app/services/smartlife_service.py` generates QR images, polls login results, saves session state, and refreshes QR on immediate expiry.
- Rule defaults: `on_threshold=79`, `off_threshold=99`, `minimum_state_change_interval=300`.
- Device discovery: the wizard can scan on the ChargePilot server network or delegate discovery to an online site connector; both paths omit local keys.
- Connector deployment: the downloadable package includes Python and Docker Compose instructions, and the standalone Docker image targets Linux amd64 and arm64.
- UI pattern: React, TypeScript, and Tailwind provide the full browser UI; FastAPI exposes JSON APIs and file downloads. Frontend design and theme decisions are documented in [FRONTEND_DESIGN.md](FRONTEND_DESIGN.md).

## File map relevant to AI understanding

```text
app/main.py                 # app bootstrap, JSON routers, React redirects, downloads
app/api/*.py               # routers for telemetry, devices, events, and mappings
app/core/*.py              # settings, DB session, auth helpers
app/models/*.py            # ORM schema
app/services/*.py          # device logic, rule processing, SmartLife flow, SSE
app/workers.py              # outbox relay and Kafka automation consumer
frontend/src/*.tsx         # React routes and UI
frontend/src/*.css         # shared responsive themes
agent/BatteryAgent.ps1     # telemetry sender
agentv2/                  # alternate agent flow or future version
docker-compose.yml         # runtime config
.github/workflows/ci.yml   # Tests, change detection, image builds and Trivy scans
.github/workflows/publish-deploy.yml # Selective Docker Hub publish, scans, GitOps update
.github/workflows/connector-multiarch.yml # Connector build, scan and multi-arch publish
deploy/k3s/                # k3s, PostgreSQL, Kafka, and Istio resources
deploy/argocd/              # ArgoCD Application bootstrap resource
scripts/scale_test.py      # temporary PostgreSQL dataset above 10M rows
tests/scale_telemetry.js   # configurable k6 live-load generator
tests/                    # validation cases
```

## Current status

The repository is a local-first product with an event-driven telemetry path,
separate API/relay/automation deployment roles, and expanded onboarding.
Compose is a development topology; production scale requires a secured
multi-node Kafka deployment and horizontally scalable PostgreSQL design
validated by staging benchmarks. The connector architecture document is the
authority for cloud-to-site connectivity.

## Claude rebuild guidance

If this project has to be rebuilt from scratch, the safe order is:

1. build the FastAPI app and core DB schema
2. add telemetry ingestion and mapping logic
3. add connector enrollment, device assignment, durable PostgreSQL commands,
   and the transactional telemetry outbox
4. run the outbox relay and Kafka automation consumer as independent services
5. add a site connector for local Tuya discovery and control
6. add battery rules and automation event logging
7. add SmartLife QR onboarding and local-key matching flow
8. add the React UI and SSE for operational visibility; follow FRONTEND_DESIGN.md for route, typography, and theme decisions

This order preserves the system's practical local-first architecture and minimizes unnecessary churn.
