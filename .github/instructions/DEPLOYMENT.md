# Deployment Guide

## 1. Deployment model

The cloud control plane runs a FastAPI management/API service, a PostgreSQL
transactional store, a Kafka broker, a transactional-outbox relay, and
independent automation consumers. The local Compose broker is a single-node
development configuration. Production requires an appropriately secured and
replicated Kafka service plus a PostgreSQL deployment sized for the measured
workload. Deploy one ChargePilot site connector on an always-on host at each
physical LAN containing Tuya devices.

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
CHARGEPILOT_KAFKA_BOOTSTRAP_SERVERS=kafka:9092
CHARGEPILOT_TELEMETRY_KAFKA_TOPIC=chargepilot.telemetry.v1
CHARGEPILOT_TELEMETRY_DEAD_LETTER_TOPIC=chargepilot.telemetry.dlq.v1
CHARGEPILOT_TELEMETRY_CONSUMER_GROUP=chargepilot-automation-v1
```

Production Kafka should use TLS and preferably SASL over TLS. Set
`CHARGEPILOT_KAFKA_SECURITY_PROTOCOL=SASL_SSL`,
`CHARGEPILOT_KAFKA_SASL_MECHANISM`, `CHARGEPILOT_KAFKA_SASL_USERNAME`, and
`CHARGEPILOT_KAFKA_SASL_PASSWORD` through a secret manager; mount a trusted CA
and set `CHARGEPILOT_KAFKA_SSL_CA_FILE` when the cluster uses a private CA.
Compose's local broker uses plaintext only on its private Compose network and
does not publish port 9092.

Generate random values rather than using placeholders. Python's `secrets.token_urlsafe(32)` is suitable for the secret key and PostgreSQL password; keep the PostgreSQL password URL-safe because Compose embeds it in the SQLAlchemy URL. The `.env` file is ignored by Git and must remain private. `CHARGEPILOT_ENCRYPTION_KEY` encrypts device local keys at rest. Preserve and
back up its value; changing it prevents the app from decrypting stored keys.
The name and format of this existing setting are unchanged.
Compose sets `CHARGEPILOT_ENVIRONMENT=production`; startup rejects a non-PostgreSQL URL, default/short secret keys, and short admin passwords.

`CHARGEPILOT_API_URL` and `CHARGEPILOT_FRONTEND_URL` are public browser-facing
HTTP(S) origins, not internal Docker service names. The API URL may be empty
when the reverse proxy serves API paths on the frontend origin. Both values
must be origins without a path, query, or fragment. The frontend origin is
also the sole credentialed CORS origin and the target for authentication
redirects. Agent setup uses `CHARGEPILOT_API_URL` as the server URL embedded
in the Windows install command; set it to the public HTTPS API origin when
agents connect through a TLS-terminating proxy. Session cookies use `Secure` in production; use `SameSite=None`
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

Compose starts PostgreSQL 16, a single-node Kafka broker, the API/frontend,
the outbox relay, and the automation worker. PostgreSQL and Kafka data use
named volumes; only the API/frontend ports are published. The API and worker
containers run as unprivileged users. Check `docker compose ps` and logs for
`app`, `outbox-relay`, and `automation-worker`. `docker compose down` preserves
database and broker volumes. `docker compose down -v` permanently deletes both
stores and all local data.

`/health` reports process liveness. `/ready` executes a database query and returns HTTP 503 while PostgreSQL is unavailable.

The API image serves FastAPI on container port `8000` and the built React
frontend on `5173`. Compose publishes both ports. Configure the reverse proxy to route the frontend hostname to
`5173` and the API hostname to `8000`; API calls, downloads, form submissions,
and server-rendered operational pages that remain in use must reach FastAPI.
Authenticated app navigation uses React routes on the frontend origin. Login
and registration pages are served only by the frontend; API `GET /login` and
`GET /register` redirect to the configured frontend origin.
Set the public origins in `.env`; the
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

Telemetry HTTP success means the endpoint snapshot and outbox event were
committed; rule evaluation and switch commands happen asynchronously. Monitor
outbox age, Kafka consumer lag, dead-letter volume, and connector command
completion before considering telemetry fully processed.

### k3s, Istio, and ArgoCD deployment

The GitOps manifests live in `deploy/k3s/`; `deploy/argocd/chargepilot.yaml`
defines the ArgoCD Application. The deployment exposes the UI at
`https://app.endusercompute.in` and the API, agent endpoint, and server-rendered
pages at `https://api.endusercompute.in`. Istio redirects HTTP to HTTPS and
terminates TLS on the existing ingress gateway using the
`chargepilot-ingress-tls` Secret in `istio-system`.

