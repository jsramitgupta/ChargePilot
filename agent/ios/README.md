# ChargePilot iOS telemetry agent

This SwiftUI iPhone/iPad app enrolls with a tenant-scoped, reusable 24-hour
token and reports battery telemetry while open, when it returns to the
foreground, or when invoked by a Shortcuts automation. It is source code for
Xcode. GitHub Releases publish the unsigned IPA and source project; the IPA
requires signing and provisioning for installation.

Latest IPA and source downloads: [ChargePilot GitHub Releases](https://github.com/jsramitgupta/ChargePilot/releases/latest).

## Requirements

- macOS with Xcode 15 or later
- iOS 16 or later
- An API origin using HTTPS; use the origin only, without `/api/v1`
- A tenant administrator's enrollment token from **Set up a device**

## Build and enroll

1. Download and extract the iOS agent project from **Set up a device**.
2. Open `ChargePilotAgent.xcodeproj` in Xcode.
3. Select the `ChargePilotAgent` scheme and a signing team, then build and
   install it on an iPhone or iPad.
4. Enter the API origin, a descriptive device label, and the 24-hour
   enrollment token. The app exchanges the token and clears it from the form.
5. The app stores a random installation ID locally and the persistent
   per-install credential in the device-only Keychain.

For an unsigned device-build IPA, use Xcode's **Product > Archive** with
automatic signing disabled, or download the IPA from the latest GitHub Release.
It cannot be installed on a device until signed with an Apple signing identity
and a matching provisioning profile.

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

## Reporting and privacy

The app sends a user-provided label, battery percentage, charging state,
observation timestamp, platform, random installation ID, device class, and
agent version. It does not send an IP address, hardware identifier, location,
phone number, or the system device name. If iOS reports an unknown battery
level or state, the app sends no sample.

The Shortcuts action is permitted to run without opening the app or requiring
device authentication so it can attempt a report while the phone is locked.
Its credential remains in device-only Keychain with
`AfterFirstUnlockThisDeviceOnly` protection: the phone must have been unlocked
once after a reboot before the action can read it. This is not a guarantee
that iOS will run the action while locked. After updating an existing test
installation, open ChargePilot once while the device is unlocked so it can
upgrade the saved credential's Keychain accessibility.

ChargePilot retains automation authority. New endpoints start with automation
disabled, and mobile platforms remain outside the default automation
allow-list. This app does not issue switch commands or control charging.

## Revoke

An administrator can revoke the endpoint credential from the ChargePilot
Endpoints page. Removing the app does not revoke the server-side endpoint.
If Keychain storage fails after enrollment, revoke the newly created endpoint
before attempting a fresh enrollment.
