# iOS Agent PRD

## 1. Product goal

Create an iOS telemetry companion for ChargePilot that sends battery readings
when active and can be prompted by user-configured Shortcuts automations.
Backend enrollment and schema plus a SwiftUI source project in `agent/ios` are
implemented; iOS build and device validation are still required before
release. Shortcut/background delivery remains opportunistic.

## 2. User value

- gives ChargePilot informative telemetry from iPhone and iPad devices
- clarifies the boundary between supported telemetry and true automation
- prevents the backend from assuming iOS is a robust always-on telemetry host

## 3. Functional requirements

- read battery level and charging state using supported public APIs
- upload through the current platform-aware ChargePilot contract
- include observation timestamp, platform metadata, and a random
  installation ID from the enrollment flow; do not depend on hardware identity
- present the user with the status of the last successful upload
- store the revocable per-install credential from the enrollment flow
  in Keychain
- expose a Shortcuts App Intent to report fresh telemetry when a personal
  battery-level or charger-connected automation runs

## 4. Non-functional requirements

- must not control charging or switch power on the device
- must not rely on background execution guarantees for timely reporting
- must keep the app's behavior consistent with Apple privacy and App Review requirements
- must clearly communicate that iOS can defer or skip shortcut actions and
  does not guarantee exact threshold timing

## 5. Success criteria

- the app can report telemetry when launched or foregrounded after iOS
  enrollment is enabled by the server operator
- the Shortcuts action sends a fresh reading while locked only when the OS runs
  it and the device has been unlocked once after reboot
- existing Windows telemetry remains compatible
- delayed reports never trigger switch control as fresh data
- the app never implies that iOS telemetry is equivalent to a continuously connected laptop telemetry source