The checked-in k3s topology is sized for a single-node installation: one API,
relay, automation consumer, PostgreSQL StatefulSet, and single-node Kafka
StatefulSet. PostgreSQL and Kafka use private cluster services and
`local-path` persistent volumes. Back up the data and keep the node available;
this is not an HA or 10M-device topology. A node or disk failure can take down
the stateful services. Do not expose PostgreSQL or Kafka through a
LoadBalancer, NodePort, Istio route, or public DNS. For production-scale
availability, replace the single-node stateful services with reviewed
multi-node PostgreSQL and Kafka services before increasing traffic.

This creates a fresh in-cluster database and does not import or connect to the
existing Docker-host PostgreSQL installation. Keep that deployment and its
data untouched until the k3s instance has been independently validated.

#### One-time GitHub setup

1. Create the Docker Hub repository `endusercompute/chargepilot` and a
   Docker Hub access token with permission to push images.
2. In GitHub **Settings → Secrets and variables → Actions**, add repository
   secret `DOCKERHUB_TOKEN`. The workflows use Docker Hub username
   `endusercompute`; never put the token in a workflow or repository file.
3. Ensure Actions is allowed to use the repository `GITHUB_TOKEN` with
   **Read and write permissions**. `publish-deploy.yml` needs `contents: write`
   to update the deployed image tag in `deploy/k3s/kustomization.yaml`.
4. Keep `main` writable by the workflow bot for that deployment-tag commit.
   The CI workflow ignores commits that only change the generated image tag,
   preventing a publish loop.

#### First deployment

First merge the CI/CD and manifest changes to `main`. Each main commit runs
`ci.yml` (Python lint/tests and frontend lint/build). After successful CI,
`publish-deploy.yml` builds and pushes the multi-platform app image to Docker
Hub as `endusercompute/chargepilot:sha-<full-commit-sha>`, then commits that
tag into the kustomization. The `sha-<full-commit-sha>` format intentionally
matches the existing Docker Hub workflow. ArgoCD tracks `main` and automatically
deploys the updated tag; CI-only commits do not publish an image.

Before syncing the ArgoCD Application, create the namespace secrets out of
band. Use a private environment file `.env.k3s` (do not commit it) with these
entries:

```env
CHARGEPILOT_DATABASE_URL=postgresql+psycopg://chargepilot:<URL_SAFE_DB_PASSWORD>@chargepilot-postgres:5432/chargepilot
CHARGEPILOT_POSTGRES_PASSWORD=<same_URL_SAFE_DB_PASSWORD>
CHARGEPILOT_SECRET_KEY=<unique_random_secret_at_least_32_characters>
CHARGEPILOT_ENCRYPTION_KEY=<unique_random_value_at_least_32_characters>
CHARGEPILOT_ADMIN_USERNAME=admin
CHARGEPILOT_ADMIN_PASSWORD=<unique_strong_password>
CHARGEPILOT_API_URL=https://api.endusercompute.in
CHARGEPILOT_FRONTEND_URL=https://app.endusercompute.in
CHARGEPILOT_SESSION_COOKIE_SECURE=true
CHARGEPILOT_SESSION_COOKIE_SAMESITE=lax
CHARGEPILOT_KAFKA_BOOTSTRAP_SERVERS=chargepilot-kafka.chargepilot.svc.cluster.local:9092
CHARGEPILOT_KAFKA_SECURITY_PROTOCOL=PLAINTEXT
CHARGEPILOT_KAFKA_SASL_MECHANISM=
CHARGEPILOT_KAFKA_SASL_USERNAME=
CHARGEPILOT_KAFKA_SASL_PASSWORD=
CHARGEPILOT_KAFKA_SSL_CA_FILE=
CHARGEPILOT_TELEMETRY_KAFKA_TOPIC=chargepilot.telemetry.v1
CHARGEPILOT_TELEMETRY_DEAD_LETTER_TOPIC=chargepilot.telemetry.dlq.v1
CHARGEPILOT_TELEMETRY_CONSUMER_GROUP=chargepilot-automation-v1
```

Generate unique values locally; use URL-safe characters for the PostgreSQL
password because it appears in the SQLAlchemy URL. Keep `.env.k3s` mode `0600`.
Create the runtime secret without printing its values:

```bash
chmod 600 .env.k3s
sudo kubectl create namespace chargepilot \
  --dry-run=client -o yaml | sudo kubectl apply -f -
sudo kubectl -n chargepilot create secret generic chargepilot-runtime \
  --from-env-file=.env.k3s --dry-run=client -o yaml | sudo kubectl apply -f -
```

Create a Cloudflare Origin Certificate for both hostnames (or use another
certificate trusted by your clients) and keep its private key out of the repo.
With the certificate and key available as local files, create the secret used
by the Istio gateway:

```bash
sudo kubectl -n istio-system create secret tls chargepilot-ingress-tls \
  --cert=origin-cert.pem --key=origin-key.pem \
  --dry-run=client -o yaml | sudo kubectl apply -f -
```

