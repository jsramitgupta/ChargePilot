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

## Remote Linux validation host

The user has authorized validation on the deployed Linux server at
`rootuser@192.168.1.21`. When a task requires checking Linux-specific shell
behavior, Docker, or the k3s cluster, the agent may connect with SSH using the
existing local SSH key or SSH configuration:

```bash
ssh rootuser@192.168.1.21
```

Use the host for task-relevant validation only. Prefer read-only inspection
commands for cluster and deployment checks (for example, `kubectl get`,
`kubectl describe`, `kubectl logs`, and Docker status/image inspection). Do not
print or copy secrets from the host. Never save passwords, private keys, or
tokens in this repository. The deployed k3s cluster may be used for
development integration checks, but it is shared infrastructure, not a
disposable local cluster. Do not use it for destructive tests or modify
workloads, persistent data, or cluster configuration unless the user
explicitly requests that specific operation.

For a requested application update, prefer the established GitHub Actions
image publish and GitOps manifest update workflow. Do not manually set image
tags or apply manifests unless the user specifically requests a direct
operational change. Validate the resulting rollout with read-only status,
image, and pod checks. The standing authorization to validate alone does not
authorize deployments, restarts, data changes, or other operational
mutations.

## 2. Prerequisites

- Python 3.12+ for local installs; production images use Python 3.15, the latest
  stable release (Python does not designate formal LTS releases)
- The frontend image build uses Node.js 24.22.0, the latest LTS release, pinned
  by the official image digest
- Docker Desktop or Docker Engine with Compose
- local network access from the site connector to the Tuya device
- outbound HTTPS access from each site connector to ChargePilot
- Windows device with a battery capable of running the currently supported
  `agent/BatteryAgent.ps1` agent
- macOS 13+ with Swift 5.9+ for the `agent/macos` menu-bar app and CLI
- Node.js 24 LTS for frontend local development

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
CHARGEPILOT_TELEMETRY_MAX_AGE_SECONDS=604800
CHARGEPILOT_TELEMETRY_MAX_FUTURE_SKEW_SECONDS=300
CHARGEPILOT_TELEMETRY_AUTOMATION_MAX_AGE_SECONDS=600
CHARGEPILOT_TELEMETRY_ENABLED_PLATFORMS=windows,macos
CHARGEPILOT_TELEMETRY_AUTOMATION_ENABLED_PLATFORMS=windows,macos
CHARGEPILOT_API_URL=https://api.example.com
CHARGEPILOT_FRONTEND_URL=https://app.example.com
CHARGEPILOT_TURNSTILE_SITE_KEY=<public-turnstile-site-key>
CHARGEPILOT_TURNSTILE_SECRET_KEY=<private-turnstile-secret-key>
CHARGEPILOT_SESSION_COOKIE_SECURE=true
CHARGEPILOT_SESSION_COOKIE_SAMESITE=lax
CHARGEPILOT_KAFKA_BOOTSTRAP_SERVERS=kafka:9092
CHARGEPILOT_TELEMETRY_KAFKA_TOPIC=chargepilot.telemetry.v1
CHARGEPILOT_TELEMETRY_DEAD_LETTER_TOPIC=chargepilot.telemetry.dlq.v1
CHARGEPILOT_TELEMETRY_CONSUMER_GROUP=chargepilot-automation-v1
```

The application defaults enable enrollment and telemetry for Windows, macOS,
Android, and iOS. Set `CHARGEPILOT_TELEMETRY_ENABLED_PLATFORMS` to a narrower
comma-separated list if production rollout should restrict enrollment.
Automation defaults to Windows/macOS only and is independently configured by
`CHARGEPILOT_TELEMETRY_AUTOMATION_ENABLED_PLATFORMS`. New endpoints start
with automation off; endpoint opt-in also requires a fresh sample and an
allow-listed platform. Android has an emulator smoke test and iOS a simulator
smoke test; physical-device validation remains outstanding. Keep the ingress
limit at seven days unless a compatibility change is reviewed; the 600-second
automation maximum is intentionally separate.

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

Public tenant and standard-user signup require Cloudflare Turnstile. Create a
Turnstile widget for the frontend hostname, configure its site key and secret
as `CHARGEPILOT_TURNSTILE_SITE_KEY` and
`CHARGEPILOT_TURNSTILE_SECRET_KEY`, and keep the secret only in the backend
environment/secret store. The public site key is injected into
`runtime-config.js`; the API validates each single-use token with Cloudflare,
checking both the configured frontend hostname and the `registration` action.
Registration returns HTTP 503 when the production keys or frontend origin are
not configured, rather than accepting an unverified signup. Local development
also requires a Turnstile widget configured for its frontend hostname.

The API rejects browser state-changing requests that include an `Origin`
different from `CHARGEPILOT_FRONTEND_URL`. Preserve this exact frontend origin
when changing hostnames. Add Cloudflare rate-limiting rules for POST requests
to `/api/v1/auth/register` and `/api/v1/auth/login` as an additional edge
control; include `/api/v1/auth/resend-verification` and
`/api/v1/support/email` as well and choose
thresholds appropriate for the expected shared-IP traffic.
New public accounts also require email verification. Configure SMTP and the
frontend origin before enabling signups; Turnstile remains independently
required. Existing users created before email verification are not blocked.

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

Compose starts PostgreSQL 16, a single-node Kafka broker, separate API and
frontend containers, the outbox relay, and the automation worker. PostgreSQL
and Kafka data use named volumes; only the API/frontend ports are published.
The API and worker
containers run as unprivileged users. Check `docker compose ps` and logs for
`app`, `outbox-relay`, and `automation-worker`. `docker compose down` preserves
database and broker volumes. `docker compose down -v` permanently deletes both
stores and all local data.

`/health` reports process liveness. `/ready` executes a database query and returns HTTP 503 while PostgreSQL is unavailable.

The API image serves FastAPI on container port `8000`; the frontend image
serves the built React application on `5173`. Compose publishes both ports.
Configure the reverse proxy to route the frontend hostname to `5173` and JSON
API calls, authenticated downloads, and public agent/connector source downloads
to `8000`. React is the only browser UI;
legacy page GETs redirect to the configured frontend origin. The frontend
receives only public runtime configuration, including the Turnstile site key;
keep private Turnstile and other server secrets in the API environment.
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
`https://console-chargepilot.endusercompute.in` and the JSON API and downloads
at `https://api-chargepilot.endusercompute.in`. Create DNS/proxy records for
both hosts that route to the existing public ingress. The checked-in Istio
Gateway accepts HTTP on port 80; public TLS must be terminated by the existing
edge proxy or explicitly configured at the ingress before HTTPS traffic reaches
the cluster. Keep the browser-facing origins HTTPS.

