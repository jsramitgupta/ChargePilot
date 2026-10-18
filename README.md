# ChargePilot

ChargePilot is a cloud-capable, local-first battery automation platform for Windows laptops. The app receives telemetry from laptop agents, evaluates battery thresholds, and routes Tuya switch commands through a site connector on the device LAN. Day-to-day control does not rely on the Tuya cloud.

## Project summary

The cloud control plane has independently deployable API, outbox-relay, and
automation-consumer processes. It uses a PostgreSQL transactional outbox and
Kafka for telemetry events; site connectors continue polling durable commands
from the API. The API and workers currently share the existing PostgreSQL
schema, so this is not yet a horizontally sharded 10-million-endpoint system.
The product contains:

- a battery telemetry ingestion API
- device, endpoint, mapping, and event models
- a hysteresis-based battery rule engine
- TinyTuya wrappers for local switch discovery and control
- React, TypeScript, Tailwind, and Vite frontend in `frontend/`, serving the
  complete browser experience through JSON APIs
- a PowerShell laptop agent that sends runtime battery data
- an outbound-HTTPS site connector that scans and controls devices on private LANs

## Runtime stack

- Python 3.12+
- FastAPI 0.134.0
- SQLAlchemy 2.0.32
- PostgreSQL / psycopg
- Apache Kafka / aiokafka for asynchronous telemetry processing
- Pydantic + pydantic-settings
- TinyTuya 1.20.0
- tuya-device-sharing-sdk for Smart Life QR pairing
- qrcode for Smart Life sign-in QR images
- tzdata for timezone handling in containerized deployments
- pytest for automated checks

## Repository layout

