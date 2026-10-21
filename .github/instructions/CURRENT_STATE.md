# Current State Summary

This file is the short operational summary for the repository as it stands today.

## Product
ChargePilot is a cloud-capable, local-first battery automation platform. The
backend supports enrolled Windows, macOS, Android, and iOS telemetry. Android
Kotlin/Compose and iOS SwiftUI source projects are implemented. The GitHub
release publishes an Android debug APK, an unsigned iOS IPA, and an unsigned,
unnotarized macOS DMG. Android has an emulator smoke test; iOS has a simulator
smoke test. Physical-device validation and signed distribution remain
outstanding. New installs use a tenant-scoped, reusable 24-hour enrollment
token to obtain a revocable per-install credential; existing Windows agents
remain compatible with tenant-wide tokens during migration.
The backend monitors endpoint battery state and controls local Tuya switches
through an outbound-HTTPS site connector on each device LAN.

## Deployment validation host
For user-authorized Linux, Docker, or k3s validation, the deployed server is
`rootuser@192.168.1.21`. Connect using the existing SSH key/configuration; do
not store passwords, private keys, or other credentials in this repository.
See `.github/instructions/DEPLOYMENT.md` for safe remote validation scope.

## Core runtime stack
- FastAPI
- SQLAlchemy
- PostgreSQL for transactional state and outbox
- Apache Kafka for durable telemetry event transport
- React, TypeScript, Tailwind CSS, and Vite for the interactive frontend
- TinyTuya
- HTTPS-polling site connector with PostgreSQL-backed durable commands
- tuya-device-sharing-sdk
- qrcode
- pytest

## Frontend and rendering
The frontend is a Vite-built React application in `frontend/`. It currently
provides sign-in/registration, dashboard, switches, mappings, endpoints,
events, connector administration, profile, user/tenant administration, agent
setup, and super-admin account pages. Authenticated in-app navigation stays
within React Router, with the dev server serving the SPA for direct page loads.
FastAPI serves JSON APIs and downloads; agent-source download endpoints redirect
to assets on the latest stable `agents-v*` GitHub Release, while connector
source and its bootstrap script remain public API downloads. Setup APIs and
credential management remain authenticated. The built React app is the only browser UI.
Legacy page GETs redirect to the matching React route.
React admin pages use authenticated, tenant-scoped API data and preserve
server-side authorization and business rules. The UI has responsive
left-rail navigation and light/dark theme parity.
The canonical route inventory, typography scale, color tokens, theme behavior,
responsive decisions, and UI change checklist are in
`.github/instructions/FRONTEND_DESIGN.md`; update that reference with UI
behavior changes so future agents can follow the established design.
The Overview refreshes fleet data every 30 seconds while the page is visible,
shows endpoint and switch counts in a responsive summary grid, and lists the
ten most recently seen endpoints first. The Endpoints page refreshes on the
same cadence, supports search and 50- or 100-endpoint pages, and sorts by last
report with missing timestamps last. Both views expose the last successful
refresh and a manual refresh action. The Smart switches page groups LAN
discovery, manual setup, and the searchable/filterable inventory into clear
work areas; card and list views remain available on small screens.
Switch onboarding separates device identity, local access, and command routing.
The route picker limits tenant users to enrolled connectors for their tenant;
Super Admins can choose an enrolled connector across tenants and the new device
is assigned to that connector's tenant. Scanning through a connector selects
that route by default. Discovery results and Smart Life key retrieval follow
the shared light/dark theme tokens.
The mapping wizard has no form submission side effect: Continue only advances
the setup, and creating or editing a mapping requires its explicit save button.
Step 3 reviews the selected device and switch alongside editable battery rules.
Mappings can disable automatic turn-on independently and can enable a separate
charging-completion shutoff threshold. The charging cutoff uses telemetry's
`charging` flag, not `ac_connected`, and does not replace the ordinary turn-off
threshold. Existing mappings can be edited or deleted; clearing a channel
during an edit restores whole-switch control. Table text, emphasized cells,
and status badges retain readable contrast in dark mode.
The Site Connectors page presents a prebuilt Docker Compose deployment for
Linux hosts and a one-line Python installer for Linux/macOS. Docker Compose
accepts the one-time enrollment code through
`CHARGEPILOT_CONNECTOR_ENROLLMENT_CODE` and persists the connector credential
in a Docker-managed volume without host-directory setup. The Python installer
prompts for the code and saves its credential locally. The source archive
remains public for manual installation.
The iOS source project exposes a Shortcuts action for fresh battery reports.
Users can attach it to battery-level and charger-connected personal
automations; iOS may defer or skip those actions, so this does not guarantee
an exact threshold response. The Shortcuts action stores its endpoint
credential in device-only Keychain available after first unlock.
The Set up a device page creates a platform-independent enrollment token,
shows its raw value once, and lists expiry, revocation, and usage metadata.
Tokens can enroll multiple endpoints for 24 hours and admins can revoke them
to prevent further exchanges. Windows stores its endpoint credential with
Windows user-scoped DPAPI; macOS and iOS use Keychain; Android encrypts the
credential with an Android Keystore key. GitHub Releases publish an Android
debug-signed APK, an unsigned iOS IPA,
and an unsigned, unnotarized macOS DMG; none is a store-signed release.
Physical-device validation for Android and iOS remains outstanding. Mobile
reports are best-effort. New endpoints begin with automation disabled; admins
can opt in only after a fresh sample and when the platform is in the server
automation allow-list.
The macOS SwiftUI menu-bar app configures enrollment and reports every five
minutes while running. Users can pause reporting or opt in to opening the app
at sign-in; it is not a system daemon and does not report during sleep.

