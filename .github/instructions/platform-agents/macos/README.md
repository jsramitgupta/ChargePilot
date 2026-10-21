# macOS Agent

The macOS client in `agent/macos` is a SwiftUI menu-bar app with CLI
diagnostics. It uses the platform-aware backend contract, reusable
tenant-scoped 24-hour enrollment tokens, and a per-install Keychain credential.

## Scope

- collect battery percentage, charging state, AC connection, and availability status
- identify the endpoint using a random per-installation UUID; do not collect a
  serial number
- upload through the current ChargePilot telemetry contract
- report every five minutes while the menu-bar app is running and the Mac is
  awake
- optionally launch in the user's session at sign-in through macOS
  `SMAppService.mainApp`

## Primary documents

- [PRD.md](./PRD.md)
- [ARCHITECTURE.md](./ARCHITECTURE.md)
- [TLD.md](./TLD.md)

## Non-goals

- no direct switch-control logic inside the app
- no bypass of backend rule evaluation
- no promise of telemetry while the Mac is sleeping, powered off, or the agent is disabled

## Implementation approach

The menu-bar app and CLI are documented in
[agent/macos/README.md](../../../../agent/macos/README.md). The app persists
the installation ID locally and the credential in Keychain, reports
immediately and every five minutes while running, and lets users enable a
login item. Never embed or use the tenant-wide Windows token. The development
DMG remains unsigned and not notarized.

## Known constraints

- macOS telemetry is available from public power-source APIs, but sleep and power-off states create natural gaps
- the app must not claim to be a real-time automation agent
- report success and failure visibly in the menu-bar UI without exposing
  credentials

## Platform references

- [IOPowerSources API headers](https://github.com/apple-oss-distributions/IOKitUser/blob/323ead896d04424f87184d8f6ff0cce811aab106/ps.subproj/IOPowerSources.h)
- [IOPS power-source keys](https://github.com/apple-oss-distributions/IOKitUser/blob/323ead896d04424f87184d8f6ff0cce811aab106/ps.subproj/IOPSKeys.h)
- [SMAppService login items](https://developer.apple.com/documentation/servicemanagement/smappservice)
- [Apple notarization guidance](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution)

Recheck the supported APIs and distribution requirements when adding an
automatically launched or signed distribution path.

## Handoff checklist

The implementation agent should verify:

1. verify the app reads power-source data through supported Apple APIs on a
   macOS 13+ build host and handles unavailable readings without sending
   synthetic values
2. verify the installation ID persists across restarts without hardware
   serials
3. verify credentials are stored in Keychain and can be revoked server-side
4. test the payload against the deployed API and the one-use enrollment flow
5. verify the backend freshness gate prevents delayed samples from automating
6. add acceptance tests for sleep, logout, token revocation, and network loss
   before shipping a background/login-item client