```text
.
├── app/
│   ├── api/                 # REST routers for health, telemetry, devices, mappings, events
│   ├── core/                # settings, DB session, startup bootstrap, security helpers
│   ├── models/              # SQLAlchemy ORM models
│   ├── schemas/             # Pydantic request/response contracts
│   ├── services/            # battery rules, event processor, Tuya abstraction
│   ├── workers.py           # Kafka outbox relay and automation consumer roles
│   └── main.py              # FastAPI app setup, redirects, and downloads
├── frontend/                # React application and design system
├── agent/
│   ├── BatteryAgent.ps1               # Windows laptop telemetry sender
│   └── CreateAgentScheduledTask.ps1   # creates the recurring Windows task
├── connector/               # site-side Tuya discovery and control runtime
├── deploy/k3s/               # Kubernetes workloads and service configuration
├── docker/                   # API image and entrypoint
├── scripts/scale_test.py    # temporary PostgreSQL dataset above 10M rows
├── tests/scale_telemetry.js # configurable k6 ingestion load
├── tests/
│   ├── api/
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

The request is authenticated with the tenant's agent token in the `Authorization` bearer header. The API commits the latest endpoint snapshot and a transactional outbox event together. A relay publishes the event to Kafka; automation consumers then evaluate mappings asynchronously. An HTTP accepted response confirms durable ingestion, not completed switch control. Monitor outbox age, consumer lag, dead-letter events, and connector command outcomes. Sign in to ChargePilot and open **Install Agent** in the top navigation to copy the one-line PowerShell installer for the current token; the page also links to a public source ZIP. The command uses `iex` to download scripts from your configured HTTPS ChargePilot server, so run it only when you trust that server. Tenant admins can regenerate the tenant token there; existing agents must be reconfigured after rotation. Super Admins can update or regenerate the installation-wide global agent token from the same page. A random global token is created during fresh database initialization and is stored in the database for tenantless Super Admin installations.

Extract `chargepilot-agent-scripts.zip`, open PowerShell in that folder, and run the displayed command. The installer saves the token in the local agent configuration and registers the recurring scheduled task. The ZIP download requires an authenticated ChargePilot session and does not contain the tenant token.

### Tenant isolation and administrator assignment

Each tenant account belongs to exactly one tenant. Super Admins can create a user
or reassign an existing account to a tenant from **Users**; assigning the
`Tenant Admin` role grants that account tenant user-management permissions.
Changing an account's tenant changes its access scope but does not move devices,
endpoints, mappings, or history between tenants.

Devices, endpoints, mappings, and automation events carry a `tenant_id`.
Authenticated application pages and JSON APIs scope tenant users to rows with
their exact tenant ID; unassigned rows are visible only to Super Admins.
Mappings are accepted only when the endpoint, device, and optional channel all
belong to the same tenant. Tenant agent tokens likewise create/update endpoints
only within the token's tenant. The global agent token remains a
Super-Admin-only legacy integration and should not be shared with tenant users.

### Automation rule

Battery decisions are evaluated in `app/services/rule_engine.py` and apply hysteresis with a minimum interval:

- default `on_threshold = 79`
- default `off_threshold = 99`
- default `minimum_state_change_interval = 300` seconds

The app prevents rapid toggling and only fires if the battery crosses threshold values with enough time since the last state change.

### Automation event history

The Events page is paginated on the server and lets you display 50, 100, or
500 event rows per page. Events older than 30 days are automatically purged at
application startup and once every 24 hours while the application is running.

### Switch control through site connectors

`app/services/tuya_service.py` encapsulates TinyTuya interactions. For cloud
deployments, TinyTuya runs from `connector/chargepilot_connector.py` on the
switch LAN instead of the cloud app:

- LAN discovery via `deviceScan()` on the selected site connector
- explicit desired-state on/off and channel operations
- request normalization for nested `dps` payloads
- durable PostgreSQL command records with leases, expiry, bounded retries, and acknowledgements
- encrypted local keys at rest using the existing `CHARGEPILOT_ENCRYPTION_KEY`

See the canonical [Cloud Connector Architecture](.github/instructions/CLOUD_CONNECTOR_ARCHITECTURE.md)
for message semantics, security boundaries, rollout, and failure behavior.

### Switch onboarding

The Switches page offers LAN-scan, manual-add, and connector assignment paths.
LAN discovery defaults to scanning the network available to the ChargePilot
server process. This works when the app host can reach the switch LAN. To scan a
different, remote site, choose an online site connector; it scans its own LAN.
Both paths return device IDs, names, IP addresses, and protocol versions, never
local keys. Assign remotely controlled switches to the connector on their
physical LAN.

The local key field stays blank until entered manually or retrieved through
Smart Life QR pairing. Smart Life returns only the local key and device ID
needed to match that key; it does not populate device details. Select the
matching TinyTuya LAN scan result to fill the device name, ID, IP address, and
protocol version. The wizard can optionally remember the Smart Life user ID on
the signed-in ChargePilot account; the account password, QR session, and local
keys are never saved as that preference. Pairing follows the device-sharing flow used by
[tuya-local-key](https://github.com/vineetchoudhary/tuya-local-key): it uses the
Smart Life user code and requires the user to approve the QR sign-in in the
mobile app; ChargePilot never asks for the account password. Linked-device keys
are held temporarily in server memory and returned only to the authenticated
account that started pairing. They are not written to a Smart Life session
file. The Smart Life account is used only for key retrieval; device details,
including the local IP address, come from the LAN scan (or manual entry).

## Site connector

Create a one-time enrollment code in **Connectors** for the tenant. The
published Docker image and Python installer use the k3s API URL by default:
`https://api-chargepilot.endusercompute.in`.

### Docker Compose on Linux

Save this `docker-compose.yml`. Compose creates a persistent Docker-managed
volume for the connector credential; no host data directory is needed.

```yaml
services:
  chargepilot-connector:
    image: endusercompute/chargepilot-connector:sha-922f4aac9cef35276eef7814620f38d674720f73
    container_name: chargepilot-connector
    network_mode: host
    restart: unless-stopped
    read_only: true
    tmpfs:
      - /tmp:rw,noexec,nosuid,size=16m
    cap_drop:
      - ALL
    security_opt:
      - no-new-privileges:true
    environment:
      CHARGEPILOT_CONNECTOR_SERVER_URL: https://api-chargepilot.endusercompute.in
      CHARGEPILOT_CONNECTOR_ENROLLMENT_CODE: ${CHARGEPILOT_CONNECTOR_ENROLLMENT_CODE:-}
      CHARGEPILOT_CONNECTOR_CONFIG: /data/connector-config.json
    volumes:
      - connector-data:/data

volumes:
  connector-data:
```

