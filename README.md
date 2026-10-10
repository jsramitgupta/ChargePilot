# ChargePilot

ChargePilot is a cloud-capable, local-first battery automation platform for Windows laptops. The app receives telemetry from laptop agents, evaluates battery thresholds, and routes Tuya switch commands through a site connector on the device LAN. Day-to-day control does not rely on the Tuya cloud.

## Project summary

The current codebase is a modular monolith built with FastAPI and SQLAlchemy. It contains:

- a battery telemetry ingestion API
- device, endpoint, mapping, and event models
- a hysteresis-based battery rule engine
- TinyTuya wrappers for local switch discovery and control
- Jinja-rendered dashboard pages for operational supervision
- a PowerShell laptop agent that sends runtime battery data
- an outbound-HTTPS site connector that scans and controls devices on private LANs

## Runtime stack

- Python 3.12+
- FastAPI 0.115.0
- SQLAlchemy 2.0.32
- PostgreSQL / psycopg
- Pydantic + pydantic-settings
- TinyTuya 1.20.0
- tuya-device-sharing-sdk for Smart Life QR pairing
- qrcode for Smart Life sign-in QR images
- tzdata for timezone handling in containerized deployments
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

The request is authenticated with the tenant's agent token in the `Authorization` bearer header. Sign in to ChargePilot and open **Install Agent** in the top navigation to download the Windows scripts and get the PowerShell installation command for the current token. Tenant admins can regenerate the tenant token there; existing agents must be reconfigured after rotation. Super Admins can update or regenerate the installation-wide global agent token from the same page. A random global token is created during fresh database initialization and is stored in the database for tenantless Super Admin installations.

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

Open **Connectors**, download the connector package, and create an enrollment
code for the tenant. The ZIP includes a README, Python runtime, and Docker
deployment files.

### Docker on Linux (amd64 or arm64)

On an always-on Linux host on the switch LAN, copy `.env.example` to `.env` in
the extracted package directory. Set the image to
`DOCKERHUB_USERNAME/chargepilot-connector@sha256:<digest-from-workflow-summary>`,
your HTTPS ChargePilot URL, and the enrollment-code file path. Create that
file with the one-time code shown in ChargePilot, then create and grant
ownership of the persistent data directory to container UID 10001:

```sh
mkdir -p connector-data
sudo chown 10001:10001 connector-data
docker compose up -d
docker compose logs -f chargepilot-connector
```

The published multi-platform image supports both `linux/amd64` and
`linux/arm64`. The included Compose service uses host networking so TinyTuya
LAN discovery works on Linux. Protect the enrollment-code file and persistent
connector data directory.

### Python runtime

For Windows, Linux, or macOS, install dependencies in the extracted package:

```powershell
python -m pip install -r requirements.txt
```

Then run:

```powershell
python -m connector.chargepilot_connector --server-url "https://YOUR-CHARGEPILOT-HOST"
```

The connector prompts securely for the one-time code and saves its
connector-specific credential outside the repository. Reuse the same host
account to run it after enrollment.

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

The Compose stack starts PostgreSQL 16 with persistent storage, waits for database health before starting the app, and runs the app as a non-root user. `/health` reports process liveness; `/ready` checks database connectivity. `docker compose down` preserves database data; `docker compose down -v` deletes it.

To publish an image to Docker Hub or install/update ChargePilot from a published image, see the [Docker Hub deployment guide](DOCKER_HUB_DEPLOYMENT.md).

For local Python development, install with `python -m pip install -e .[dev]`, set `CHARGEPILOT_DATABASE_URL` to a reachable existing PostgreSQL database, and run `uvicorn app.main:app --reload`. The app creates tables and the initial admin account at startup on an empty database.

The app's startup schema compatibility path creates the connector tables and
adds the device connector assignment column to older databases. Back up the
database before upgrading. The repository currently has no versioned Alembic
revisions; `create_all()` and the compatibility bootstrap are not a general
schema migration system. Plan and apply a reviewed, versioned migration before
future production schema changes.

## Operational observations from the codebase

- The app treats endpoint telemetry as the source of truth for device state and mapping decisions.
- Device commands target an explicit desired state and channel; they are
  durable and routed only to the assigned site connector.
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
- telemetry auth uses generated bearer tokens for new installations; rotate the legacy `test-endpoint-token` after upgrading an older database
- device actions depend on the actual switch payload format
- the rule engine uses hysteresis and a cooldown window to avoid chatter
- all automation outcomes are persisted in the database as events

The technical docs in [.github/instructions](.github/instructions) are meant to serve as the implementation reference for future rebuilds and deeper automated analysis.
