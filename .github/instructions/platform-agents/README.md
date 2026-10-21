# Platform Agent Streams

This directory tracks ChargePilot's cross-platform telemetry work. The
platform-aware backend contract, a .NET Windows service with an elevated
configuration UI and CLI, a SwiftUI
macOS menu-bar app with CLI diagnostics, and Kotlin/Compose Android and SwiftUI
iOS clients are implemented. Existing Windows agents remain compatible with
the shared-token flow. GitHub Releases publish an Android debug APK, an
unsigned iOS IPA, and an unsigned, unnotarized macOS DMG with platform source
archives. Android has an emulator smoke test; iOS has a simulator smoke test.
Physical-device validation and signed store distribution remain pending.
The self-contained Windows executable is built on a Windows GitHub Actions
runner (or cross-published from macOS with .NET 10). The PowerShell bootstrap
downloads and opens its setup UI; new installations run as a Windows service,
not a scheduled task. Existing user-scoped enrollment is migrated during
elevated setup, and the old scheduled task is removed after service startup.
The service stores its per-install credential using machine-scoped DPAPI in a
SYSTEM/Administrators-only ProgramData directory. The .NET contract tests run
on macOS; Windows service runtime validation still requires Windows.

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
contract; published development builds are not signed store releases. New
endpoint automation is enabled by default across all four platforms, with
freshness, platform allow-list, tenant, and mapping checks enforced by the
server. Do not ship local Tuya control in an endpoint agent.
