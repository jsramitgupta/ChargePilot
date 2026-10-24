# ChargePilot coding instructions

Before changing code, read `.github/instructions/CURRENT_STATE.md` and the
specific architecture/API/deployment reference for the files being changed.
Use `.github/instructions/README.md` as the index; do not load unrelated
reference documents. Keep implementation docs aligned with shipped behavior
and label proposals as proposals.

## Preserve product behavior

- ChargePilot is a local-first battery automation platform. Keep battery
  hysteresis/cooldown rules authoritative on the backend, preserve tenant
  boundaries, and route cloud-hosted Tuya operations through the assigned
  site connector.
- SmartLife pairing returns local keys for matching only. Device identity,
  address, and protocol metadata must come from LAN discovery or explicit
  manual entry.
- Extend the existing FastAPI/SQLAlchemy backend and React/TypeScript/Tailwind
  management console. The separate Next.js/Strapi app in `docs-site/` is only
  for public documentation; implement JSON API operations for product workflows.
- Preserve ChargePilot's local-first behavior, responsive layout, light/dark
  theme parity, and left-aligned authenticated navigation. Do not introduce
  mock data or dead-end controls.
- Treat `.github/instructions/FRONTEND_DESIGN.md` as the canonical reference
  for frontend routes, typography, design decisions, and light/dark theme
  behavior; keep it aligned when changing the UI.
- Windows PowerShell, macOS SwiftUI, Android Kotlin, and iOS SwiftUI telemetry
  clients use the live platform-aware enrollment contract. Their validation
  and distribution maturity differs; see `.github/instructions/CURRENT_STATE.md`
  and `.github/instructions/platform-agents/`. Never use the legacy
  tenant-wide Windows token as a per-device mobile credential. Keep automation
  server-authoritative: automation is enabled by default for all four
  platforms, subject to
  `CHARGEPILOT_TELEMETRY_AUTOMATION_ENABLED_PLATFORMS`, tenant-safe enabled
  mappings, and a fresh report. Mobile reporting and OS background scheduling
  are best-effort.

## Deployment and secrets

- Keep PostgreSQL private. In one Compose project, use the `db` service DNS
  name on port `5432`; for separate Portainer stacks, explicitly attach both
  services to the same external user-defined network and give PostgreSQL the
  `db` alias. Never hardcode container IPs or publish the database port merely
  to solve app connectivity.
- Runtime API/frontend URLs are public browser origins, not Docker service
  names. Keep credentials out of frontend configuration, logs, and diagnostic
  output.
- Preserve `CHARGEPILOT_ENCRYPTION_KEY`; changing it makes stored device local
  keys unreadable.
- Database schema setup currently uses `create_all()` and compatibility SQL,
  not versioned Alembic revisions. Treat schema changes as migrations that
  need backup and a reviewed upgrade/rollback path; do not rely on startup
  `create_all()` to upgrade an existing production schema.
- For user-authorized Linux, Docker, or k3s validation, see the remote host and
  safety scope documented in `.github/instructions/DEPLOYMENT.md`. Use existing
  SSH credentials only; validation permission does not authorize deployment
  mutations or secret disclosure.
- For repeatable local-development or integration checks against the authorized
  k3s host, follow `.github/skills/k3s-validation/SKILL.md`. Treat the deployed
  cluster as shared infrastructure, and use the CI/GitOps publishing path for
  requested updates rather than manually changing images.

## Tests and delivery

- Pytest must use the isolated SQLite database configured unconditionally in
  `tests/conftest.py`, before application imports. Never allow tests to inherit
  a developer or production database URL.
- For code changes, run the smallest relevant tests plus Python lint and the
  frontend TypeScript build/lint when applicable. Report actual results and
  deployment limitations accurately.
- Prefer direct, actionable guidance and safe copy/paste commands when helping
  operate or diagnose the deployment.
