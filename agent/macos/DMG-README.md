# ChargePilot macOS agent

This is a foreground command-line agent, not a graphical macOS app.

## Check this Mac

Open Terminal, change to the mounted `ChargePilotAgent` volume, then run:

```sh
./ChargePilotAgent check
```

This reads battery state locally. It does not enroll the Mac or contact the
ChargePilot server.

## Enroll and report

Create a reusable enrollment token from ChargePilot's **Set up a device**
page. Then, in Terminal, run:

```sh
./ChargePilotAgent enroll --server-url https://chargepilot.example.com --label "Office Mac"
```

Replace the example origin and label with your values. Enter the enrollment
token at the hidden prompt; it is not saved. The installation ID is stored in
`~/Library/Application Support/ChargePilot` and the per-install credential is
stored in your macOS Keychain.

Start foreground reporting with:

```sh
./ChargePilotAgent run
```

Reports are sent immediately and then every five minutes while the process is
running and the Mac is awake. Stop with **Ctrl+C**. New endpoints are
telemetry-only until an authorized administrator explicitly enables
automation.

This development DMG is unsigned and not notarized. Its executable supports
Apple Silicon and Intel Macs running macOS 13 or later. It is not a signed
release.
