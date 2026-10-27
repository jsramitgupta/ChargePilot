# Platform Agent Streams

This directory tracks ChargePilot's cross-platform telemetry work. The
platform-aware backend contract, a .NET Windows service with an elevated
configuration UI and CLI, a SwiftUI macOS menu-bar app with CLI diagnostics,
and Kotlin/Compose Android and SwiftUI iOS clients are implemented. Existing
Windows agents remain compatible with the shared-token flow. Each enrolled
client supports self-service deregistration and re-enrollment without
reinstallation. Development artifacts remain unsigned or debug-signed as
appropriate. `agents-v*` releases publish all platform builds and source
archives with or without signing secrets. Each platform is signed and verified
when its complete signing-secret group is present; otherwise the release
identifies it as unsigned. A partially configured group fails that platform
job. Android has an emulator smoke test; iOS has a simulator smoke test.
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
- endpoint agents never control Tuya switches. Enrolled Windows/macOS agents
  can receive only the fixed, user-opted-in shutdown request after the mapped
  switch is confirmed off; Windows has a local cancellation countdown and
  macOS requires local confirmation. They can also claim tenant-scoped fixed
  read-only sensors from Smart Groups. No uploaded script or arbitrary shell
  payload is executed. Windows sensors run in its service; macOS sensors
  require the app/CLI process to run in a signed-in user session.
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
  login item; self-service deregistration; release DMG may be unsigned or
  signed and notarized
- [android](./android/README.md) — Kotlin/Compose source project; WorkManager
  reporting is best-effort; self-service deregistration; release APK may be
  unsigned or signed with the configured release key
- [ios](./ios/README.md) — SwiftUI source project; foreground and Shortcuts
  reporting and self-service deregistration; release IPA may be unsigned or
  ad-hoc signed for provisioned devices; no guaranteed unattended automation
- [windows](../../agent/windows/README.md) — .NET Windows service, elevated
  setup UI/CLI, self-service deregistration, and optionally Authenticode-signed
  releases

## Shared server-side recommendations

See [SERVER_SIDE_CONFIG.md](./SERVER_SIDE_CONFIG.md) for the live
enrollment/telemetry contract and remaining rollout work. The authoritative API
reference is [API_SPEC.md](../API_SPEC.md).

## Execution policy for downstream AI work

The endpoint-agent workflow builds development artifacts for source changes
and publishes releases on `agents-v*` tags with or without signing
credentials. Continue Android/iOS acceptance testing and physical-device
validation. A signed iOS release is ad-hoc provisioned for included devices
and is not an App Store release. Coordinate against the shared API contract. New
endpoint automation is enabled by default across all four platforms, with
freshness, platform allow-list, tenant, and mapping checks enforced by the
server. Do not ship local Tuya control in an endpoint agent.