## Current primary workflows
1. New Windows and macOS agents exchange a tenant-scoped, reusable 24-hour
   enrollment token for a backend endpoint ID and per-install credential.
   Windows protects the credential with user-scoped DPAPI; macOS uses Keychain.
   Existing Windows agents continue using the legacy shared-token protocol
   until reinstalled with a new enrollment token.
2. API validates the legacy Windows token or resolves the per-install
   credential to its endpoint and tenant. It validates timestamp age/future
   skew, prevents delayed samples from regressing the current snapshot, and
   atomically stores the snapshot plus a
   transactional outbox event in PostgreSQL. Existing UUID-less endpoints are
   retained and linked to a UUID on matching tenant-scoped telemetry.
   Legacy global-token telemetry registers unassigned endpoints only. A Super
   Admin can assign an unassigned endpoint to a tenant; existing legacy agents
   must then use that tenant's token. Newly enrolled devices remain
   tenant-bound to the enrollment token's workspace.
3. The outbox relay publishes events to Kafka in endpoint-key order.
4. Automation consumers evaluate active mappings using battery hysteresis and
   cooldown rules only when the endpoint is opted in, its platform is
   allow-listed, and the sample is no older than the configured automation
   freshness limit. New enrolled endpoints default to telemetry-only.
   Mappings can disable turn-on independently and can enable a separate
   charging-only cutoff; connector commands remain durable in PostgreSQL.
5. The assigned site connector controls the switch locally and acknowledges;
   resulting events/state are exposed in the UI.
   Endpoint and switch ownership must match before a mapping can be created.
   The dashboard, endpoint list, switch list, and mapping workflow show tenant
   ownership; the Super Admin can assign unassigned endpoints from Endpoints.
6. Users can discover LAN devices through a connector and pair them through SmartLife/Tuya QR login.
7. SmartLife linked devices can be matched to connector discovery results to fill IP and local key fields.
8. The React frontend consumes the API and keeps session cookies; browser-facing
   API/frontend origins are provided by runtime `CHARGEPILOT_API_URL` and
   `CHARGEPILOT_FRONTEND_URL` configuration. JSON login and registration APIs
   establish the browser session. Existing standard-user self-registration
   accepts a tenant-admin/manager-issued legacy one-time code; new managed-role
   invitations are sent by email with a single-use password setup link. Both
   public signup paths additionally require server-verified
   Cloudflare Turnstile before an account or tenant can be created. Production
   registration fails closed when Turnstile keys are missing. Tenant signup
   also requires configured SMTP and a public frontend origin; newly
   registered users must verify their unique email link before login. Existing
   users and admin-created accounts remain verified. Tenant signup creates
   the tenant and its first admin. Authenticated
   navigation and connector, profile, account, user, tenant, and agent setup
   workflows are React routes. Signed-in users can contact the configured
   support inbox from the React navigation using SMTP. Signed-in users can change
   their own password from the Account page using the authenticated auth API.
   Account settings select the user's display time zone from a region-grouped
   IANA time-zone dropdown; timestamps throughout the app follow that choice.
   People & Invites sends role- and tenant-scoped invitations by email with a
   single-use, seven-day setup code. The recipient sets a password before the
   account is created and is signed in after redemption. Invitation codes are
   stored hashed, expire, can be revoked, and are never returned by the admin API.
   Signed-in users change their own password alongside profile preferences; the
   legacy `/account` route redirects to `/profile`.

