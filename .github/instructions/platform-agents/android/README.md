# Android Agent Stream

The native Kotlin/Compose Android telemetry client source project is
implemented in `agent/android`. It uses the platform-aware backend schema and
reusable enrollment flow. It has not yet been built or validated on an Android
device, and no signed APK is distributed.

## Scope

- collect battery level, charging state, AC connection, and app-level telemetry metadata
- use Android battery APIs and WorkManager for best-effort uploads
- use a random installation UUID and the per-install enrollment
  credential; do not collect hardware identifiers
- use the live ChargePilot schema and tenant-scoped enrollment token; Android
  enrollment is enabled by default, subject to server configuration
- show local last-success status; backend reporting dashboards require
  separate server/UI implementation

## Primary documents

- [PRD.md](./PRD.md)
- [ARCHITECTURE.md](./ARCHITECTURE.md)
- [TLD.md](./TLD.md)

## Non-goals

- no direct charging control of the device
- no direct local-network switch control
- no guarantee of exact polling intervals under Doze or background restrictions

## Implementation approach

Build a Kotlin app with `BatteryManager` and WorkManager. WorkManager periodic
work has a 15-minute minimum interval and actual execution may be delayed.
Report when foregrounded, use local persistence for bounded retries, and use
the per-install credential. Do not embed the current tenant-wide agent token.
Server contract and rollout details are in
[../SERVER_SIDE_CONFIG.md](../SERVER_SIDE_CONFIG.md).

## Known constraints

- Android background execution is constrained by work scheduling, Doze, and OS optimization
- the app cannot promise exact automation timing
- local-network access has additional permission and privacy requirements depending on platform policy and target SDK

## Platform references

- [BatteryManager](https://developer.android.com/reference/android/os/BatteryManager)
- [ACTION_BATTERY_CHANGED](https://developer.android.com/reference/android/content/Intent#ACTION_BATTERY_CHANGED)
- [WorkManager periodic work](https://developer.android.com/reference/androidx/work/PeriodicWorkRequest)
- [Doze and App Standby](https://developer.android.com/training/monitoring-device-state/doze-standby)
- [Local network permission](https://developer.android.com/privacy-and-security/local-network-permission)
- [Google Play target API requirements](https://developer.android.com/google/play/requirements/target-sdk)

Recheck current target API, privacy, and Play policy requirements at release
time.

## Handoff checklist

The implementation agent should verify:

1. battery data is read through supported Android APIs
2. WorkManager execution is treated as inexact, including Doze and battery
   optimization delays
3. installation identity persists across restarts and is not hardware identity
4. uploads start only after a tenant administrator enrolls the device
5. stale queued samples are not replayed as fresh automation input
6. privacy disclosures and Play distribution requirements are in the release
   plan
