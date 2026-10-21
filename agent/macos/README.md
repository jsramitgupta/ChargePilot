# ChargePilot macOS telemetry agent

This Swift command-line agent enrolls one Mac installation with a
tenant-scoped, reusable 24-hour token and reports its battery state while the
process is running. The token can enroll multiple devices; each exchange
creates a distinct endpoint credential. The agent does not control switches
and does not promise reports while the Mac sleeps, is powered off, or the
process is stopped.

## Requirements

- macOS 13 or later
- Swift 5.9 or later (Xcode Command Line Tools)
- a public ChargePilot API URL using HTTPS; plain HTTP is accepted only for
  `localhost` development
- a tenant-admin generated, reusable 24-hour enrollment token

The enrolled endpoint starts with automation disabled. Keep it telemetry-only
unless an administrator explicitly enables automation after a fresh reading.

## Build and enroll

1. Download and extract the macOS agent source from the authenticated ChargePilot
   **Set up a device** page.
2. To create a development DMG on this Mac, run from the extracted project
   directory:

   ```sh
   ./scripts/build-dmg.sh
   open dist/ChargePilotAgent-0.1.0.dmg
   ```

   The image contains a universal ARM64/Intel release CLI and package README.
   It supports macOS 13 and later but is not signed or notarized. It is a
   command-line agent, not a graphical app.
3. With the image mounted in Finder, validate local battery access without
   enrolling or contacting the server:

   ```sh
   /Volumes/ChargePilotAgent/ChargePilotAgent check
   ```

4. To enroll, run the following from Terminal, substituting your tenant's API
   origin and a label:

   ```sh
   /Volumes/ChargePilotAgent/ChargePilotAgent enroll \
     --server-url https://chargepilot.example.com \
     --label "Office Mac"
   ```

5. Paste the enrollment token when prompted. The token is not saved.
   The agent persists a random installation ID in
   `~/Library/Application Support/ChargePilot` and stores the per-install
   credential in the user's macOS Keychain.
6. Start reports while signed in:

   ```sh
   /Volumes/ChargePilotAgent/ChargePilotAgent run
   ```

   The agent sends an initial reading and then reports every five minutes
   while the process is active.

The **Build endpoint agent artifacts** GitHub Actions workflow also builds the
development DMG. Agent-source pushes and pull requests upload APK, unsigned
IPA, and DMG build artifacts for 90 days. Push an `agents-v*` tag to publish
those artifacts on a GitHub Release. The Android APK is debug-signed; the iOS
IPA is unsigned; the DMG is unsigned and not notarized.

Use the API origin only; the agent appends `/api/v1` routes itself. Do not put
credentials in shell history, source control, or environment files. Never
reuse the tenant-wide Windows agent token in this app.

## Data and privacy

The agent sends an explicit user-provided label, battery percentage, charging
and AC state, observation timestamp, platform, installation ID, device class,
and agent version. It does not send a serial number, hardware UUID, IP address,
or system hostname. When Apple does not provide a usable battery reading, the
agent reports the failure locally and sends no synthetic sample.

## Stop or revoke

Stop the foreground process with `Ctrl+C`. A tenant administrator or manager
can revoke the installation credential from the Endpoints page. Revocation
immediately prevents further telemetry requests using that credential.

This first release is a foreground CLI. A signed, notarized menu-bar/login-item
application and Android/iOS clients remain follow-up work.
