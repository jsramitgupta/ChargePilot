# ChargePilot Windows service agent

The self-contained x64 .NET executable installs a background Windows service.
It also provides an elevated Windows Forms setup UI and a command-line
interface. The service reports battery telemetry without requiring a user to
be signed in; the UI runs separately and never appears in the service session.
New installations do not use Task Scheduler.

Tagged GitHub Releases publish the Windows executable whether or not
Authenticode signing is configured. Configure both Windows signing secrets to
sign it; otherwise it is unsigned and may trigger Windows SmartScreen. A
partially configured secret group or failed signature verification stops the
release. Check the release notes and `agent-release-manifest.json` for its
signing status. The executable does not hide or encrypt its application code.
Enrollment tokens are entered in the UI or at a masked CLI prompt, never
passed as command-line arguments.

## Install from ChargePilot

On **Set up a device**, create or reveal an active enrollment token and copy
the Windows install command. On the Windows device, run the command in
PowerShell and approve the administrator prompt. The bootstrap downloads the
latest executable over HTTPS and opens its setup UI.

In the setup window:

1. Confirm the ChargePilot API origin and device name.
2. Select **Laptop** or **Desktop**, then choose the reporting interval.
3. Enter the enrollment token and choose **Save and start service**.

The agent exchanges the 24-hour enrollment token for a per-install endpoint
credential. The token is not stored. The credential is machine-protected with
Windows DPAPI in `%ProgramData%\ChargePilot\Agent\config.json`; the directory
ACL grants access only to SYSTEM and Administrators. The service runs as
LocalSystem and starts automatically after reboot.

The installer can migrate an existing `%LOCALAPPDATA%\ChargePilot\agent-config.json`
created by the previous Windows agent. Run setup as the same Windows account
that created that configuration so its user-scoped DPAPI value can be
decrypted. After the new service starts, setup removes the legacy
`ChargePilotBatteryAgent` scheduled task. The shared-token agent remains
available in the source archive only for compatibility and diagnostics.

## Configure with the UI

Run `ChargePilotAgent.exe ui` as Administrator. The window can install or
update configuration, deregister this device, start or stop the service, and
remove the service.
Leave the enrollment-token field blank to keep an existing enrollment when
changing the device name, class, or reporting interval. Enter a new token to
enroll again or change the server. Deregistration revokes this installation's
credential on the server, stops reporting, and returns the window to an
unenrolled state; the Windows app does not need to be reinstalled.

Reporting defaults to every five minutes and can be set from 1 to 60 minutes.
The backend remains authoritative for freshness, automation eligibility,
hysteresis, cooldowns, and switch commands.

## Configure and manage from the CLI

Open an elevated PowerShell window in the executable directory:

```powershell
.\ChargePilotAgent.exe install --server-url "https://api-chargepilot.endusercompute.in" --name "Office device" --class laptop --interval-minutes 5
.\ChargePilotAgent.exe configure --server-url "https://api-chargepilot.endusercompute.in" --name "Office device" --class desktop --interval-minutes 5
.\ChargePilotAgent.exe status
.\ChargePilotAgent.exe start
.\ChargePilotAgent.exe stop
.\ChargePilotAgent.exe deregister
.\ChargePilotAgent.exe send-once
.\ChargePilotAgent.exe uninstall
```

`install` and `configure` prompt for the enrollment token without displaying
its characters. Do not pass tokens as CLI options; command-line arguments may
be exposed in process listings or shell history. The `status` and `send-once` commands can be run without elevation. Service
installation, configuration, deregistration, start, stop, and uninstall
require an elevated administrator terminal.

`uninstall` removes the service and any old scheduled task, but retains the
configuration and executable for reinstall. Use
`uninstall --purge-config` to remove the saved enrollment as well. After
uninstalling, the Program Files application directory can be removed manually.

## Build

Install the .NET 10 SDK. Builds produce a single-file self-contained Windows
x64 executable, so target devices do not need a separate .NET runtime.

On macOS or Windows:

```sh
dotnet test agent/windows/tests/ChargePilotAgent.Core.Tests/ChargePilotAgent.Core.Tests.csproj --configuration Release
dotnet publish agent/windows/ChargePilotAgent.csproj \
  --configuration Release \
  --runtime win-x64 \
  --self-contained true \
  -p:EnableWindowsTargeting=true \
  --output ./dist/windows
```

On Windows, the repository build script also checks the generated PE header:

```powershell
.\agent\windows\BuildAgentExe.ps1 -OutputPath .\dist\ChargePilotAgent.exe
```

GitHub Actions runs the Windows build and uploads a 90-day development
artifact for `agent/**` changes. An `agents-v*` tag publishes the executable
only after Authenticode signing and verification succeed. See the
platform-agent release-signing instructions for the required GitHub secrets.
Windows service installation and telemetry runtime behavior must be validated
on a Windows device; they cannot be run on macOS.

## Legacy PowerShell agent

`agent/BatteryAgent.ps1` and `agent/CreateAgentScheduledTask.ps1` remain in the
source archive for existing deployments. They are not used by the new service
installer and should not be used for new installations.
