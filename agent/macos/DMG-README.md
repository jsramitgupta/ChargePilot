# ChargePilot macOS agent

## Install and connect

1. Drag `ChargePilotAgent.app` to **Applications**, then open it.
2. Use the ChargePilot icon in the menu bar to enter your server origin, a
   device label, and an enrollment code from **Set up a device**.
3. Select **Connect this Mac**. The one-time code is exchanged immediately and
   is not saved. The per-install credential is stored in Keychain.
4. Leave the menu-bar app running. It reports immediately and every five
   minutes while the Mac is awake. Turn on **Open when I sign in** to launch it
   automatically in your user session.

The menu-bar app displays its latest accepted report and any upload errors.
Use **Pause reports** to stop telemetry, or **Quit** to close the background
app. Sleep, logout, and network loss can interrupt reporting; this is not a
real-time service. New endpoints remain telemetry-only until an authorized
administrator explicitly enables automation.

## Command-line checks

The app bundle also contains the command-line interface:

```sh
/Applications/ChargePilotAgent.app/Contents/MacOS/ChargePilotAgent check
```

This reads battery state locally without enrolling or contacting the server.
For foreground reporting and troubleshooting, the CLI supports `enroll` and
`run`; run it without arguments to see its usage.

This development DMG is unsigned and not notarized. Its app supports Apple
Silicon and Intel Macs running macOS 13 or later.
