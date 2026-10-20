# Android Agent TLD

## 1. Tech stack

- Kotlin
- Android SDK
- `BatteryManager`
- `Intent.ACTION_BATTERY_CHANGED`
- WorkManager
- OkHttp or a comparable HTTPS client
- Jetpack Security for secure local token storage

## 2. Modules

- app bootstrap
- battery telemetry collector
- identity manager
- upload worker
- retry policy manager
- status UI

## 3. Battery telemetry integration

Use the Android battery APIs to capture battery percentage, charging state, and AC power status. Treat health values as optional because they are not a fully analogous battery-health metric to a laptop's power-source API.

## 4. Upload flow

- generate or load installation ID
- collect battery snapshot with timestamp and platform metadata
- authenticate using the per-install credential, not the tenant-wide
  Windows agent token
- send only after Android is enabled in the server allow-list; the enrolled
  endpoint does not require a hardware UUID or IP address
- store the report and log retry / failure outcome

## 5. Operational notes

- Use WorkManager periodic scheduling no more frequently than its documented
  minimum interval; execution is inexact.
- Do not assume exact periodicity under memory pressure or Doze.
- Keep observation timestamps and report local staleness. The backend applies
  its configured automation freshness gate independently.