The checked-in k3s topology is sized for a single-node installation: one API,
one frontend, relay, automation consumer, PostgreSQL StatefulSet, and
single-node Kafka StatefulSet. PostgreSQL and Kafka use private cluster services and
`local-path` persistent volumes. Back up the data and keep the node available;
this is not an HA or 10M-device topology. A node or disk failure can take down
the stateful services. Do not expose PostgreSQL or Kafka through a
LoadBalancer, NodePort, Istio route, or public DNS. For production-scale
availability, replace the single-node stateful services with reviewed
multi-node PostgreSQL and Kafka services before increasing traffic.
Each Deployment and StatefulSet retains at most one prior controller revision
for rollback. Older zero-replica Deployment ReplicaSets are historical
metadata, not extra running pods; each service remains configured for one
replica.

This creates a fresh in-cluster database and does not import or connect to the
existing Docker-host PostgreSQL installation. Keep that deployment and its
data untouched until the k3s instance has been independently validated.

#### One-time GitHub setup

1. Create Docker Hub repositories `endusercompute/chargepilot-api` and
   `endusercompute/chargepilot-frontend`, plus a Docker Hub access token with
   permission to push both images.
2. In GitHub **Settings → Secrets and variables → Actions**, add repository
   secret `DOCKERHUB_TOKEN`. The workflows use Docker Hub username
   `endusercompute`; never put the token in a workflow or repository file.
3. Ensure Actions is allowed to use the repository `GITHUB_TOKEN` with
   **Read and write permissions**. `publish-deploy.yml` needs `contents: write`
   to update the deployed image tag in `deploy/k3s/kustomization.yaml`; the
   agent release job needs it to publish tagged release assets.
4. Keep `main` writable by the workflow bot for that deployment-tag commit.
   The CI workflow ignores commits that only change the generated image tag,
   preventing a publish loop.

