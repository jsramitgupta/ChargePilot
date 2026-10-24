# ChargePilot documentation site

The public help site is a separate application from the ChargePilot console:

- `web/` is a Next.js server-rendered documentation frontend.
- `cms/` is Strapi, which stores and publishes the task-based guides.
- `cms/release-notes/` contains the user-facing notes required for each
  `agents-vMAJOR.MINOR.PATCH` release.
- `deploy/k3s/docs.yaml` runs the web app, CMS, and private PostgreSQL in the
  `chargepilot-docs` namespace.

The requested public address is
`https://docs-chargepilot.endusercompute.in`. The checked-in Istio route
serves the web app at `/` and Strapi's read-only public API at `/api`.
Strapi's admin and database are not published outside the cluster. DNS and
public TLS termination are managed outside this repository and must route
this hostname to the existing ingress.

## Local development

Use Node.js 24.22.1 and npm. Create a local environment file and replace every
placeholder with a random value; never use development values in production:

```sh
cp docs-site/.env.example docs-site/.env
```

Start the isolated local PostgreSQL service:

```sh
docker compose --env-file docs-site/.env -f docs-site/compose.yaml up -d database
```

In one terminal, start Strapi:

```sh
set -a
. docs-site/.env
set +a
npm ci --prefix docs-site/cms
npm run develop --prefix docs-site/cms
```

Create the first Strapi administrator at `http://localhost:1337/admin`. In
another terminal, start Next.js:

```sh
CMS_API_URL=http://localhost:1337/api/public/guides \
  npm ci --prefix docs-site/web
CMS_API_URL=http://localhost:1337/api/public/guides \
  npm run dev --prefix docs-site/web
```

For the deployed CMS, use an authorized Kubernetes port-forward to reach
`/admin`; do not expose the admin or first-user setup route on the public
documentation hostname.

The first Strapi start seeds the starter guides. Edit and publish them in
Strapi; the Next.js site refreshes published content within 60 seconds. The
public API exposes only published guide summaries and bodies. Create content
in the Strapi admin; do not add mock or fallback guide data to the Next.js app.

## Writing and release updates

Write for the person's task, not the internal service implementation. Use
plain language, short steps, and separate administrator-only actions from
standard user tasks. Verify every instruction against the current console,
agent setup page, [API contract](../.github/instructions/API_SPEC.md), and
current-state reference before publishing it.

For every agent release, add
`cms/release-notes/agents-vMAJOR.MINOR.PATCH.md` before creating its Git tag.
The release workflow blocks a tag when its matching note is missing or lacks
a title and useful summary. The CMS image seeds these versioned notes into
Strapi and updates them from the source file on rollout. Update an existing
procedural guide in Strapi when product behavior changes; avoid putting
credentials, device local keys, personal data, or unsupported claims in
content.

## Checks

```sh
npm ci --prefix docs-site/web
npm run lint --prefix docs-site/web
npm run build --prefix docs-site/web

npm ci --prefix docs-site/cms
npm audit --prefix docs-site/cms --omit=dev --audit-level=high
APP_KEYS=ci-one,ci-two,ci-three,ci-four \
ADMIN_JWT_SECRET=ci-admin-secret-not-used-at-runtime \
API_TOKEN_SALT=ci-api-salt-not-used-at-runtime \
TRANSFER_TOKEN_SALT=ci-transfer-salt-not-used-at-runtime \
ENCRYPTION_KEY=ci-encryption-key-not-used-at-runtime \
npm run build --prefix docs-site/cms
```

The GitHub workflow builds and scans both images, updates only their immutable
source-SHA tags in the Argo CD Kustomize manifest, and lets Argo CD reconcile
the namespace. Do not deploy by applying manifests or changing live images
manually.
