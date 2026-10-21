# Android Agent PRD

## 1. Product goal

Create a native Android battery telemetry app for ChargePilot using the
platform-aware API and per-install enrollment flow. Kotlin/Compose source is
implemented in `agent/android`; a debug APK has been built and smoke-tested on
an emulator. Physical-device validation and a signed release are still
required before distribution. Background reporting is best-effort.

## 2. User value

- enables ChargePilot to include Android devices as best-effort telemetry sources
- keeps device control within the server and connector model
- creates a clear operational distinction between real-time automation and opportunistic reporting

## 3. Functional requirements

- read battery percentage and charging state from Android system APIs
- upload through the per-install credential flow; do not embed the
  current tenant-wide bearer token in a distributed APK
- use a random installation ID, not IMEI or another hardware identifier
- schedule periodic uploads with WorkManager or equivalent background framework
- provide a user-visible status for the last telemetry upload and freshness

## 4. Non-functional requirements

- must not perform switching or direct control actions
- must handle Doze and OS-initiated background delays gracefully
- must store tokens securely and avoid exposing credentials in logs
- must document the best-effort nature of uploads in-app and to operators

## 5. Success criteria

- the app uploads only after Android is enabled in server configuration and
  the user completes enrollment
- existing Windows telemetry and tenant isolation remain unchanged
- quality and freshness warnings appear when uploads are delayed or context is degraded
- the app can recover from failed uploads and restarts using its installation
  ID; a reinstall/re-enrollment creates an explicit new identity