## Current important service modules
- app/services/rule_engine.py — threshold logic and hysteresis
- app/services/tuya_service.py — local device control / discovery
- connector/chargepilot_connector.py — site-side TinyTuya runtime; generic
  switch, plug, and outlet labels are normalized to the default OutletDevice
  profile, matching the app's direct-control path. TinyTuya `status()` reads
  all DPS values without a channel argument; the connector selects the
  requested channel from that response.
- app/services/smartlife_service.py — QR generation and linked-device polling
- app/services/broadcaster.py — SSE updates
- app/services/connector_service.py — connector identity, command queue, lease, and result handling
- app/services/automation_processor.py — asynchronous rule evaluation and command creation
- app/workers.py — transactional-outbox relay and Kafka automation consumer processes

## Service topology and scale status

The deployment now has separate API, outbox-relay, and automation-consumer
processes, a Kafka event log, PostgreSQL transactional state, and independently
deployed site connectors. The API and workers currently share the existing
PostgreSQL schema; domain-database ownership and horizontal database sharding
are not yet implemented. Redis is not enabled because token/rule caching has
not been shown to be a measured bottleneck.

The delivery pipeline is split between `.github/workflows/ci.yml` (Python
tests/lint, frontend lint/build, component change detection, and affected
container build/scan jobs), `.github/workflows/publish-deploy.yml` (latest-main
API/frontend change detection, multi-platform Docker Hub publication, image
security scans, and selective ArgoCD tag updates), and
`.github/workflows/connector-multiarch.yml` (connector image build, scan, and
multi-platform publication). Trivy checks created images for OS/library
vulnerabilities and secrets; published AMD64 and ARM64 images are scanned by
digest before deployment tags advance. API and frontend images use separate repositories and immutable
`endusercompute/chargepilot-api:sha-<full-commit-sha>` and
`endusercompute/chargepilot-frontend:sha-<full-commit-sha>` tags. The k3s
manifests under `deploy/k3s/` configure Istio routes for
`console-chargepilot.endusercompute.in` and `api-chargepilot.endusercompute.in`;
runtime frontend and API origins use HTTPS on those hosts. ArgoCD bootstrapping
is under `deploy/argocd/`.
The Connectors page uses the immutable published image by default and also
offers a one-line Python installer.
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
- configure Cloudflare edge rate limits for public auth paths in addition to
  Turnstile; the app validates challenge tokens and browser origins but does
  not maintain a distributed login-rate counter
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

## Remaining platform-agent validation

Android and iOS source projects are implemented and available from device
setup. Android has a debug APK build and emulator smoke test; iOS has an
unsigned device IPA build and simulator smoke test. Physical-device validation
and signed distribution remain follow-up work. Their platform values are
accepted by the shared enrollment and telemetry APIs by default. Read
[platform-agents/README.md](platform-agents/README.md) and
[platform-agents/SERVER_SIDE_CONFIG.md](platform-agents/SERVER_SIDE_CONFIG.md)
for the implemented API contract, rollout controls, and client-specific
constraints. Mobile reports remain subject to endpoint opt-in and server-side
freshness gates; do not claim reliable background reporting.

The current schema keeps the legacy Windows payload compatible while allowing
optional IP/AC metadata, platform and device-class metadata, and an
installation UUID. New clients must use the reusable tenant-scoped enrollment
token and per-install credentials, not the shared Windows token. Enrollment
and telemetry accept all four platforms by default. Android has been
smoke-tested on an emulator; Android and iOS have not been physically
validated, and the iOS IPA is unsigned. Automation remains separately
allow-listed.

## Persistent implementation guidance
- Always post a concise completion update by default, reporting the work done,
  actual validation results, and whether it was committed, pushed, or deployed.
- Preserve ChargePilot product terminology and business rules. Keep React as
  the only browser UI; add JSON API operations before changing user-facing
  workflows. Keep pages responsive and aligned in both light and dark themes.
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
