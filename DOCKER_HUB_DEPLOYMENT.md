# Docker Hub publishing and deployment

This guide covers publishing ChargePilot images from GitHub Actions, deploying
to k3s with ArgoCD, and using the image in a microservice Compose deployment.
The API, frontend, connector, docs-web, and docs-cms images are published to
the `endusercompute` Docker Hub namespace for `linux/amd64` and `linux/arm64`.

## Continuous integration, publishing, and deployment

### One-time setup

1. Create the `chargepilot-api`, `chargepilot-frontend`,
   `chargepilot-connector`, `chargepilot-docs-web`, and
   `chargepilot-docs-cms` repositories under the `endusercompute` Docker Hub
   account.
2. Create a Docker Hub access token with permission to push all five images.
   If the repositories are private, separately create read-only pull
   credentials for k3s and authorized connector operators. Never share the CI
   push token.
3. In GitHub **Settings → Secrets and variables → Actions**, add the
   repository secret `DOCKERHUB_TOKEN`. The workflows use username
   `endusercompute`; do not commit the access token.
4. Allow GitHub Actions `GITHUB_TOKEN` **Read and write permissions** so the
   image publisher can commit the ArgoCD tag update to `main`.
5. Confirm GitHub Actions and the ArgoCD controller are enabled.
6. Before making the repository private, configure a read-only SSH deploy key
   in Argo CD. The checked-in Application uses
   `git@github.com:jsramitgupta/ChargePilot.git`; add its public key as a
   read-only deploy key in GitHub and register its private key with
   `argocd repo add git@github.com:jsramitgupta/ChargePilot.git --ssh-private-key-path <private-key-file>`.
   The live Application currently uses the public HTTPS URL. Apply the
   checked-in Application manifest and verify that its live source is SSH
   while the repository is still public.
7. To keep agent binary downloads available from a private repository, provision
   a fine-grained Contents: read token as `CHARGEPILOT_AGENT_RELEASE_GITHUB_TOKEN`
   in the separate `chargepilot-agent-release` Kubernetes Secret. The API
   proxies only installable agent binaries; source archives are not exposed.
8. For private image pulls, the k3s manifests reference
   `chargepilot-dockerhub` in `chargepilot` and
   `chargepilot-docs-dockerhub` in `chargepilot-docs`. Provision these
   namespace-local `kubernetes.io/dockerconfigjson` Secrets before the image
   repositories are made private; see the private visibility preflight in
   `.github/instructions/DEPLOYMENT.md`.

### Main-branch pipeline and security practices

`.github/workflows/ci.yml` runs Python lint/tests and frontend lint/build, then
detects image inputs changed by the commit. It builds and scans only affected
API, frontend, and connector images. A successful main-branch CI run triggers
`.github/workflows/publish-deploy.yml`; that workflow compares source files
with each API/frontend image's deployed source revision and publishes only
changed images. A newer commit makes an older run a no-op; the newer successful
CI run compares against the last deployed revisions and includes accumulated
changes. API and frontend deployment tags advance independently.

The connector workflow publishes only when connector image inputs change (or
when an operator explicitly dispatches a rebuild). All workflows pin actions
to full commit SHAs and use read-only token permissions except the deployment
job that must commit the GitOps image-tag update. Docker Hub credentials stay
in the `DOCKERHUB_TOKEN` repository secret; pull-request CI never receives
registry credentials.

Every built local image is scanned by Trivy for OS/library vulnerabilities and
secrets. Published multi-platform images are then scanned by digest for both
AMD64 and ARM64 before deployment tags advance. High/critical findings with
available fixes fail the publishing workflow; unfixed vulnerability findings
are excluded from this blocking scan. BuildKit generates provenance and SBOM
attestations for each published image. Protect `main` with required CI checks
and review before merging Dockerfile or workflow changes.

API and frontend tags use the `sha-<full-commit-sha>` format; connector tags
use the same full source SHA format. Workflow summaries report each published
digest and its scan outcome. ArgoCD tracks `main`; commits that only update
`deploy/k3s/kustomization.yaml` are excluded from CI to prevent a publish loop.

### First k3s rollout

The k3s manifests are in `deploy/k3s/`; the ArgoCD Application is
`deploy/argocd/chargepilot.yaml`. The deployment uses
`console-chargepilot.endusercompute.in` for the frontend and
`api-chargepilot.endusercompute.in` for the JSON API, Windows agent, and
downloads. Configure both DNS/proxy hosts to the existing public ingress and
ensure public HTTPS is terminated by the edge proxy or configured at ingress.
The checked-in Istio Gateway currently accepts HTTP on port 80, so configure a
TLS origin at the ingress before selecting strict HTTPS-to-origin validation.
Before applying the ArgoCD Application:

1. Merge the CI/CD and deployment changes to `main`, then wait for CI, image
   publish, and the GitOps tag update to succeed.
2. Create the `chargepilot-runtime` Kubernetes Secret from a local, untracked
   `.env.k3s` file. Include the database URL and password, application and
   admin secrets, public browser origins, and Kafka settings. Use the same
   URL-safe PostgreSQL password in both the URL and
   `CHARGEPILOT_POSTGRES_PASSWORD`.
3. Create the `chargepilot-agent-release` Secret from the secret manager or a
   secure local process; do not store the GitHub token in `.env.k3s`, Git, or
   the shared `chargepilot-runtime` Secret.
