# Docker Hub publishing and deployment

This guide covers publishing ChargePilot images from GitHub Actions and using
those images for a fresh Docker Compose deployment or an existing installation.
The workflow builds `linux/amd64` and `linux/arm64` images and publishes them to
`<Docker-Hub-username>/chargepilot`.

## Publish an image (maintainers)

### One-time setup

1. Create the `chargepilot` repository under the Docker Hub account or
   organization that will own the image.
2. Create a Docker Hub access token with permission to push to that repository.
3. In the GitHub repository, open **Settings → Secrets and variables → Actions**
   and add these repository secrets:
   - `DOCKERHUB_USERNAME`: the Docker Hub username or organization name.
   - `DOCKERHUB_TOKEN`: the access token created above (not the Docker Hub
     account password).
4. Confirm the GitHub Actions workflow is enabled.

### Publish a release

The workflow in `.github/workflows/docker-multiarch.yml` runs after a push to
`main`, or can be started manually from **Actions → Build and Push Docker Image
to Docker Hub → Run workflow**. For a manual run, select the intended branch.

Each successful run publishes two tags:

- `latest` — updated to the image from the newest successful run.
- A timestamp tag in `DDMMYYYY.HHmmss` format — a fixed version useful for
  pinning or rollback.

The workflow builds from `docker/Dockerfile` and publishes a multi-platform
manifest. Confirm the Actions run succeeds, then check the tags and platforms
on the Docker Hub repository page. Do not put Docker Hub credentials in the
workflow file or commit them to the repository.

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
updating the app. Add the published Docker Hub image under `CHARGEPILOT_IMAGE`,
replacing `endusercompute` with the publisher's account or organization:

```env
CHARGEPILOT_IMAGE=endusercompute/chargepilot:latest
```

Generate candidate secret values with Python, then copy them into the matching
fields in `.env`:

```powershell
python -c "import secrets; print('CHARGEPILOT_SECRET_KEY=' + secrets.token_urlsafe(32)); print('CHARGEPILOT_ENCRYPTION_KEY=' + secrets.token_urlsafe(32)); print('CHARGEPILOT_POSTGRES_PASSWORD=' + secrets.token_urlsafe(32)); print('CHARGEPILOT_ADMIN_PASSWORD=' + secrets.token_urlsafe(24))"
```

Set `CHARGEPILOT_ADMIN_USERNAME` to the desired initial administrator name.
Retain the secret and database values for subsequent restarts and upgrades.

For a private Docker Hub repository, sign in first with `docker login` using an
account that can pull the image. Validate the Compose configuration and start
the stack:

```powershell
docker compose config
docker compose pull app
docker compose up -d --no-build
docker compose ps
```

The Compose file uses the published image when `CHARGEPILOT_IMAGE` is set; if
it is omitted, it retains the local source-build behavior and uses
`chargepilot:local`. The published images support 64-bit x86 and ARM Linux.
The application listens on port `8000` by default.

### Update an existing installation

1. Back up the PostgreSQL database before applying an update. Keep the same
   `.env` file and Docker Compose project so the existing `postgres-data`
   volume is reused.
2. Leave `CHARGEPILOT_IMAGE` set to `.../chargepilot:latest` for automatic
   latest-version updates, or set it to a specific timestamp tag to control
   which release is installed.
3. From the directory containing the Compose file and `.env`, run:

   ```powershell
   docker compose pull app
   docker compose up -d --no-build
   docker compose ps
   docker compose logs --tail 100 app
   ```

4. Confirm both services are running and the readiness check succeeds at
   `http://localhost:8000/ready`.

Do not use `docker compose down -v` when updating: `-v` removes the database
volume and permanently deletes stored ChargePilot data. A normal `docker
compose down` does not remove the volume, but is not required for routine
updates.

### Pin or roll back an image

To pin a deployment, set `CHARGEPILOT_IMAGE` in `.env` to a known timestamp tag,
then run `docker compose pull app` followed by `docker compose up -d --no-build`.
To roll back, change the value to the prior timestamp tag and repeat those
commands. Keep a database backup: rolling back the container image does not
reverse database changes.

## Upgrade and security notes

- The project does not currently have versioned Alembic migrations.
  `create_all()` and startup compatibility adjustments are not a general schema
  migration system. Review release notes for database changes before updating
  an existing installation; back up first and plan any required migration.
- The PostgreSQL data is stored in the named `postgres-data` volume. Do not
  replace it with a new Compose project name or delete it when updating.
- Keep `.env`, backups, and Docker Hub access tokens private. Do not post the
  output of `docker compose config`, which may include expanded secrets.
- The `latest` tag moves with each successful publish. Use a timestamp tag when
  reproducibility or controlled rollouts are required.
