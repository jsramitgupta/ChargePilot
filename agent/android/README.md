# ChargePilot Android telemetry agent

This native Android app enrolls with a tenant-scoped, reusable 24-hour
enrollment token and sends battery telemetry to ChargePilot. Development
builds use the debug key. Tagged GitHub Releases use the configured Android
release keystore when available; otherwise the APK is unsigned and Android
will not install it as a trusted release. This is not a Google Play release.

Latest APK and source downloads: [ChargePilot GitHub Releases](https://github.com/jsramitgupta/ChargePilot/releases/latest).

## Requirements

- Android Studio with JDK 17 and Android SDK 35
- Android 8.0 (API 26) or later
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
4. Paste the 24-hour enrollment token. The API origin is fixed to
   `https://api-chargepilot.endusercompute.in`; the non-unique Android model
   name is used automatically. Serial numbers are not collected. The token is
   cleared after exchange.
5. The app stores a random installation ID and encrypts its per-install
   credential with an AES key held by Android Keystore.
6. Use **Send reading now** for an immediate sample. WorkManager also schedules
   fresh reports at an inexact interval of at least 15 minutes.

The **Build endpoint agent artifacts** GitHub Actions workflow builds a
debug APK for development and publishes an APK on `agents-v*` releases.
Configure all four Android signing secrets to sign the release APK. If none
are configured, the release is unsigned; a partially configured group fails
the release job. Check the release notes and `agent-release-manifest.json`
for the published signing status.

The first report is submitted after enrollment. If saving the issued
credential fails, revoke that endpoint from the ChargePilot Endpoints page
before trying another enrollment token.

## Reporting and privacy

Each report contains the non-unique model label, battery percentage, charging
state, optional AC connection state, current observation timestamp, platform,
random installation ID, device class, and app version. It does not send a
serial number, hardware ID, phone number, location, IP address, or personal
Android device name. Admins can change the display label on the Endpoints page.
If Android cannot provide a valid battery reading, no sample is sent.

WorkManager respects network availability, Doze, and system scheduling. Its
15-minute minimum is not a promise of exact reporting time. The app does not
control switches. New endpoints default to automation enabled, but the
backend requires a fresh report, an allow-listed platform, and a
tenant-matching enabled mapping before creating switch commands.

## Deregister and re-enroll

Select **Deregister device** in the app and confirm. ChargePilot revokes the
per-install credential, stops scheduled reports, and returns the app to its
enrollment form. Enter a new enrollment token to reconnect without
reinstalling. An administrator can also revoke the credential from the
ChargePilot Endpoints page. Removing the app alone does not revoke the
server-side endpoint.