4. Apply `deploy/argocd/chargepilot.yaml`; ArgoCD will sync the app and future
   successful main-branch image updates automatically.
5. In Cloudflare, create proxied DNS records for both hostnames to the public
   address that forwards traffic to the ingress. Select a TLS mode compatible
   with the configured origin; use **Full (strict)** only after configuring a
   trusted origin certificate and TLS listener.

See `.github/instructions/DEPLOYMENT.md` for exact Secret keys, commands,
health checks, and recovery guidance.

The included k3s PostgreSQL and Kafka StatefulSets use local-path PVCs and one
replica each. They are a single-node starting deployment, not HA services or
a demonstrated 10M-device platform. Back up their data and keep PostgreSQL
and Kafka private inside the cluster.

## Install or update from Docker Hub (end users)

### Prerequisites and first-time setup

Install Docker Engine or Docker Desktop with the Docker Compose plugin. Get
`docker-compose.yml` and `.env.example` from the ChargePilot repository release
or source checkout. In the directory containing `docker-compose.yml`, create
the private environment file if it does not already exist:

```powershell
Copy-Item .env.example .env
```

Edit `.env` and set strong, unique values for the required secrets and initial
administrator credentials. Keep this file private and do not overwrite it when
updating the app. To deploy published images, set the API and frontend image
digests reported by the same successful workflow run:

```env
CHARGEPILOT_API_IMAGE=endusercompute/chargepilot-api@sha256:<api-digest>
CHARGEPILOT_FRONTEND_IMAGE=endusercompute/chargepilot-frontend@sha256:<frontend-digest>
```

Generate candidate secret values with Python, then copy them into the matching
fields in `.env`:

```powershell
python -c "import secrets; print('CHARGEPILOT_SECRET_KEY=' + secrets.token_urlsafe(32)); print('CHARGEPILOT_ENCRYPTION_KEY=' + secrets.token_urlsafe(32)); print('CHARGEPILOT_POSTGRES_PASSWORD=' + secrets.token_urlsafe(32)); print('CHARGEPILOT_ADMIN_PASSWORD=' + secrets.token_urlsafe(24))"
```

Set `CHARGEPILOT_ADMIN_USERNAME` to the desired initial administrator name.
Retain the secret and database values for subsequent restarts and upgrades.

For private Docker Hub repositories, sign in first with `docker login` using an
account that has read access to the required images. Each connector host needs
its own authorized pull credentials for a private connector image; do not
distribute the CI push token. The API/frontend split does not require a new
database. Back up PostgreSQL before upgrading an existing installation;
keep its Compose project and database volume. Validate the Compose configuration. With published image digests configured,
pull and start or update the project:

```powershell
docker compose config
docker compose pull app frontend outbox-relay automation-worker
docker compose up -d --no-build
docker compose ps
```

For a local source build instead, run `docker compose up --build -d`; do not
pull the `:local` tags from Docker Hub.

The API, outbox-relay, and automation-worker use `CHARGEPILOT_API_IMAGE`; the
frontend service uses `CHARGEPILOT_FRONTEND_IMAGE`. If either setting is
omitted, Compose builds that service's local image. PostgreSQL and Kafka are
separate services. Only API port `8000` and frontend port `5173` are
published. The Compose Kafka broker is single-node development infrastructure,
not a production cluster.

### Update an installation

1. Back up PostgreSQL before applying an update. Keep the existing project and
   its `.env`.
2. Set `CHARGEPILOT_API_IMAGE` and `CHARGEPILOT_FRONTEND_IMAGE` to the
   digests reported by the successful workflow run for the same commit. The
   deployment is deliberately pinned and will not silently move to newer
   images.
3. From the directory containing the Compose file and `.env`, run:

   ```powershell
   docker compose pull app frontend outbox-relay automation-worker
   docker compose up -d --no-build
   docker compose ps
   docker compose logs --tail 100 app frontend outbox-relay automation-worker
   ```

4. Confirm API and workers are running, `/ready` succeeds at
   `http://localhost:8000/ready`, and the frontend loads at
   `http://localhost:5173`.

Do not use `docker compose down -v` when updating: `-v` removes the database
volume and permanently deletes stored ChargePilot data. A normal `docker
compose down` does not remove the volume, but is not required for routine
updates.

### Pin or roll back an image

To pin an installation, set both image variables in `.env` to their digests
from the same workflow run, then pull and recreate the API, frontend, and
worker services. To roll back, restore the previous pair of image digests and
repeat those commands. Keep a database backup: rolling back container images
does not reverse database changes.

## Upgrade and security notes

- The project does not currently have versioned Alembic migrations.
  `create_all()` and startup compatibility adjustments are not a general schema
  migration system. Review release notes for database changes before updating
  an existing installation; back up first and plan any required migration.
- PostgreSQL and Kafka data are stored in named volumes. Preserve these
  volumes during routine updates; do not run `docker compose down -v`.
- Keep `.env`, backups, and Docker Hub access tokens private. Do not post the
  output of `docker compose config`, which may include expanded secrets.
- Workflow runs publish immutable commit tags and report digests suitable for
  reproducible deployment. Keep the digest with the release record for
  controlled rollouts and rollback.
