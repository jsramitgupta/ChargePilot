# iOS Agent Stream

This stream specifies the planned iOS telemetry companion. The platform-aware
backend schema and enrollment flow are implemented, but no iOS client is
shipped and iOS enrollment remains disabled by default.

## Scope

- collect battery level and charging state using public iOS APIs
- send HTTPS telemetry through the current backend contract after iOS
  enrollment is enabled by a server operator
- adapt the app to the privacy and background limitations of iOS
- use a random installation UUID and per-install credential; do not
  collect hardware identifiers
- present the app as a telemetry companion, not an always-on automation agent

## Primary documents

- [PRD.md](./PRD.md)
- [ARCHITECTURE.md](./ARCHITECTURE.md)
- [TLD.md](./TLD.md)

## Non-goals

- no direct charging-policy control
- no device battery management API usage beyond reading status
- no assumption of reliable background telemetry delivery

## Implementation approach

Build a native SwiftUI app that reads battery state in the foreground and
supports user-initiated sync. Background URLSession transfers may be used only
for opportunistic delivery of already-collected samples; they do not guarantee
background sampling. Do not embed the current tenant-wide agent token. The
backend contract is in
[../SERVER_SIDE_CONFIG.md](../SERVER_SIDE_CONFIG.md).

## Known constraints

- iOS has strong background execution limitations and system-controlled scheduling
- the app cannot guarantee periodic telemetry while suspended
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
2. uploads begin only after an operator enables iOS and the user enrolls
3. the app exposes local last-success status and makes background limits clear
4. lifecycle changes and delayed uploads cannot create a false control signal
5. local-network permission is not requested for ordinary HTTPS telemetry
6. distribution and App Review requirements are included in release planning
