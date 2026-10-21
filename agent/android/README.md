# ChargePilot Android telemetry agent

This native Android app enrolls with a tenant-scoped, reusable 24-hour
enrollment token and sends battery telemetry to ChargePilot. GitHub Releases
publish a debug-signed APK for sideloading and the source project; this is not
a Google Play release.

Latest APK and source downloads: [ChargePilot GitHub Releases](https://github.com/jsramitgupta/ChargePilot/releases/latest).

## Requirements

- Android Studio with JDK 17 and Android SDK 35
- Android 8.0 (API 26) or later
- An API origin using HTTPS; use the origin only, without `/api/v1`
- A tenant administrator's enrollment token from **Set up a device**

## Build and install

1. Download and extract the Android agent source archive, then open the
   extracted `chargepilot-android-agent` folder in Android Studio.
2. Allow Gradle sync, then build the debug APK with **Build > Build Bundle(s) /
   APK(s) > Build APK(s)**, or run `./gradlew assembleDebug` from the project
   folder (`gradlew.bat assembleDebug` on Windows). The APK is written to
   `app/build/outputs/apk/debug/app-debug.apk`.
3. To install it on a running emulator or connected device, run
   `adb install -r app/build/outputs/apk/debug/app-debug.apk`, then open
   ChargePilot from the launcher. This debug APK is for development; it is not
   a signed release.
4. Enter the ChargePilot API origin, a device label, and the 24-hour
   enrollment token. The token is cleared after exchange.
5. The app stores a random installation ID and encrypts its per-install
   credential with an AES key held by Android Keystore.
6. Use **Send reading now** for an immediate sample. WorkManager also schedules
   fresh reports at an inexact interval of at least 15 minutes.

The **Build endpoint agent artifacts** GitHub Actions workflow builds the debug
APK and publishes it on `agents-v*` releases.

The first report is submitted after enrollment. If saving the issued
credential fails, revoke that endpoint from the ChargePilot Endpoints page
before trying another enrollment token.

## Reporting and privacy

Each report contains the user-provided label, battery percentage, charging
state, optional AC connection state, current observation timestamp, platform,
random installation ID, device class, and app version. It does not send a
hardware ID, phone number, location, IP address, or the Android device name.
If Android cannot provide a valid battery reading, no sample is sent.

WorkManager respects network availability, Doze, and system scheduling. Its
15-minute minimum is not a promise of exact reporting time. The app does not
control switches; new endpoints are telemetry-only until explicitly enabled
by an authorized ChargePilot administrator under server policy.

## Revoke

An administrator can revoke the endpoint credential from the ChargePilot
Endpoints page. Credential revocation prevents further reports. Removing the
app removes its local key and configuration but does not revoke the server
endpoint.
