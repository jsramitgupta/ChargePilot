# ChargePilot documentation site

## Purpose and boundary

The public help site serves task-based guidance for ChargePilot tenant
administrators, managers, and users. It is not a second management console.
The main product remains the authenticated React app and FastAPI JSON API.

## Runtime

- `docs-site/web` is a Next.js server-rendered frontend.
- `docs-site/cms` is the Strapi content management system.
- Strapi stores guides in its own PostgreSQL database and seeds starter guides
  when the content collection is empty.
- Next.js reads only the Strapi read-only public guide endpoints. Published
  edits are reflected within 60 seconds; draft content stays out of public
  pages.
- Strapi administrator access is internal-only at `/admin`; reach it through
  an authorized Kubernetes port-forward. The CMS and PostgreSQL services are
  ClusterIP-only. The public Strapi API has two GET-only custom routes for
  published guide data. No public content write route is enabled.
- `deploy/k3s/docs.yaml` places the web app, CMS, and a dedicated PostgreSQL
  StatefulSet in `chargepilot-docs`. The deployment has bounded resources,
  non-root app containers, read-only root filesystems, and persistent CMS
  storage. The Postgres PVC is node-local and must be backed up independently.

## Content ownership

Strapi is authoritative for editable how-to guides. The CMS startup seed
creates initial user and administrator guides only when a guide does not
already exist. It does not overwrite edited how-to content.

Versioned `agents-v*` release notes are source-controlled under
`docs-site/cms/release-notes/`. The release workflow requires a matching
`agents-vMAJOR.MINOR.PATCH.md` file with a heading and useful summary. Strapi
loads these notes and synchronizes them from their source files on startup,
so a release image update publishes the versioned notes alongside the guides.
The release-note template is
[`agents-vMAJOR.MINOR.PATCH.md.example`](../../docs-site/cms/release-notes/agents-vMAJOR.MINOR.PATCH.md.example).

When user-visible behavior changes, update the task guide in Strapi and
include a relevant note before creating the release tag. Include the required
follow-up/action, affected platform, and any limitation. Run the
[`docs-content-maintenance` skill](../skills/docs-content-maintenance/SKILL.md)
for the full content review workflow.

## Release and deployment

GitHub Actions runs the docs frontend lint/build and CMS build in CI. CI also
blocks CMS releases when production dependencies have high or critical npm
advisories. A successful `main` CI run triggers image build and scan for changed
docs components; the existing publisher writes immutable source-SHA tags to
`deploy/k3s/kustomization.yaml`. Argo CD then reconciles the desired state. Do
not apply manifests or change image tags directly on the shared cluster.

Before the first deployment:

1. Provision `docs-runtime` in `chargepilot-docs` out of band with PostgreSQL
   credentials and fresh Strapi signing/encryption secrets. It must include
   `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `DATABASE_PASSWORD`,
   `APP_KEYS`, `ADMIN_JWT_SECRET`, `API_TOKEN_SALT`, `TRANSFER_TOKEN_SALT`,
   `ENCRYPTION_KEY`, and `JWT_SECRET`. Use the same random database password
   for `POSTGRES_PASSWORD` and `DATABASE_PASSWORD`. Do not commit the Secret or
   place values in CI logs.
2. Confirm independent backup and restore for the docs PostgreSQL PVC.
3. Confirm DNS and the external TLS/edge proxy route
   `docs-chargepilot.endusercompute.in` to the existing Istio ingress.
4. Let the documented main-branch CI and GitOps workflow publish and reconcile
   the images.
5. Create the first Strapi administrator through a trusted port-forward, not
   the public documentation hostname. Verify that unauthenticated write
   requests are denied.

The Strapi dependency audit must remain clean of critical/high findings before
images are published. Do not bypass the existing container vulnerability
scans to force deployment.
