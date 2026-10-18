# ChargePilot coding instructions

Before changing code, read `.github/instructions/CURRENT_STATE.md` and consult
the relevant architecture, API, and deployment references in
`.github/instructions/`. Keep those documents aligned with implemented
behavior.

## Preserve product behavior

- ChargePilot is a local-first battery automation platform. Keep battery
  hysteresis/cooldown rules authoritative on the backend, preserve tenant
  boundaries, and route cloud-hosted Tuya operations through the assigned
  site connector.
- SmartLife pairing returns local keys for matching only. Device identity,
  address, and protocol metadata must come from LAN discovery or explicit
  manual entry.
- Extend the existing FastAPI/SQLAlchemy backend and React/TypeScript/Tailwind
  frontend. React is the only browser UI; implement JSON API operations for
  user-facing workflows.
- Preserve ChargePilot's local-first behavior, responsive layout, light/dark
  theme parity, and left-aligned authenticated navigation. Do not introduce
  mock data or dead-end controls.
- Treat `.github/instructions/FRONTEND_DESIGN.md` as the canonical reference
  for frontend routes, typography, design decisions, and light/dark theme
  behavior; keep it aligned when changing the UI.

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
  need backup and a reviewed upgrade path.

## Tests and delivery

- Pytest must use the isolated SQLite database configured unconditionally in
  `tests/conftest.py`, before application imports. Never allow tests to inherit
  a developer or production database URL.
- For code changes, run the smallest relevant tests plus Python lint and the
  frontend TypeScript build/lint when applicable. Report actual results and
  deployment limitations accurately.
- Prefer direct, actionable guidance and safe copy/paste commands when helping
  operate or diagnose the deployment.
