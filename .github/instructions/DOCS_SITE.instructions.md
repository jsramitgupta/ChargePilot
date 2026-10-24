---
name: ChargePilot documentation site
description: "Use when changing docs-site, documentation content, Strapi, the Next.js help site, or its Kubernetes and release workflows."
applyTo: "docs-site/**"
---

# ChargePilot documentation site

- Keep the Next.js documentation site separate from the React management
  console. Read [the site reference](./DOCS_SITE.md) before changing its
  content model, public API, deployment, or release behavior.
- Write task-based instructions for tenant administrators/managers and users.
  Verify workflow names and capabilities against the current product UI and
  `.github/instructions/CURRENT_STATE.md`; do not document proposals as shipped.
- Keep battery hysteresis, cooldown, tenant checks, and command routing
  server-authoritative. Do not suggest that the browser, agent, or docs site
  can override automation decisions.
- SmartLife local keys are for matching only. Take device identity, address,
  and protocol metadata from LAN discovery or explicit manual entry.
- Publish only guide records explicitly marked published. The public Strapi
  endpoints are read-only; keep all write and admin operations authenticated.
- Do not add placeholder content, success-shaped fallbacks, credentials,
  device local keys, enrollment tokens, or customer data to published docs.
- When user-visible product behavior changes, update the relevant guide and
  release notes before the release tag. `agents-v*` tags must have a matching
  `cms/release-notes/agents-vMAJOR.MINOR.PATCH.md` file.
- Run `npm run lint --prefix docs-site/web`, `npm run build --prefix
  docs-site/web`, and `npm run build --prefix docs-site/cms` after relevant
  changes. Use disposable local credentials for builds only.
