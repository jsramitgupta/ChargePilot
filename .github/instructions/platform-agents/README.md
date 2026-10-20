# Platform Agent Streams

This directory tracks ChargePilot's cross-platform telemetry work. The
platform-aware backend contract and a foreground Swift macOS CLI are
implemented. Windows remains supported through the existing PowerShell agent.
Android and iOS native clients are planned and gated from enrollment by server
configuration until their implementations are validated.

## Objectives

- Keep the ChargePilot backend as the authority for automation and device control.
- Preserve existing Windows telemetry ingestion, tenant boundaries, outbox
  processing, and site-connector architecture.
- Provide platform-specific PRD, architecture, and technical design documents.
- Keep the implemented server contract, configuration, migration, and
  remaining client work documented accurately.

## Shared backend constraints

The existing backend contract is described in:

- [../CURRENT_STATE.md](../CURRENT_STATE.md)
- [../ARCHITECTURE.md](../ARCHITECTURE.md)
- [../API_SPEC.md](../API_SPEC.md)
- [../CLOUD_CONNECTOR_ARCHITECTURE.md](../CLOUD_CONNECTOR_ARCHITECTURE.md)
- [../DEPLOYMENT.md](../DEPLOYMENT.md)

Key rules to preserve:

- endpoint control remains server-authoritative and site-connector-driven
- telemetry agents send readings only; they do not issue switch commands
- tenant boundaries and bearer-token assignment remain enforced by the server
- Windows can retain its existing tenant-token and `hardware_uuid` flow;
  enrolled clients must use the new tenant-bound per-install credential.
- An installation UUID is not hardware identity. Do not collect serials,
  IMEI, Wi-Fi identifiers, or location.
- mobile agents must treat background reporting as best-effort and not as guaranteed real-time automation

## Platform streams

- [macos](./macos/README.md) — implemented Swift foreground CLI; signed
  login-item/menu-bar distribution remains future work
- [android](./android/README.md) — useful best-effort battery telemetry with WorkManager scheduling
- [ios](./ios/README.md) — foreground-first reporting; no guaranteed unattended automation

## Shared server-side recommendations

See [SERVER_SIDE_CONFIG.md](./SERVER_SIDE_CONFIG.md) for the live
enrollment/telemetry contract and remaining rollout work. The authoritative API
reference is [API_SPEC.md](../API_SPEC.md).

## Execution policy for downstream AI work

Build Android and iOS as separate projects/tasks with native acceptance tests
and distribution plans. Coordinate against the shared API contract; their
platforms remain disabled until a client is ready. Keep new endpoint
automation disabled until explicit server-authorized opt-in, and do not ship
local Tuya control in an endpoint agent.
