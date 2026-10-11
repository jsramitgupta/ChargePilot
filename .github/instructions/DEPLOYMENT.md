# Deployment Guide

## 1. Deployment model

The cloud control plane runs ChargePilot and PostgreSQL as Compose services.
PostgreSQL data is persisted in a named volume; the app waits for the database
health check before starting. Deploy one ChargePilot site connector on an
always-on host at each physical LAN containing Tuya devices.

The connector initiates outbound HTTPS connections to ChargePilot and performs
TinyTuya discovery/control locally. Do not expose a site listener or route the
cloud app directly into the device LAN.

## 2. Prerequisites

- Python 3.12+ for local installs
- Docker Desktop or Docker Engine with Compose
- local network access from the site connector to the Tuya device
- outbound HTTPS access from each site connector to ChargePilot
- Windows laptop capable of running `agent/BatteryAgent.ps1`

## 3. Environment variables

Compose reads the root `.env` file for variable substitution. The app itself reads `CHARGEPILOT_` settings from its process environment.

Required Compose settings:

```env
CHARGEPILOT_SECRET_KEY=<unique-random-secret>
CHARGEPILOT_ENCRYPTION_KEY=<unique-random-value>
CHARGEPILOT_ADMIN_USERNAME=admin
CHARGEPILOT_ADMIN_PASSWORD=<unique-strong-password>
CHARGEPILOT_POSTGRES_DB=chargepilot
CHARGEPILOT_POSTGRES_USER=chargepilot
CHARGEPILOT_POSTGRES_PASSWORD=<url-safe-random-password>
```

Other supported settings include:

```env
CHARGEPILOT_TELEMETRY_RATE_LIMIT_PER_MINUTE=60
CHARGEPILOT_ENDPOINT_OFFLINE_TIMEOUT_SECONDS=600
CHARGEPILOT_API_URL=https://api.example.com
CHARGEPILOT_FRONTEND_URL=https://app.example.com
CHARGEPILOT_SESSION_COOKIE_SECURE=true
CHARGEPILOT_SESSION_COOKIE_SAMESITE=lax
```

Generate random values rather than using placeholders. Python's `secrets.token_urlsafe(32)` is suitable for the secret key and PostgreSQL password; keep the PostgreSQL password URL-safe because Compose embeds it in the SQLAlchemy URL. The `.env` file is ignored by Git and must remain private. `CHARGEPILOT_ENCRYPTION_KEY` encrypts device local keys at rest. Preserve and
back up its value; changing it prevents the app from decrypting stored keys.
The name and format of this existing setting are unchanged.
Compose sets `CHARGEPILOT_ENVIRONMENT=production`; startup rejects a non-PostgreSQL URL, default/short secret keys, and short admin passwords.

`CHARGEPILOT_API_URL` and `CHARGEPILOT_FRONTEND_URL` are public browser-facing
HTTP(S) origins, not internal Docker service names. The API URL may be empty
when the reverse proxy serves API paths on the frontend origin. Both values
must be origins without a path, query, or fragment. The frontend origin is
also the sole credentialed CORS origin and the target for authentication
redirects. Session cookies use `Secure` in production; use `SameSite=None`
when the frontend and API are on different registrable domains.

## 4. Fresh Docker Compose deployment

