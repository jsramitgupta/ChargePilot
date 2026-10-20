# Platform Agent Streams

This directory tracks ChargePilot's cross-platform telemetry work. The platform-aware backend contract, Windows PowerShell enrollment, a
foreground Swift macOS CLI, and Kotlin/Compose Android and SwiftUI iOS source
projects are implemented. Existing Windows agents remain compatible with the
shared-token flow. The Android and iOS source projects still require native
build and physical-device validation; signed mobile releases are not shipped.

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
- New Windows installs use the universal tenant-bound enrollment token and
  per-install credential; existing Windows installs can retain the
  `hardware_uuid`/shared-token flow during migration.
- An installation UUID is not hardware identity. Do not collect serials,
  IMEI, Wi-Fi identifiers, or location.
- mobile agents must treat background reporting as best-effort and not as guaranteed real-time automation

## Platform streams

- [macos](./macos/README.md) — implemented Swift foreground CLI; signed
  login-item/menu-bar distribution remains future work
- [android](./android/README.md) — Kotlin/Compose source project; WorkManager
  reporting is best-effort and device validation remains
- [ios](./ios/README.md) — SwiftUI source project; foreground and Shortcuts
  reporting, with no guaranteed unattended automation

## Shared server-side recommendations

See [SERVER_SIDE_CONFIG.md](./SERVER_SIDE_CONFIG.md) for the live
enrollment/telemetry contract and remaining rollout work. The authoritative API
reference is [API_SPEC.md](../API_SPEC.md).

## Execution policy for downstream AI work

Complete Android and iOS native builds, acceptance tests, physical-device
validation, and distribution plans. Coordinate against the shared API
contract; source projects do not mean signed mobile releases are available.
Keep new endpoint automation disabled until explicit server-authorized opt-in,
and do not ship local Tuya control in an endpoint agent.
