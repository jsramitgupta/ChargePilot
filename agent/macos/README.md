# ChargePilot macOS telemetry agent

The native Swift menu-bar app enrolls one Mac installation with a
tenant-scoped, reusable 24-hour token and reports battery state in the
background while the user is signed in and the Mac is awake. It does not
control switches or promise reports during sleep, logout, network loss, or
when the app is stopped.

The latest development DMG and source archive are published at
[ChargePilot GitHub Releases](https://github.com/jsramitgupta/ChargePilot/releases/latest).

## Requirements

- macOS 13 or later
- Swift 5.9 or later (Xcode Command Line Tools)
- a public ChargePilot API origin using HTTPS; plain HTTP is accepted only for
  `localhost` development
- a tenant-admin generated, reusable 24-hour enrollment token

New endpoints are automation-enabled by default across all platforms. The
server still requires a fresh sample, an allow-listed platform, and an enabled
tenant-matching mapping before it can issue a switch command. macOS reports
only while the app is running and the Mac is awake.

## Build and install

From the extracted project directory, create a development DMG:

```sh
./scripts/build-dmg.sh
open dist/ChargePilotAgent-0.1.0.dmg
```

Drag `ChargePilotAgent.app` to **Applications** and open it. The ChargePilot
battery icon appears in the menu bar. Use it to configure the server origin,
an explicit device label, and the enrollment code from ChargePilot's **Set up
a device** page. Select **Connect this Mac** to exchange the code. It is not
saved; the per-install credential is stored in the user's macOS Keychain.

After enrollment, the app sends a report immediately and every five minutes.
Its menu shows the latest accepted report and any upload errors. **Pause
reports** stops collection; **Open when I sign in** registers the app as a
macOS login item. Both are user-controlled. The app is a menu-bar process, not
a system daemon. Sleep and logout interrupt reporting, and macOS scheduling
does not provide a real-time guarantee.

The development DMG is universal for Apple Silicon and Intel but is unsigned
and not notarized. A first open may require the user to approve macOS's
security prompt.

## Command-line checks

The app bundle includes the same CLI for local diagnostics:

```sh
/Applications/ChargePilotAgent.app/Contents/MacOS/ChargePilotAgent check
```

This reads battery state without enrolling or contacting the server. The
`enroll` and `run` CLI commands remain available for foreground use. Use
`ChargePilotAgent --help` for their syntax.

The **Build endpoint agent artifacts** GitHub Actions workflow also builds the
DMG. Agent-source pushes and pull requests upload APK, unsigned IPA, and DMG
artifacts for 90 days. Push an `agents-v*` tag to publish them on a GitHub
Release. The Android APK is debug-signed, the iOS IPA is unsigned, and the DMG
is unsigned and not notarized.

Use the API origin only; the agent appends `/api/v1` routes itself. Do not put
credentials in shell history, source control, or environment files. Never
reuse the tenant-wide Windows agent token in this app.

## Data and privacy

The agent sends the chosen device label, battery percentage, charging and AC
state, observation timestamp, platform, installation ID, device class, and
agent version. It does not send a serial number, hardware UUID, IP address, or
system hostname. If Apple does not provide a usable battery reading, no sample
is sent.

## Stop or revoke

Pause reports or quit the app from its menu. A tenant administrator or manager
can revoke the installation credential from the Endpoints page; revocation
prevents further telemetry requests using that credential.
