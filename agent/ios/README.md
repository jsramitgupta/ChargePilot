# ChargePilot iOS telemetry agent

This SwiftUI iPhone/iPad app enrolls with a tenant-scoped, reusable 24-hour
token and reports battery telemetry while open, when it returns to the
foreground, or when invoked by a Shortcuts automation. Tagged GitHub Releases
publish an installable IPA. When
Apple signing secrets are configured, it is ad-hoc signed for devices in the
configured provisioning profile; without them, it is unsigned and requires
signing before device installation. This is not an App Store release.

The latest installable IPA is available from ChargePilot **Set up a device**.
The source project requires an authorized checkout of the private repository.

## Requirements

- macOS with Xcode 15 or later
- iOS 16 or later
- A tenant administrator's enrollment token from **Set up a device**

## Build and enroll

1. Open `agent/ios/ChargePilotAgent.xcodeproj` from an authorized repository
   checkout in Xcode.
3. Select the `ChargePilotAgent` scheme and a signing team, then build and
   install it on an iPhone or iPad.
4. Paste the 24-hour enrollment token. The API origin is fixed to
   `https://api-chargepilot.endusercompute.in`; the app uses a generic device
   type (iPhone or iPad), not a serial number or personal device name. The app
   exchanges the token and clears it from the form.
5. The app stores a random installation ID locally and the persistent
   per-install credential in the device-only Keychain.

For a local device build, configure a signing team in Xcode. A signed release
IPA is ad-hoc provisioned and can only be installed on devices included in
its profile. Configure all iOS signing secrets and `APPLE_TEAM_ID` to enable
release signing. An absent group publishes an unsigned IPA; a partial group
or failed signature verification fails the release. Check the release notes
and `agent-release-manifest.json` for the signing status. Tagged release
versions are taken from the `agents-vMAJOR.MINOR.PATCH` tag and applied to the
IPA's app metadata and telemetry reports.

The app exposes **Report battery to ChargePilot** as an App Shortcut. After
enrollment, set up these personal automations in the Shortcuts app:

1. Create a **Battery Level** automation for **Rises Above 90%**.
2. Create a second **Charger** automation for **Is Connected**. This reports
   the current level if the phone is plugged in after it has already passed
   90%.
3. In each automation, add the **Report battery to ChargePilot** action. Set
   it to run immediately/automatically when iOS offers that option.
4. Confirm a test run appears as a fresh endpoint report in ChargePilot.

The action reads the current battery level and charging state when it runs,
then sends a fresh sample using the enrolled endpoint credential. It does not
make a switch decision. Configure a mapping's charging cutoff to 90%, and
ensure the iOS platform is explicitly allowed and the endpoint opted in before
expecting server-side automation.

iOS may defer or skip automations, and background execution, battery readings,
network access, and switch command completion can all be delayed. This does
not guarantee a switch action exactly at 90%. The app also sends a reading
after enrollment, when it returns to the foreground, and when **Send reading
now** is tapped.

Each report also includes CPU utilization, used/total memory, and system
storage usage when available. GPU utilization is unavailable on iOS. The
server-configured tenant cadence (5 minutes to 24 hours) is shown in the app;
iOS has no guaranteed repeating background schedule, so foreground and
Shortcuts reports remain best-effort regardless of that target. Tenant admins
and managers set the cadence from ChargePilot's Agent setup page. Resource
history is retained for 30 days and does not affect automation.

## Reporting and privacy

The app sends a generic device-type label, battery percentage, charging state,
observation timestamp, platform, random installation ID, device class, agent
version, and available system resource metrics. It does not send an IP address,
hardware identifier, location, phone number, or the system device name. If iOS
reports an unknown battery level or state, the app sends no sample.

The Shortcuts action is permitted to run without opening the app or requiring
device authentication so it can attempt a report while the phone is locked.
Its credential remains in device-only Keychain with
`AfterFirstUnlockThisDeviceOnly` protection: the phone must have been unlocked
once after a reboot before the action can read it. This is not a guarantee
that iOS will run the action while locked. After updating an existing test
installation, open ChargePilot once while the device is unlocked so it can
upgrade the saved credential's Keychain accessibility.

ChargePilot retains automation authority. New endpoints default to automation
enabled across all four platforms, subject to a fresh report, server platform
policy, and an enabled tenant-safe mapping. This app does not issue switch
commands or control charging.

## Deregister and re-enroll

Select **Deregister device** in the app and confirm. ChargePilot revokes the
per-install credential and the app returns to its enrollment form. Enter a
new enrollment token to reconnect without reinstalling. An administrator can
also revoke the endpoint credential from the ChargePilot Endpoints page.
Removing the app does not revoke the server-side endpoint. If Keychain
storage fails after enrollment, revoke the newly created endpoint before
attempting a fresh enrollment.
