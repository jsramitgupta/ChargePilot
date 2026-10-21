# Android Agent Architecture

## 1. Core architecture

A Kotlin app collects battery telemetry from Android system services and
uploads over HTTPS after an operator enables Android enrollment in server
configuration.
It does not issue switch commands or route control decisions locally.

## 2. Components

- Battery collector: reads level and charging state via Android APIs
- Identity manager: stores a random installation ID; no hardware ID is
  required or collected
- Scheduler: uses WorkManager to schedule periodic uploads with OS-aware constraints
- Upload service: sends the versioned payload with its enrolled per-install
  credential
- Status dashboard: shows last report and any stale or failed state

## 3. Key design decisions

- app behavior must be resilient to Doze and background delays
- last-report freshness must be visible to operators and users
- telemetry should include optional platform fields rather than assume all device platforms expose identical battery semantics
- backend policy remains the authority for automation decisions

## 4. Data flow

1. app starts or the OS runs an inexact WorkManager job
2. read current battery status and platform metadata
3. attach installation identity and platform metadata
4. send the current platform-aware payload after Android is enabled
5. persist update and record last success/failure
6. retry on later scheduled runs if the upload fails

## 5. Acceptance criteria

- the client uses the additive platform-aware schema and per-install
  enrollment; it never uses the Windows shared tenant token
- the app timestamps observations and does not treat queued samples as fresh
- installation ID and tenant logic remain isolated from the server's device-control path