#### Workflow security and build best practices

The GitHub Actions pipeline keeps routine validation separate from publishing:

- `ci.yml` always reports a PR check, then runs Python tests/lint, frontend
  lint/build, and container builds only for affected server components. This
  avoids path-filtered workflow skips leaving required branch-protection checks
  pending.
- `publish-deploy.yml` runs only after successful CI for the latest `main`
  commit from this repository. It compares API/frontend source files with the
  source revision recorded in their deployed image tags, so stale CI runs and
  unchanged images are skipped. API and frontend tags are updated independently.
- `connector-multiarch.yml` builds only for connector-related changes or an
  explicit manual rebuild.
- Trivy scans each created image for OS/library vulnerabilities and secrets.
  Published multi-platform images are scanned by digest for AMD64 and ARM64.
  High and critical findings with fixes available fail the workflow before the
  image tag is promoted to the k3s manifests. Images include BuildKit
  provenance and SBOM attestations.
- Python runtime images remove package-installer tooling and copy the final
  filesystem into a `scratch` stage so scanners do not report vulnerable
  bundled packages left in upstream image layers.
- Workflows grant read-only repository permissions by default; only the
  deployment workflow and tagged agent release job receive the narrowly
  scoped `contents: write` permission. Third-party actions are pinned to full
  commit SHAs, registry credentials stay in Actions secrets, and generated
  manifest-only commits do not start another CI run.

Agent source is not copied into the API image. `build-agent-artifacts.yml`
builds APK, unsigned IPA, and DMG artifacts for changes under `agent/`; an
`agents-v*` tag also publishes those binaries and platform source archives as a
GitHub Release. The public `/agent/.../download` API routes redirect to the
latest stable release assets. Before deploying API code that uses those
redirects, publish the first agent release (for example, create and push
`agents-v0.1.0`). No additional GitHub secret or application environment
variable is required for release creation.

Use short-lived branches named `server/<change>`, `agents/<change>`, or
`connector/<change>` and merge them into protected `main` through pull
requests. The names make work easy to identify; the workflows enforce
component boundaries by changed files:

- Agent-only changes run the agent artifact workflow and do not run server
  tests, build server images, or trigger a deployment.
- API/frontend changes run the corresponding CI checks and publish only the
  changed images after merge to `main`.
- Connector changes validate and publish the connector image; the API image
  is also rebuilt when connector source changes because the API currently
  serves the connector source package.

The image workflow updates immutable image tags in the GitOps manifest, and
Argo CD reconciles those workload changes. Routine application deployments do
not rebuild the k3s cluster or its control plane. Protect `main` with required
CI checks and review before merging workflow or Dockerfile changes. Review
Trivy reports and update vulnerable dependencies or base-image pins rather
than bypassing scans.

#### First deployment

First merge the CI/CD and manifest changes to `main`. Each main commit runs
`ci.yml` (Python lint/tests and frontend lint/build). After successful CI,
`publish-deploy.yml` builds, scans, and pushes only changed API/frontend
multi-platform images to Docker Hub as
`endusercompute/chargepilot-api:sha-<full-commit-sha>` and
`endusercompute/chargepilot-frontend:sha-<full-commit-sha>`, then commits only
the corresponding changed tag into the kustomization. Connector images are
published by `connector-multiarch.yml` after their own multi-platform build
and security scans. CI-only commits do not publish images.

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
CHARGEPILOT_API_URL=https://api-chargepilot.endusercompute.in
CHARGEPILOT_FRONTEND_URL=https://console-chargepilot.endusercompute.in
CHARGEPILOT_TURNSTILE_SITE_KEY=<public-turnstile-site-key>
CHARGEPILOT_TURNSTILE_SECRET_KEY=<private-turnstile-secret-key>
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

Configure the DNS provider or edge proxy for both hostnames and ensure its TLS
mode matches the origin connection. The current Istio Gateway manifest accepts
HTTP only; do not select strict HTTPS-to-origin validation unless TLS is
configured on the ingress with a matching certificate.

Only after the first successful Docker publish has updated the image tag, add
the ArgoCD Application:

