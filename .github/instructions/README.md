# ChargePilot Project Reference Pack

This directory is the project reference pack. It records implemented behavior
and approved design constraints; future work is labeled so it is not mistaken
for an existing API or runtime feature.

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
- [platform-agents/README.md](platform-agents/README.md) — cross-platform
  telemetry status and remaining native client streams.
- [platform-agents/SERVER_SIDE_CONFIG.md](platform-agents/SERVER_SIDE_CONFIG.md)
  — implemented enrollment/telemetry contract and remaining rollout work.

## What this codebase does now

The implemented product is a cloud-capable, local-first battery automation
platform. Windows PowerShell and macOS agents are device-validated; Android
and iOS source projects are implemented. The artifact workflow builds a
self-contained .NET Windows service executable with setup UI/CLI, Android
APK, iOS IPA, and macOS DMG. An `agents-v*` tag publishes the builds to a
GitHub Release; each platform is signed when its complete signing-secret group
is configured, and is identified as unsigned otherwise. The Windows
service executable build and runtime validation are pending.
Android has an emulator smoke test; iOS has a simulator smoke test. Physical-device
validation and signed distribution remain pending. The current product
includes:

- Battery telemetry from Windows, macOS, Android, and iOS endpoint agents
- enrolled macOS battery telemetry via a SwiftUI menu-bar app and CLI, with
  per-install credentials, explicit user labels, and an optional login item
- Android Kotlin/Compose and iOS SwiftUI telemetry apps with secure per-install
  credential storage; development builds are published, while signed store
  releases and physical-device validation remain outstanding
- platform-aware telemetry, endpoint enrollment, credential revocation, and
  server-enforced all-platform automation defaults with freshness gates
- endpoint-to-device mappings and automation rules
- connector-based Tuya discovery and state control over the LAN
- PostgreSQL transactional outbox and command delivery, Kafka telemetry events,
  and tenant-scoped connector enrollment
- a SmartLife/Tuya QR login flow for linked-device recovery and local key matching
- a wizard-based device onboarding flow using AJAX and local session state
- SSE-driven UI updates and current-state refreshes

## Reading guidance

Start with [CURRENT_STATE.md](CURRENT_STATE.md), then read only the relevant
reference for the files being changed. Use [API_SPEC.md](API_SPEC.md) for the
live HTTP contract and [CLOUD_CONNECTOR_ARCHITECTURE.md](CLOUD_CONNECTOR_ARCHITECTURE.md)
for the authoritative cloud-to-LAN control boundary. Platform-agent documents
are proposals and must not be treated as permission to change the current
contract without a separately reviewed backend change.

## Current implementation facts captured from the repo

- Runtime stack: Python 3.15 production image (Python 3.12+ supported for local
  development), FastAPI, SQLAlchemy 2.x, PostgreSQL, Kafka/aiokafka,
  TinyTuya, tuya-device-sharing-sdk, pytest.
- App entrypoint: `app/main.py` registers JSON APIs, serves public connector downloads and redirects agent downloads to GitHub Release assets, and redirects legacy page paths to React routes.
- Settings prefix: `CHARGEPILOT_` via `app/core/config.py`.
- Database bootstrap: `create_db_and_tables()` runs on startup and ensures missing columns are added.
- Telemetry auth: the current bearer token remains available for backward-compatible Windows telemetry; enrolled
platforms use tenant-bound, hash-only per-install credentials. Accepted
events use a PostgreSQL outbox and Kafka before asynchronous rule processing.
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
app/main.py                  # API bootstrap, router registration, downloads, SPA routing
app/api/                     # JSON API routers
app/core/                    # settings, database, authorization, and security
app/models/                  # SQLAlchemy persistence models
app/schemas/                 # Pydantic request/response schemas
app/services/                # automation, connector, Tuya, SmartLife, and support logic
app/workers.py               # telemetry outbox relay and Kafka automation consumer
connector/                   # site-LAN connector runtime and packaging
agent/                       # Windows, macOS, Android, and iOS telemetry agents
frontend/src/App.tsx         # React routes and page composition
frontend/src/main.tsx        # frontend bootstrap
frontend/src/index.css       # shared/light theme and layout styles
frontend/src/theme.css       # dark theme overrides
tests/                       # Python unit and API tests
deploy/k3s/                  # Kubernetes, PostgreSQL, Kafka, and Istio resources
deploy/argocd/               # ArgoCD application
.github/workflows/           # CI, image publishing/scanning, and GitOps updates
scripts/                     # scale and operational scripts
tests/scale_telemetry.js     # configurable k6 live-ingestion scenario
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
9. Android and iOS reporters use the shipped platform-aware backend contract.
   Android has a development APK and emulator smoke test; iOS has a device IPA
   and simulator smoke test. Physical-device validation and signed distribution
   remain follow-up work. Tagged releases can publish unsigned or per-platform
   signed artifacts depending on configured secrets.

This order preserves the local-first architecture and distinguishes source
availability from validated, distributable mobile apps.