From the repository root, create and populate the ignored environment file:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
python -c "import secrets; print('CHARGEPILOT_SECRET_KEY=' + secrets.token_urlsafe(32)); print('CHARGEPILOT_ENCRYPTION_KEY=' + secrets.token_urlsafe(32)); print('CHARGEPILOT_POSTGRES_PASSWORD=' + secrets.token_urlsafe(32)); print('CHARGEPILOT_ADMIN_PASSWORD=' + secrets.token_urlsafe(24))"
```

Copy the generated values into `.env` and set the admin username. Save the admin password securely; it is used to sign in after initialization.

Validate configuration and start the deployment:

```bash
docker compose config
docker compose up --build -d
```

The Compose configuration defines PostgreSQL 16, a persistent volume, PostgreSQL health checking, and an app `/ready` health check. The app container runs as an unprivileged user. Check logs with `docker compose logs -f app`; stop services with `docker compose down`. This preserves the database volume. To permanently delete the database and all stored ChargePilot data, use `docker compose down -v`.

`/health` reports process liveness. `/ready` executes a database query and returns HTTP 503 while PostgreSQL is unavailable.

The single app image runs the FastAPI backend on container port `8000` and
serves the built React frontend on container port `5173`. Compose publishes
both ports. Configure the reverse proxy to route the frontend hostname to
`5173` and the API hostname to `8000`; the API hostname must also route the
authentication paths (`/login`, `/register`, `/logout`) and any server-rendered
pages still used by the application. Set the public origins in `.env`; the
frontend configuration is injected when the container starts, so changing
these values does not require rebuilding the image:

```env
CHARGEPILOT_API_URL=https://api.example.com
CHARGEPILOT_FRONTEND_URL=https://app.example.com
CHARGEPILOT_SESSION_COOKIE_SECURE=true
CHARGEPILOT_SESSION_COOKIE_SAMESITE=lax
```

TLS should terminate at the reverse proxy. For separate registrable domains,
set `CHARGEPILOT_SESSION_COOKIE_SAMESITE=none`; Secure cookies are required.
For local plain-HTTP development only, set
`CHARGEPILOT_SESSION_COOKIE_SECURE=false`.

## 5. Local Python deployment

Install dependencies:

```bash
python -m pip install -e .[dev]
```

Configure `CHARGEPILOT_DATABASE_URL` to a reachable, existing PostgreSQL database, set strong secret/admin values, then run:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The app creates its schema and initial admin account at startup. The database role must own the application tables or have privileges to create and alter them.

## 6. Database initialization and upgrades

On a genuinely empty database, startup uses SQLAlchemy `Base.metadata.create_all()` followed by the compatibility column and foreign-key adjustments in `app/core/database.py`. The `users.created_at` column is PostgreSQL `TIMESTAMPTZ`, matching its server-side `now()` default.

The repository does not currently contain Alembic revision files. `create_all()` is not a versioned migration system and does not safely upgrade arbitrary existing schemas. Back up existing data and plan a dedicated schema migration before deploying schema-changing updates to an existing installation.

## 7. Site connector deployment

In ChargePilot, open **Connectors**, create an enrollment code for the correct
tenant, and download the connector package. On an always-on Windows, Linux, or
Raspberry Pi host on that switch LAN, extract the ZIP and run:

```bash
python -m pip install -r requirements.txt
python -m connector.chargepilot_connector --server-url "https://YOUR-CHARGEPILOT-HOST"
```

The connector prompts for the one-time code, enrolls it once, then stores its
credential in a connector-specific configuration file. On Windows this is
under `%ProgramData%\ChargePilot`; on Linux it is under
`~/.config/chargepilot`. The connector restricts access to this directory and
file; run enrollment and the long-running connector under the same restricted
host account. Production server URLs must use HTTPS (HTTP is accepted only for
loopback development). Keep the connector on the same LAN as the switches,
allow outbound HTTPS to ChargePilot, and permit TinyTuya LAN traffic (TinyTuya
discovery uses UDP 6666, 6667, 7000 and TCP 6668; check device-specific network
behavior).

Assign switches to the enrolled connector on the **Switches** page. The
connector page reports last contact and version. If you revoke the connector,
its credential is invalidated and assigned switches are unassigned.

The connector requires Python 3.12+ and an installed TinyTuya. Use the service
manager appropriate to the host to start at boot and restart on failure. Do
not put the one-time code or permanent connector credential into source
control, shared command history, or support logs.

### Docker image for Linux amd64 and arm64

The `connector/` folder contains a standalone Dockerfile and Compose file. The
GitHub Actions workflow `.github/workflows/connector-multiarch.yml` builds and
publishes `DOCKERHUB_USERNAME/chargepilot-connector` for `linux/amd64` and
`linux/arm64` on pushes to `main` that change `connector/**`. It also supports
manual runs. Configure the repository secrets `DOCKERHUB_USERNAME` and
`DOCKERHUB_TOKEN`.

The downloadable connector ZIP includes the Compose file and `.env.example`.
On the Linux host, set the Docker image, ChargePilot HTTPS URL, enrollment-code
file path, and persistent data path in `.env`. Create the enrollment code file
using the one-time code generated in ChargePilot. Before starting Compose,
restrict the code file so only the container's unprivileged UID can read it.
Then create the persistent data directory and grant it to the same UID:

```bash
sudo chown 10001:10001 enrollment-code.txt
sudo chmod 0400 enrollment-code.txt
mkdir -p connector-data
sudo chown 10001:10001 connector-data
docker compose up -d
```

Compose uses `network_mode: host` for Linux LAN discovery and persists the
connector credential under `/data`. The one-time enrollment code is mounted
as a Compose secret and read only if no connector credential exists yet.
Set `CHARGEPILOT_CONNECTOR_IMAGE` to the digest reported by the successful
connector image workflow before pulling and restarting. The image reference is
immutable; deployments do not silently follow a moving `latest` tag.

The Switches page can also scan directly from the ChargePilot app's network
without a connector. This scans from the app runtime itself: for Docker
deployments, configure the container/network and host firewall to allow LAN
reachability and TinyTuya discovery traffic (UDP 6666, 6667, 7000 and TCP
6668). Use an online site connector in the scan-location selector when devices
are on a different LAN or the app host cannot reach the switch network.

## 8. Windows laptop agent deployment

The PowerShell agent is located at `agent/BatteryAgent.ps1`.

```powershell
powershell -ExecutionPolicy Bypass -File .\agent\BatteryAgent.ps1 -ServerUrl "http://YOUR_SERVER:8000" -EndpointToken "YOUR_ENDPOINT_TOKEN" -AgentVersion "1.0.0"
```

Use `agent/CreateAgentScheduledTask.ps1` to register the recurring Windows task. The agent sends hostname, IP address, battery percentage, charging/AC state, switch state, timestamp, and agent version.

Agent tokens are generated randomly for new installations and can be viewed or rotated from the authenticated **Install Agent** page. Existing deployments initialized with the historical `test-endpoint-token` should rotate it after upgrading.

## 9. Device and mapping workflow

1. Enroll a connector on the LAN where the Tuya device is located.
2. Discover the device through that connector, or add it manually.
3. Save its device ID, local key, IP, protocol version, and device type.
4. Assign the device to the correct connector.
5. Create the endpoint and mapping records.
6. Ensure the mapping points to the intended device and channel.
7. Confirm the channel index and thresholds before enabling automation.

The default thresholds are `on_threshold = 79`, `off_threshold = 99`, and `minimum_state_change_interval = 300` seconds.

## 10. Operational checklist

- Keep `.env` and database backups private; do not commit secrets.
- Confirm `docker compose ps` shows both services healthy.
- Keep PostgreSQL storage in the named volume and back it up before updates.
- Verify the connector is online and the Tuya device is reachable from its LAN.
- Confirm device protocol version and channel index.
- Inspect automation events after failed or unexpected state changes.

## 11. Validation commands

```bash
pytest tests/unit/test_rule_engine.py -q
pytest tests/api/test_device_mapping_crud.py -q
```

## 12. Important cautions

- The current authentication flow is intentionally simple and should not be treated as a complete production security boundary.
- Local keys are encrypted at rest using `CHARGEPILOT_ENCRYPTION_KEY`; backups
  must preserve the matching key setting.
- `TinyTuya` payloads vary by device family; do not assume a flat boolean status.
- Commands are desired-state, leased, and expire; inspect the command row and
  resulting event when troubleshooting delayed or failed work.
- The cloud app cannot control a device whose LAN has no active connector.
