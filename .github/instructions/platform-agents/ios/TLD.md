# iOS Agent TLD

## 1. Tech stack

- Swift
- SwiftUI
- `UIDevice` battery API
- URLSession
- Keychain for the per-install credential and installation ID
- App Intents/Shortcuts for user-configured battery and charger triggers

## 2. Modules

- app bootstrap
- battery status collector
- endpoint identity manager
- HTTPS uploader
- Shortcuts reporting intent
- error and freshness management
- status UI

## 3. Battery integration

Use the public battery APIs to read level and charging state. Do not assume broad health metadata is available; treat it as optional and avoid using unsupported APIs.

## 4. Upload flow

- read battery data when the app is active, a user triggers a sync, or a
  Shortcuts automation invokes the reporting intent
- attach the per-install credential and platform metadata
- send through the platform-aware schema after iOS enrollment is enabled;
  optional AC/IP fields can be omitted when unavailable
- persist the last successful upload and the current freshness state
- use device-only `AfterFirstUnlockThisDeviceOnly` Keychain protection so a
  shortcut can attempt reporting while locked after the first unlock since
  reboot
- retry delivery only within a bounded freshness window; never replay an old
  sample as a current reading or claim guaranteed timing

## 5. Operational notes

- the app should be launchable and useful even when background delivery is unavailable
- the UI should display stale state clearly to users and operators
- iOS telemetry is informational and telemetry-only by default, not a
  replacement for a continuously reporting endpoint or an automation trigger