Start it on an always-on Linux host on the switch LAN, passing the one-time
enrollment code for first enrollment:

```sh
read -rsp 'One-time ChargePilot code: ' CHARGEPILOT_CONNECTOR_ENROLLMENT_CODE && echo && export CHARGEPILOT_CONNECTOR_ENROLLMENT_CODE && docker compose up -d && unset CHARGEPILOT_CONNECTOR_ENROLLMENT_CODE
```

### Python on Linux or macOS

Install Python 3.12+, `curl`, and `unzip`. Run this on the switch LAN and enter
the one-time code when prompted:

```sh
curl -fsSL https://api-chargepilot.endusercompute.in/connectors/install.sh | sh
```

The installer creates a private virtual environment and stores its permanent
credential under `~/.local/share/chargepilot/site-connector/`. Keep the
process running or configure your OS service manager to start it at boot. The
command runs an installer served by ChargePilot; use it only if you trust
that HTTPS server.

The public source archive for manual installation is available at
`https://api-chargepilot.endusercompute.in/connectors/download`. Downloads
contain no enrollment or connector credentials. On Windows, extract the
archive and run:

```powershell
python -m pip install -r requirements.txt
python -m connector.chargepilot_connector --server-url "https://api-chargepilot.endusercompute.in"
```

Enter the one-time code when prompted.

Assign switches to that connector on the **Switches** page. Confirm that the
connector reports online, then use LAN scan or switch controls. The connector
requires outbound HTTPS to ChargePilot and TinyTuya local LAN access. No inbound
site firewall rule is needed. The connector image is rebuilt and pushed to
Docker Hub when files under `connector/` change on `main`; the build publishes
both supported CPU architectures.

The existing Windows laptop agent, its config JSON, telemetry contract,
`CHARGEPILOT_` settings, and Compose variables are unchanged. The connector is
a separate process with its own configuration.

## Environment configuration

The application reads settings using `pydantic-settings` with the environment prefix `CHARGEPILOT_`. For Compose, copy `.env.example` to `.env`, then set unique secret, admin-password, and PostgreSQL-password values. Generate URL-safe values with `python -c "import secrets; print(secrets.token_urlsafe(32))"`. The `.env` file is ignored by Git. `CHARGEPILOT_ENCRYPTION_KEY` encrypts device
local keys at rest. Keep it backed up and stable: losing or changing it makes
previously stored keys unreadable.

## Quick start: fresh PostgreSQL deployment

```bash
docker compose config
docker compose up --build -d
```

The Compose stack starts PostgreSQL 16, a single-node Kafka broker, the API,
outbox relay, and automation consumer. Both stateful services use persistent
volumes; only app ports `8000` and `5173` are published. `/health` reports
process liveness; `/ready` checks database connectivity. `docker compose down`
preserves data; `docker compose down -v` deletes database and broker volumes.
This single-host Compose topology is for development/smoke tests, not the
10M-device production deployment.

The `ChargePilot CI` workflow runs backend tests/lint and frontend lint/build,
then builds and scans only affected component images. Successful main CI
publishes changed API/frontend images for both supported architectures after
Trivy vulnerability and secret scans, then selectively updates the
ArgoCD-deployed k3s manifest tags. The connector image has its own
change-filtered multi-platform publishing and scanning workflow. The UI hostname is
`console-chargepilot.endusercompute.in`; API and telemetry use
`api-chargepilot.endusercompute.in`. See the
[Docker Hub and k3s deployment guide](DOCKER_HUB_DEPLOYMENT.md) for required
GitHub/Docker Hub setup, Cloudflare TLS, ArgoCD bootstrap, and single-node
storage limitations.

To publish an image to Docker Hub or install/update ChargePilot from a published image, see the [Docker Hub deployment guide](DOCKER_HUB_DEPLOYMENT.md).

For local Python development, install with `python -m pip install -e .[dev]`, set `CHARGEPILOT_DATABASE_URL` to a reachable existing PostgreSQL database, and run `uvicorn app.main:app --reload`. The app creates tables and the initial admin account at startup on an empty database.

