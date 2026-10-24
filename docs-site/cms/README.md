# ChargePilot documentation CMS

This Strapi application stores the published help guides rendered by
`docs-site/web`. Its custom public API exposes only published guide summaries
and article bodies. Content editing and administrator setup stay on the
internal Strapi admin route.

## Local development

Use Node.js 24.22.1 and npm. Start the PostgreSQL service and configure the
values from `docs-site/cms/.env.example`, then run:

```sh
npm ci
npm run develop
```

The first Strapi start seeds starter guides when the collection is empty. Edit
and publish task-based guides in the Strapi admin. Versioned agent release
notes are synchronized from `release-notes/` when the CMS starts; they do not
overwrite procedural guides.

## Dependency security

The production build uses patched Zod 4 dependency versions. The pinned
`koa-session` compatibility patch in `patches/` updates its option-schema
function declarations for Zod 4; `postinstall` reapplies it after clean
installs. Keep the patch and dependency overrides aligned with their package
versions, and remove them only after the upstream packages support the patched
Zod version directly.

Before publishing, run:

```sh
npm audit --omit=dev --audit-level=high
npm run build
```

Moderate advisories are reported separately; do not bypass high/critical npm
audit or container image scan failures. Review and refresh dependency pins and
patches when upgrading Strapi.
