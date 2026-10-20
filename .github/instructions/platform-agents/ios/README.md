# iOS Agent Stream

The native SwiftUI iOS telemetry companion source project is implemented in
`agent/ios`. It uses the platform-aware backend schema and reusable enrollment
flow. It has not yet been built or validated on an iOS device, and no signed
app is distributed.

## Scope

- collect battery level and charging state using public iOS APIs
- send HTTPS telemetry through the current backend contract using the
  tenant-scoped enrollment token; iOS enrollment is enabled by default,
  subject to server configuration
- adapt the app to the privacy and background limitations of iOS
- use a random installation UUID and per-install credential; do not
  collect hardware identifiers
- expose a Shortcuts App Intent for user-configured battery/charger
  automations, while keeping reporting best-effort and server-authoritative

## Primary documents

- [PRD.md](./PRD.md)
- [ARCHITECTURE.md](./ARCHITECTURE.md)
- [TLD.md](./TLD.md)

## Non-goals

- no direct charging-policy control
- no device battery management API usage beyond reading status
- no assumption of reliable background telemetry delivery

## Implementation approach

Build a native SwiftUI app that reads battery state in the foreground, supports
user-initiated sync, and exposes an App Intent for Shortcuts automations.
Shortcuts may request a fresh reading on battery-level and charger-connected
events, but iOS may defer or skip invocation. The App Intent uses device-only
Keychain storage accessible after first unlock so it can attempt reporting
while locked; it does not provide an exact timing guarantee. Do not embed the
current tenant-wide agent token. The backend contract is in
[../SERVER_SIDE_CONFIG.md](../SERVER_SIDE_CONFIG.md).

## Known constraints

- iOS has strong background execution limitations and system-controlled scheduling
- Shortcuts automations can prompt a report but cannot guarantee invocation
  timing or successful delivery while the device is locked
- the device must be unlocked once after reboot before the App Intent can read
  the endpoint credential from Keychain
- battery health and rich power-source metadata are not consistently exposed through public APIs

## Platform references

- [UIDevice battery level](https://developer.apple.com/documentation/uikit/uidevice/batterylevel)
- [UIDevice battery state](https://developer.apple.com/documentation/uikit/uidevice/batterystate-swift.enum)
- [Battery monitoring](https://developer.apple.com/documentation/uikit/uidevice/isbatterymonitoringenabled)
- [Choosing background strategies](https://developer.apple.com/documentation/backgroundtasks/choosing-background-strategies-for-your-app)
- [Background URLSession](https://developer.apple.com/documentation/foundation/urlsessionconfiguration/background%28withidentifier%3A%29)
- [Local network privacy](https://developer.apple.com/documentation/technotes/tn3179-understanding-local-network-privacy)
- [App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/)

Recheck supported background modes and App Review/privacy requirements when
implementation and release begin.

## Handoff checklist

The implementation agent should verify:

1. the app reads battery state and level only through supported public APIs;
   it does not send an unknown level as zero
2. uploads begin only after a user enrolls with an administrator-provided token
3. the app exposes local last-success status and makes background limits clear
4. lifecycle changes and delayed uploads cannot create a false control signal
5. local-network permission is not requested for ordinary HTTPS telemetry
6. distribution and App Review requirements are included in release planning