For the React development frontend, start the backend on `http://localhost:8000`,
then run `npm --prefix frontend install` and `npm --prefix frontend run dev`.
Vite serves the frontend on `http://localhost:5173` and proxies application
requests to FastAPI. Set `CHARGEPILOT_BACKEND_URL` to change the development
proxy target.

The API image serves FastAPI on port `8000`; a separate frontend image serves
the React application on port `5173`. Compose runs the outbox relay and
automation worker from the API image. `CHARGEPILOT_API_URL` and
`CHARGEPILOT_FRONTEND_URL` are read by the frontend container at startup and
injected into its runtime configuration; changing them does not require
rebuilding the image. Only the public Turnstile site key is exposed to the
frontend; the private key remains in the API environment.
Use browser-accessible public URLs, not Docker service names. For example:

```dotenv
CHARGEPILOT_API_URL=https://api.chargepilot.example.com
CHARGEPILOT_FRONTEND_URL=https://chargepilot.example.com
CHARGEPILOT_SESSION_COOKIE_SECURE=true
CHARGEPILOT_SESSION_COOKIE_SAMESITE=lax
```

Configure the reverse proxy to send the frontend hostname to container port
`5173` and the API hostname to port `8000`. The API hostname must proxy the
JSON API, authenticated downloads, and public agent/connector source downloads.
The backend permits credentialed
browser requests only from the configured frontend origin. For frontend and API
hostnames on different registrable domains, set
`CHARGEPILOT_SESSION_COOKIE_SAMESITE=none`; secure cookies are required for
that mode. TLS should terminate at the reverse proxy, with
`CHARGEPILOT_SESSION_COOKIE_SECURE=true`.

For local development over plain HTTP, set
`CHARGEPILOT_SESSION_COOKIE_SECURE=false` in `.env`. Do not use that setting for
a public HTTPS deployment. Run `npm --prefix frontend run build` to type-check
and build the frontend independently. No server secrets belong in frontend
configuration.

The app's current schema bootstrap creates tables and runs compatibility SQL;
it is not a substitute for reviewed, versioned production migrations. New
outbox and per-endpoint automation-cursor tables are part of the current
schema.

The requested capacity target is 10 million registered endpoints and 1 million
active telemetry agents. `scripts/scale_test.py` builds and queries a temporary
10,000,001-row dataset in a dedicated PostgreSQL database ending in
`_scale_test`; `tests/scale_telemetry.js` drives configurable live HTTP traffic
with k6. These are test tools, not evidence of target-scale performance. The
current app/worker schema is not horizontally sharded, and no 1M-active
staging benchmark has been run. See the [deployment guide](.github/instructions/DEPLOYMENT.md)
and [architecture](.github/instructions/ARCHITECTURE.md) for the scale gate
and k3s GitOps manifests.

## Operational observations from the codebase

- The app treats endpoint telemetry as the source of truth for device state and mapping decisions.
- Device commands target an explicit desired state and channel; they are
  durable and routed only to the assigned site connector.
- A device can expose its state under `dps`, `data.dps`, or `status` payloads.
- React is the only browser UI. Login and signup use JSON session APIs;
  tenant signup creates a tenant and its first admin. Managed-role invitations
  are sent by email with a single-use password setup link; legacy
  code-based standard-user signup remains supported for existing invitations.
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

ChargePilot remains local-first at the device edge while the cloud control
plane uses asynchronous services. The most important design constraints are:

- local network access is required for Tuya control
- telemetry auth uses generated bearer tokens for new installations; rotate the legacy `test-endpoint-token` after upgrading an older database
- device actions depend on the actual switch payload format
- the rule engine uses hysteresis and a cooldown window to avoid chatter
- all automation outcomes are persisted in the database as events
- telemetry HTTP acceptance is asynchronous; inspect the outbox, Kafka lag,
  dead-letter topic, and connector result before treating an action as done
- production capacity remains unproven until the documented 10M-row and
  provisioned live-load tests have been run and reviewed

The technical docs in [.github/instructions](.github/instructions) are meant to serve as the implementation reference for future rebuilds and deeper automated analysis.
