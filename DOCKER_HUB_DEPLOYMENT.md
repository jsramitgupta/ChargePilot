# Docker Hub publishing and deployment

This guide covers publishing ChargePilot images from GitHub Actions, deploying
to k3s with ArgoCD, and using the image in a microservice Compose deployment.
The app and connector images are published to the `endusercompute` Docker Hub
namespace for `linux/amd64` and `linux/arm64`.

## Continuous integration, publishing, and deployment

### One-time setup

1. Create the `chargepilot` and `chargepilot-connector` repositories under the
   `endusercompute` Docker Hub account.
2. Create a Docker Hub access token with permission to push those images.
3. In GitHub **Settings → Secrets and variables → Actions**, add the
   repository secret `DOCKERHUB_TOKEN`. The workflows use username
   `endusercompute`; do not commit the access token.
4. Allow GitHub Actions `GITHUB_TOKEN` **Read and write permissions** so the
   image publisher can commit the ArgoCD tag update to `main`.
5. Confirm GitHub Actions and the ArgoCD controller are enabled.

### Main-branch pipeline

`.github/workflows/ci.yml` runs Python lint/tests and frontend lint/build for
pull requests into `main` and pushes to `main`. A successful main-branch CI run
triggers `.github/workflows/publish-deploy.yml`, which builds the tested source
commit, pushes the multi-platform image, and updates `deploy/k3s/kustomization.yaml`.
ArgoCD tracks the `main` branch and syncs this new immutable tag to k3s. CI
skips commits that only change the generated image tag, preventing a publish
loop.

The app tag format remains `sha-<full-commit-sha>`, as produced by the
previous `type=sha,format=long` configuration. Workflow summaries include the
image digest. The connector workflow separately publishes
`endusercompute/chargepilot-connector:sha-<full-commit-sha>` when connector
files change on `main`.

### First k3s rollout

The k3s manifests are in `deploy/k3s/`; the ArgoCD Application is
`deploy/argocd/chargepilot.yaml`. The deployment uses
`app.endusercompute.in` for the frontend and `api.endusercompute.in` for the
JSON API, Windows agent, and downloads. Before applying the ArgoCD
Application:

1. Merge the CI/CD and deployment changes to `main`, then wait for CI, image
   publish, and the GitOps tag update to succeed.
2. Create the `chargepilot-runtime` Kubernetes Secret from a local, untracked
   `.env.k3s` file. Include the database URL and password, application and
   admin secrets, public browser origins, and Kafka settings. Use the same
   URL-safe PostgreSQL password in both the URL and
   `CHARGEPILOT_POSTGRES_PASSWORD`.
3. Create the `chargepilot-ingress-tls` Secret in `istio-system` with a
   Cloudflare Origin Certificate covering both hostnames. Never commit the
   private key.
4. Apply `deploy/argocd/chargepilot.yaml`; ArgoCD will sync the app and future
   successful main-branch image updates automatically.
5. In Cloudflare, create proxied DNS records for both hostnames to the public
   address that forwards TCP 443 to the Istio ingress gateway, and set
   encryption to **Full (strict)**.

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
updating the app. Pin the published Docker Hub image under `CHARGEPILOT_IMAGE`:

```env
CHARGEPILOT_IMAGE=endusercompute/chargepilot@sha256:<digest-from-workflow-summary>
```

Generate candidate secret values with Python, then copy them into the matching
fields in `.env`:

```powershell
python -c "import secrets; print('CHARGEPILOT_SECRET_KEY=' + secrets.token_urlsafe(32)); print('CHARGEPILOT_ENCRYPTION_KEY=' + secrets.token_urlsafe(32)); print('CHARGEPILOT_POSTGRES_PASSWORD=' + secrets.token_urlsafe(32)); print('CHARGEPILOT_ADMIN_PASSWORD=' + secrets.token_urlsafe(24))"
```

Set `CHARGEPILOT_ADMIN_USERNAME` to the desired initial administrator name.
Retain the secret and database values for subsequent restarts and upgrades.

For a private Docker Hub repository, sign in first with `docker login` using an
account that can pull the image. This architecture change is a breaking
redesign: start with a fresh Compose project/database and do not reuse an
earlier ChargePilot PostgreSQL volume. Retain the old deployment until the
new stack has been validated and explicitly decide how to retire its data.
Validate the Compose configuration and start the new project:

```powershell
docker compose config
docker compose -p chargepilot-v2 pull app outbox-relay automation-worker
docker compose -p chargepilot-v2 up -d --no-build
docker compose -p chargepilot-v2 ps
```

The API, outbox-relay, and automation-worker use the published ChargePilot
image when `CHARGEPILOT_IMAGE` is set; Kafka and PostgreSQL are separate
services. If the image setting is omitted, the stack builds `chargepilot:local`.
Only API ports `8000` and `5173` are published. The Compose Kafka broker is
single-node development infrastructure, not a production cluster.

### Update a v2 installation

1. Back up the v2 PostgreSQL database before applying an update. Keep the
   `chargepilot-v2` project and its `.env`.
2. To upgrade, replace `CHARGEPILOT_IMAGE` with the digest reported by the
   successful workflow run for the intended commit. The Compose deployment is
   deliberately pinned and will not silently move to a newer image.
3. From the directory containing the Compose file and `.env`, run:

   ```powershell
   docker compose -p chargepilot-v2 pull app outbox-relay automation-worker
   docker compose -p chargepilot-v2 up -d --no-build
   docker compose -p chargepilot-v2 ps
   docker compose -p chargepilot-v2 logs --tail 100 app outbox-relay automation-worker
   ```

4. Confirm API and workers are running and the readiness check succeeds at
   `http://localhost:8000/ready`.

Do not use `docker compose down -v` when updating: `-v` removes the database
volume and permanently deletes stored ChargePilot data. A normal `docker
compose down` does not remove the volume, but is not required for routine
updates.

### Pin or roll back an image

To pin a v2 deployment, set `CHARGEPILOT_IMAGE` in `.env` to the image digest
reported by the workflow, then pull and recreate the API and worker services
with the same project name. To roll back, restore the previous digest
and repeat those commands. Keep a database backup: rolling back the container
image does not reverse database changes.

## Upgrade and security notes

- The project does not currently have versioned Alembic migrations.
  `create_all()` and startup compatibility adjustments are not a general schema
  migration system. Review release notes for database changes before updating
  an existing installation; back up first and plan any required migration.
- PostgreSQL and Kafka data are stored in named volumes. Do not reuse an older
  ChargePilot deployment's PostgreSQL volume for this breaking redesign.
- Keep `.env`, backups, and Docker Hub access tokens private. Do not post the
  output of `docker compose config`, which may include expanded secrets.
- Workflow runs publish immutable commit tags and report a digest suitable for
  reproducible deployment. Keep the digest with the release record for
  controlled rollouts and rollback.
