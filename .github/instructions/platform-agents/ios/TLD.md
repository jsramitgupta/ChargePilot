# iOS Agent TLD

## 1. Tech stack

- Swift
- SwiftUI
- `UIDevice` battery API
- URLSession
- Keychain for the per-install credential and installation ID
- background task support only where permitted by Apple

## 2. Modules

- app bootstrap
- battery status collector
- endpoint identity manager
- HTTPS uploader
- error and freshness management
- status UI

## 3. Battery integration

Use the public battery APIs to read level and charging state. Do not assume broad health metadata is available; treat it as optional and avoid using unsupported APIs.

## 4. Upload flow

- read battery data when the app is active or a user triggers a sync
- attach the per-install credential and platform metadata
- send through the platform-aware schema after iOS enrollment is enabled;
  optional AC/IP fields can be omitted when unavailable
- persist the last successful upload and the current freshness state
- retry delivery only within a bounded freshness window; never replay an old
  sample as a current reading or claim guaranteed timing

## 5. Operational notes

- the app should be launchable and useful even when background delivery is unavailable
- the UI should display stale state clearly to users and operators
- iOS telemetry is informational and telemetry-only by default, not a
  replacement for a continuously reporting endpoint or an automation trigger
