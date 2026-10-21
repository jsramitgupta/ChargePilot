# macOS Agent TLD

## 1. Tech stack

- Swift
- SwiftUI
- Apple power-source APIs
- URLSession for HTTPS uploads
- Keychain for the per-install credential and local identity

## 2. Current implementation

`agent/macos` contains a SwiftUI menu-bar app and a command-line diagnostic
interface. The app provides server, label, and enrollment-code setup, local
configuration storage, Keychain credential storage, Apple power-source
collection, HTTPS upload, and visible report status. It can register itself
as a per-user login item with `SMAppService.mainApp`. After enrollment, it
reports immediately and then every five minutes while the app is running. The
CLI `check` command reads battery state without enrollment or network access.

## 3. Power-source integration

Use public Apple APIs to read battery percentage and charging/power-source
state. Treat health or battery-condition values as optional. Do not collect
serial numbers or assume the API always supplies health metrics.

## 4. Upload flow

- collect telemetry snapshot
- attach the enrolled per-install credential
- send the platform payload to the deployed `/api/v1/telemetry` endpoint
- handle HTTP success, schema/auth rejection, and network retry states
- show the last upload result in the menu-bar UI or foreground terminal

## 5. Operational notes

- the current development menu-bar app and login-item flow are unsigned and
  unnotarized; signed distribution remains future work
- running while sleeping is not guaranteed; do not claim a reliable wake-up or background sampling contract
- the CLI should degrade gracefully when offline or when enrollment is revoked
