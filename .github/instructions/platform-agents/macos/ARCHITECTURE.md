# macOS Agent Architecture

## 1. Core architecture

The shipped client is a SwiftUI menu-bar app with CLI diagnostics. It collects
power data while awake and while the app process is running; a user may opt in
to launch at sign-in through `SMAppService.mainApp`. It does not command
switches or manipulate Tuya devices. It uses the live tenant-scoped enrollment
and platform-aware telemetry contract. The installation ID is stored locally
and the per-install credential is stored in Keychain.

## 2. Components

- Power source service: reads battery state and charging metadata using Apple power APIs
- Identity manager: creates and preserves a random installation ID; server
  enrollment binds it to one endpoint and tenant
- Network uploader: sends the agreed versioned payload using the enrolled
  per-install credential
- Scheduler: determines when to read and transmit based on the user session and OS state
- Menu-bar UI: configures enrollment and reporting, and displays last
  upload success/failure

CPU telemetry is host-wide utilization, calculated from Mach counters in
user/system/idle/nice order over a short sampling window. It describes the Mac,
not the ChargePilot process, and is sampled only when a report is sent.

## 3. Key design decisions

- battery checks should be opportunistic rather than a guaranteed real-time loop
- telemetry is uploaded over HTTPS using an additive backend contract; the
  legacy Windows payload/auth behavior remains unchanged
- app state should never replace backend validation or mapping rules
- no local battery-rule or switch-control logic should exist in the app
- accept only the fixed, authenticated shutdown request for an enrolled
  endpoint; require confirmation in the menu-bar app before calling System
  Events. Never run shell text or arbitrary commands received from the server.

## 4. Data flow

1. app starts or wakes in the signed-in user session
2. retrieve installation identity and credential from secure storage
3. read battery state and available optional power-source metadata
4. build the agreed platform-aware payload; omit unavailable network data
5. send authenticated JSON through the enrolled per-install credential
6. update local success/failure state
7. retry later if upload fails
8. while reporting is active, poll for fixed shutdown requests, deduplicate
   handled request IDs locally, ask the logged-in user, and acknowledge the
   result using the same per-install credential

## 5. Acceptance criteria

- telemetry uses the platform-aware contract and never uses the tenant-wide
  Windows token
- the app is structured so scheduler details can change without changing
  server logic
- login-item, sleep, and background behavior are documented as best-effort
  limitations
- shutdown is not received while the app is paused, stopped, logged out, or the
  Mac is asleep; a scheduled acknowledgement is not proof of OS shutdown