```bash
sudo kubectl apply -f deploy/argocd/chargepilot.yaml
sudo kubectl -n argocd get applications.argoproj.io chargepilot -w
sudo kubectl -n chargepilot get pods,pvc,services
sudo kubectl -n chargepilot rollout status statefulset/chargepilot-postgres
sudo kubectl -n chargepilot rollout status statefulset/chargepilot-kafka
sudo kubectl -n chargepilot rollout status deployment/chargepilot-api
sudo kubectl -n chargepilot rollout status deployment/chargepilot-frontend
sudo kubectl -n chargepilot rollout status deployment/chargepilot-outbox-relay
sudo kubectl -n chargepilot rollout status deployment/chargepilot-automation
```

For an existing local k3s installation, retain its PostgreSQL and Kafka PVCs.
Build local images and import them into the k3s containerd image store:

```bash
sudo docker build -t chargepilot-api:local -f docker/Dockerfile .
sudo docker build -t chargepilot-frontend:local -f frontend/Dockerfile .
sudo docker save chargepilot-api:local chargepilot-frontend:local \
  | sudo k3s ctr images import -
```

To apply the checked-in manifests using those local tags, render the
kustomization and replace only the two published image references:

```bash
sudo kubectl kustomize deploy/k3s \
  | sed -E 's#endusercompute/chargepilot-api:[^[:space:]]+#chargepilot-api:local#g; s#endusercompute/chargepilot-frontend:[^[:space:]]+#chargepilot-frontend:local#g' \
  | sudo kubectl apply -f -
sudo kubectl -n chargepilot rollout status deployment/chargepilot-api
sudo kubectl -n chargepilot rollout status deployment/chargepilot-frontend
sudo kubectl -n chargepilot rollout status deployment/chargepilot-outbox-relay
sudo kubectl -n chargepilot rollout status deployment/chargepilot-automation
sudo kubectl -n chargepilot get pods,services
```

The local image override is not GitOps state: after a successful publish,
ArgoCD should reconcile to the immutable Docker Hub tags. Keep automated sync
disabled during an image bootstrap if either repository/tag is not available.

In Cloudflare, create proxied DNS records for both hostnames to the public
address that forwards TCP 443 to the k3s Istio ingress gateway. Set SSL/TLS
encryption to **Full (strict)** for a Cloudflare Origin Certificate. Do not
publish internal service addresses or the PostgreSQL/Kafka ports.

#### Configure SMTP for email verification on k3s

The API optionally loads SMTP credentials from a separate
`chargepilot-smtp` Secret. Create or update it without replacing
`chargepilot-runtime`; the secret below prompts for the SMTP password without
echoing it, stores the temporary environment file in `/dev/shm`, and removes
it on exit. For Gmail, use `smtp.gmail.com`, port `587`, STARTTLS, and a
Google App Password (not the account password). `SMTP_FROM_EMAIL` must be the
authenticated Gmail address or a verified Gmail send-as alias. You can use
`chargepilot.support@endusercompute.in` as the sender if that address is
configured as the authenticated mailbox or an authorized send-as alias.
Support requests are sent to `CHARGEPILOT_SUPPORT_RECIPIENT`, which defaults
to `chargepilot.support@endusercompute.in`. To route them elsewhere, add
`CHARGEPILOT_SUPPORT_RECIPIENT=your-support-inbox@example.com` to the
`chargepilot-smtp` Secret values.

Run this on the k3s control-plane host:

```bash
sudo bash <<'SH'
set -eu
umask 077
secret_file="$(mktemp /dev/shm/chargepilot-smtp.XXXXXX)"
trap 'rm -f "$secret_file"' EXIT
read -r -p "SMTP username/email: " smtp_username </dev/tty
read -r -p "Verified sender email: " smtp_from_email </dev/tty
read -r -s -p "SMTP app password: " smtp_password </dev/tty
printf '\n'
{
  printf 'CHARGEPILOT_SMTP_HOST=%s\n' 'smtp.gmail.com'
  printf 'CHARGEPILOT_SMTP_PORT=%s\n' '587'
  printf 'CHARGEPILOT_SMTP_USERNAME=%s\n' "$smtp_username"
  printf 'CHARGEPILOT_SMTP_PASSWORD=%s\n' "$smtp_password"
  printf 'CHARGEPILOT_SMTP_FROM_EMAIL=%s\n' "$smtp_from_email"
  printf 'CHARGEPILOT_SMTP_FROM_NAME=%s\n' 'ChargePilot'
  printf 'CHARGEPILOT_SMTP_USE_STARTTLS=%s\n' 'true'
  printf 'CHARGEPILOT_SMTP_USE_SSL=%s\n' 'false'
  printf 'CHARGEPILOT_SUPPORT_RECIPIENT=%s\n' 'chargepilot.support@endusercompute.in'
} > "$secret_file"
sudo kubectl -n chargepilot create secret generic chargepilot-smtp \
  --from-env-file="$secret_file" --dry-run=client -o yaml | sudo kubectl apply -f -
sudo kubectl -n chargepilot rollout restart deployment/chargepilot-api
sudo kubectl -n chargepilot rollout status deployment/chargepilot-api
SH
```

