# Platform Agent Streams

This directory tracks ChargePilot's cross-platform telemetry work. The
platform-aware backend contract, Windows PowerShell enrollment and an unsigned
Windows executable wrapper, a SwiftUI
macOS menu-bar app with CLI diagnostics, and Kotlin/Compose Android and SwiftUI
iOS clients are implemented. Existing Windows agents remain compatible with
the shared-token flow. GitHub Releases publish an Android debug APK, an
unsigned iOS IPA, and an unsigned, unnotarized macOS DMG with platform source
archives. Android has an emulator smoke test; iOS has a simulator smoke test.
Physical-device validation and signed store distribution remain pending.
The Windows executable is built on a Windows GitHub Actions runner and is
configured by the existing PowerShell installer; it cannot run on macOS.

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
- mobile agents must treat background reporting as best-effort and not as
  guaranteed real-time automation

## Platform streams

- [macos](./macos/README.md) — SwiftUI menu-bar app with optional per-user
  login item; development DMG is unsigned and unnotarized
- [android](./android/README.md) — Kotlin/Compose source project; WorkManager
  reporting is best-effort and device validation remains
- [ios](./ios/README.md) — SwiftUI source project; foreground and Shortcuts
  reporting, with no guaranteed unattended automation

## Shared server-side recommendations

See [SERVER_SIDE_CONFIG.md](./SERVER_SIDE_CONFIG.md) for the live
enrollment/telemetry contract and remaining rollout work. The authoritative API
reference is [API_SPEC.md](../API_SPEC.md).

## Execution policy for downstream AI work

The endpoint-agent workflow builds and publishes agent artifacts on
`agents-v*` tags. Continue Android/iOS acceptance testing, physical-device
validation, and signed distribution. Coordinate against the shared API
contract; published development builds are not signed store releases. Keep
new endpoint automation disabled until explicit server-authorized opt-in, and
do not ship local Tuya control in an endpoint agent.
