# macOS Agent TLD

## 1. Tech stack

- Swift
- SwiftUI
- Apple power-source APIs
- URLSession for HTTPS uploads
- Keychain for the per-install credential and local identity

## 2. Current implementation

`agent/macos` is a foreground Swift CLI. It contains command parsing,
one-time enrollment exchange, local configuration storage, Keychain
credential storage, Apple power-source collection, and HTTPS upload. It
reports immediately and then every five minutes while running. It does not
install a login item and has no graphical status UI.

## 3. Power-source integration

Use public Apple APIs to read battery percentage and charging/power-source
state. Treat health or battery-condition values as optional. Do not collect
serial numbers or assume the API always supplies health metrics.

## 4. Upload flow

- collect telemetry snapshot
- attach the enrolled per-install credential
- send the platform payload to the deployed `/api/v1/telemetry` endpoint
- handle HTTP success, schema/auth rejection, and network retry states
- report the last upload result to the foreground terminal

## 5. Operational notes

- a signed, notarized menu-bar/login-item app remains recommended future work
- running while sleeping is not guaranteed; do not claim a reliable wake-up or background sampling contract
- the CLI should degrade gracefully when offline or when enrollment is revoked