For another SMTP provider, change the host, port, and TLS values to match its
documented configuration. If signup remains unavailable after the API
rollout, verify that `chargepilot-runtime` still contains both
`CHARGEPILOT_TURNSTILE_SITE_KEY` and `CHARGEPILOT_TURNSTILE_SECRET_KEY`, and
that its `CHARGEPILOT_FRONTEND_URL` is the exact public frontend origin. Check
API logs for mail-delivery errors without printing Secret contents. Never
include SMTP credentials in shell history, manifests, or support output.
To list runtime Secret key names without showing their values:

```bash
sudo kubectl -n chargepilot get secret chargepilot-runtime \
  -o go-template='{{range $key, $value := .data}}{{$key}}{{"\n"}}{{end}}'
```

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

Email verification adds nullable `users.email`, `users.email_verified` (legacy
rows default to verified), a unique index for non-null email addresses, and the
`email_verifications` token table. Startup creates the token table and applies
the user-column compatibility additions; back up an existing database before
upgrading and check for duplicate non-null email values before applying the
unique index.

The repository does not currently contain Alembic revision files. `create_all()` is not a versioned migration system and does not safely upgrade arbitrary existing schemas. Back up existing data and run the reviewed SQL migrations before deploying schema-changing updates to an existing installation.

Cross-platform telemetry adds `endpoints.installation_id`, `platform`,
`device_class`, and `automation_enabled`, makes `ac_connected` nullable, adds
unique partial indexes for per-install identity/credential hashes, and creates
`endpoint_enrollments`. For existing PostgreSQL deployments:

1. Take and verify a database backup.
2. Stop API, outbox-relay, and automation-consumer processes.
3. Apply `deploy/migrations/20261020_cross_platform_telemetry.sql` through a
   private database connection, not a published database port.
4. Deploy the new application and run Windows regression tests before enabling
   macOS enrollment.

Rollback is in `deploy/migrations/20261020_cross_platform_telemetry_rollback.sql`.
It removes enrollment rows and platform identity/eligibility data and converts
unknown AC values to `false`; only use it after disabling new clients and
accepting that data loss. Test both scripts against a backup before production.

Universal endpoint enrollment adds a nullable enrollment platform and
`enrollment_count` / `last_used_at` metadata so one hash-only token can enroll
multiple devices across platforms for 24 hours. For existing PostgreSQL
deployments, back up and verify the database, then apply
`deploy/migrations/20261020_universal_endpoint_enrollment.sql` through the
private database service before deploying the application. Its rollback
invalidates all universal tokens and converts them to expired Windows-scoped
records; already enrolled endpoint credentials remain intact.

Enrollment-token reveal adds the nullable `endpoint_enrollments.encrypted_code`
column. New tokens retain their verifier as a SHA-256 hash and a separately
encrypted reveal value protected by the existing `CHARGEPILOT_ENCRYPTION_KEY`.
The key must remain stable and available to every API process. For an existing
PostgreSQL deployment:

1. Take and verify a database backup.
2. Apply `deploy/migrations/20261021_endpoint_enrollment_reveal.sql` through
   the private database service before deploying the updated API.
3. Deploy the API and verify token creation, reveal, and revocation.

The rollback file drops only the encrypted reveal column; token hashes,
exchange behavior, and enrollment rows remain. Roll back the API before
applying `deploy/migrations/20261021_endpoint_enrollment_reveal_rollback.sql`.
After rollback, reveal is unavailable. Existing tokens created before this
migration have no encrypted value and cannot be revealed; they remain usable
until expiry or revocation, after which an administrator can create a new
token. On a genuinely empty database, `create_all()` creates the column from
the current model, but does not add it to an existing table.