Only after the first successful Docker publish has updated the image tag, add
the ArgoCD Application:

```bash
sudo kubectl apply -f deploy/argocd/chargepilot.yaml
sudo kubectl -n argocd get applications.argoproj.io chargepilot -w
sudo kubectl -n chargepilot get pods,pvc,services
sudo kubectl -n chargepilot rollout status statefulset/chargepilot-postgres
sudo kubectl -n chargepilot rollout status statefulset/chargepilot-kafka
sudo kubectl -n chargepilot rollout status deployment/chargepilot-api
sudo kubectl -n chargepilot rollout status deployment/chargepilot-outbox-relay
sudo kubectl -n chargepilot rollout status deployment/chargepilot-automation
```

In Cloudflare, create proxied DNS records for both hostnames to the public
address that forwards TCP 443 to the k3s Istio ingress gateway. Set SSL/TLS
encryption to **Full (strict)** for a Cloudflare Origin Certificate. Do not
publish internal service addresses or the PostgreSQL/Kafka ports.

For subsequent `main` commits, the successful image publish updates the
kustomization, which ArgoCD syncs automatically. Watch the GitHub Actions
summary for the immutable tag and digest, and ArgoCD for sync/health status.
If `main` branch protections prevent GitHub Actions from pushing the
deployment-tag commit, configure an approved bot bypass or change the workflow
to open a deployment PR; do not disable branch protections blindly.

Kafka is plaintext only on the private in-cluster network in this starter
topology. The Kafka StatefulSet has one replica and 24 partitions; it is not a
production broker cluster. Configure TLS/SASL and replicated brokers before
using a remote or production Kafka service.

The current services share PostgreSQL and are not yet database-sharded.
`scripts/scale_test.py` can verify a temporary synthetic dataset above 10
million rows on a dedicated PostgreSQL database with a `_scale_test` suffix.
`tests/scale_telemetry.js` drives configurable HTTP load from k6. These tools
do not establish 10M-device capacity by themselves. Benchmark 1M active agents
at the selected reporting cadence on provisioned staging hardware, recording
the database topology, Kafka partitioning, event latency percentiles, error
rates, queue age, consumer lag, and connector outcomes. Never point scale
tools at production.

### Portainer deployments split across stacks

The Compose file's implicit default network is shared only by services in that
same Compose project. If Portainer deploys the app and PostgreSQL as separate
stacks, create one private user-defined bridge network once:

```sh
docker network create chargepilot-private
```

Declare that network as external in both stack files. Attach the database with
the stable `db` alias:

```yaml
services:
  db:
    networks:
      chargepilot-private:
        aliases:
          - db

networks:
  chargepilot-private:
    external: true
    name: chargepilot-private
```

Attach the app stack to the same network:

```yaml
services:
  app:
    networks:
      - chargepilot-private

networks:
  chargepilot-private:
    external: true
    name: chargepilot-private
```

Keep `CHARGEPILOT_DATABASE_URL` on host `db`, port `5432`, and do not add a
PostgreSQL `ports:` mapping. Start PostgreSQL first and verify it is healthy
before deploying the app; `depends_on` does not coordinate services across
separate Compose projects.

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

Laptop endpoints are identified by the Windows
`Win32_ComputerSystemProduct.UUID`; hostname remains mutable display and
diagnostic data. The endpoint `hardware_uuid` column is nullable for existing
rows, and a unique index permits those unassigned legacy rows while preventing
duplicate hardware identities. Startup adds the nullable column and index.
For a large PostgreSQL database, apply the additive change before rollout to
avoid building the unique index during API startup:

```sql
ALTER TABLE endpoints ADD COLUMN IF NOT EXISTS hardware_uuid VARCHAR(36);
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ix_endpoints_hardware_uuid
    ON endpoints (hardware_uuid);
```

`CREATE INDEX CONCURRENTLY` must run outside a transaction. Existing endpoint
rows keep their IDs and mappings; the first UUID-bearing telemetry from the
same tenant and hostname attaches the UUID to an unassigned legacy row. No
hardware identity is guessed during migration. New endpoint registrations
require an updated agent that sends a valid hardware UUID. Install the current
agent package after upgrading the API.

The telemetry lookup path now uses the composite
`ix_endpoints_tenant_hostname` index. `create_all()` creates it for a new
database, but does not add it to an already-existing `endpoints` table. For
large PostgreSQL deployments, create it outside a transaction before scaling
telemetry traffic:

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_endpoints_tenant_hostname
    ON endpoints (tenant_id, hostname);
```

The transactional outbox and automation cursor tables are created at startup;
review their storage/retention needs and PostgreSQL capacity before a high-rate
production rollout.

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