Legacy Windows endpoints are identified by the
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

Create a one-time enrollment code in **Connectors** for the correct tenant.
Use the published multi-platform Docker image on Linux, or the one-line Python
installer on Linux/macOS. Both use the k3s API URL by default:
`https://api-chargepilot.endusercompute.in`.

### Docker Compose on Linux

Save this as `docker-compose.yml`. The image is published for amd64 and arm64;
Compose pulls it when starting and creates a persistent Docker-managed volume
for the connector credential.

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

Pass the one-time code as an environment variable when starting it for the
first time:

```sh
read -rsp 'One-time ChargePilot code: ' CHARGEPILOT_CONNECTOR_ENROLLMENT_CODE && echo && export CHARGEPILOT_CONNECTOR_ENROLLMENT_CODE && docker compose up -d && unset CHARGEPILOT_CONNECTOR_ENROLLMENT_CODE
```

This prompts without recording the code in shell history. It is still visible
in Docker container metadata while configured. Once the connector is online,
run `docker compose up -d --force-recreate` without setting the variable to
remove the code from the container; the permanent credential remains in the
Docker-managed volume. No `connector-data` directory, enrollment-code file, or
ownership commands are needed.

### Python on Linux or macOS

Install Python 3.12+, `curl`, and `unzip`. Run this on the switch LAN and
enter the one-time enrollment code when prompted:

```sh
curl -fsSL https://api-chargepilot.endusercompute.in/connectors/install.sh | sh
```

The installer downloads the public source package over HTTPS, creates a
virtual environment, and saves the connector credential under
`~/.local/share/chargepilot/site-connector/`. Keep the process running or
configure your OS service manager to start it at boot. The command executes an
installer from your ChargePilot server; use it only if you trust that server.

For Windows Python hosts, download and extract the public source package, then
run these commands from the extracted folder and enter the one-time code when
prompted:

```powershell
python -m pip install -r requirements.txt
python -m connector.chargepilot_connector --server-url "https://api-chargepilot.endusercompute.in"
```

### Windows agent

On **Set up a device**, select the workspace, create an enrollment token, and
copy the generated PowerShell command. Run it on the Windows device; it
downloads the installer and agent over HTTPS, prompts for the enrollment token,
and registers the recurring task. The command uses `iex`; run it only against
a ChargePilot server you trust. Public release assets contain no credentials.
Setup APIs and token management remain authenticated. Existing Windows agents
using the legacy shared-token protocol must use their assigned tenant's token;
the global token is only for unassigned endpoints.

### macOS agent

On **Set up a device**, choose the correct tenant and create a reusable
24-hour enrollment token. The same token can enroll multiple devices across
enabled platforms until it expires or is revoked. Each admin may have up to
five active tokens across workspaces; the creator can reveal or hide each
active token until it expires. Expired and revoked tokens are hidden.
Download the macOS DMG from the GitHub Release, move the app to Applications,
and enter the API origin, device label, and enrollment token in the menu-bar
app. The per-install credential is stored in the user's Keychain. The
development DMG is unsigned and not notarized; follow the macOS approval
prompt if needed. The app reports only while running and the Mac is awake.
The source project is also available from the release for users who prefer to
build it. Revoke a token to prevent new enrollments and revoke individual
endpoint credentials from the **Endpoints** page to stop already-enrolled
devices. New endpoints remain telemetry-only until an authorized admin
enables automation after a fresh sample.

Keep the connector on the switch LAN and allow outbound HTTPS plus local Tuya
traffic (UDP 6666, 6667, 7000 and TCP 6668). Assign switches to the enrolled
connector on the **Switches** page.

## 9. Device and mapping workflow

1. Enroll a connector on the LAN where the Tuya device is located.
2. Discover the device through that connector, or add it manually.
3. Save its device ID, local key, IP, protocol version, and device type.
4. Assign the device to the correct connector.
5. Enroll supported devices using a workspace enrollment token. If a legacy
   Windows device was registered with the global token, assign it to the tenant
   from the Super Admin Endpoints page, then re-run its installer using the
   tenant-specific command.
6. Create a mapping only when the endpoint and switch belong to the same tenant.
   Tenant ownership is visible on the dashboard, endpoint/switch lists, and
   mapping form.
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
