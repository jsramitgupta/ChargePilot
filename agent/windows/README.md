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
signing status. The executable's assembly and telemetry versions come from
the `agents-vMAJOR.MINOR.PATCH` release tag. The executable does not hide or
encrypt its application code.
Enrollment tokens are entered in the UI or at a masked CLI prompt, never
passed as command-line arguments.

## Install from ChargePilot

On **Set up a device**, create or reveal an active enrollment token and copy
the Windows install command. On the Windows device, run the command in
PowerShell and approve the administrator prompt. The bootstrap downloads the
latest executable over HTTPS and opens its setup UI.

The installer downloads the executable from the same public API origin that
served the install command and passes that origin to the setup application.
This also works for self-hosted deployments that set `CHARGEPILOT_API_URL`.

In the setup window:

1. The ChargePilot API origin is shown for confirmation. The Windows computer
   name is used automatically; serial numbers are not collected.
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
retained in the private repository only for compatibility and diagnostics.

## Configure with the UI

Run `ChargePilotAgent.exe ui` as Administrator. The window can install or
update configuration, update the agent, deregister this device, start or stop
the service, and remove the service. The installed app version appears beside
the service status. Select **Update agent** to check the latest public
`agents-v*` release and confirm before downloading it. The service is stopped
and restarted if it was running; its saved enrollment and settings are kept.
If the new service executable cannot start, the previous executable is
restored.
The update uses the HTTPS GitHub release asset. Unsigned releases can still
trigger Windows SmartScreen.
Leave the enrollment-token field blank to keep an existing enrollment while
changing the device class or reporting interval. The reported computer name
and API origin are not editable. Enter a new token to enroll again.
Deregistration revokes this installation's
credential on the server, stops reporting, and returns the window to an
unenrolled state; the Windows app does not need to be reinstalled.

The local reporting interval defaults to five minutes and can be set from 1
to 60 minutes as a fallback. After each accepted report, the service follows
the tenant's server-configured cadence (5 minutes to 24 hours) for its next
report. Tenant admins and managers configure this value from ChargePilot's
Agent setup page; a change takes effect when the service receives the next
successful response. The backend remains authoritative for freshness,
automation eligibility, hysteresis, cooldowns, and switch commands.
The enrolled service also polls for the fixed endpoint shutdown request every
15 seconds while configured. It schedules only Windows shutdown, with the
server-specified 60-second countdown visible to signed-in users; a local user
can cancel it with `shutdown /a`. It never accepts arbitrary command text.
The server issues this request only when a mapping explicitly selects
switch-and-shutdown and its switch-off action succeeds.

Every report also includes the resource values Windows can read: CPU and
available GPU utilization, used/total physical memory, and fixed local-disk
usage. GPU readings remain unavailable when Windows WMI does not expose them.
The server stores this optional history for 30 days; it does not affect
automation decisions.

The Windows service also polls for tenant-assigned Smart Group sensor work.
It supports only the fixed read-only `os_version`, `uptime_seconds`, and
`system_disk_free_bytes` sensors. Collection uses native .NET APIs in the
service and works without a signed-in user. The server returns a sensor ID,
not PowerShell or another script, and validates each typed result.

## Configure and manage from the CLI

Open an elevated PowerShell window in the executable directory:

```powershell
.\ChargePilotAgent.exe install --class laptop --interval-minutes 5
.\ChargePilotAgent.exe configure --class desktop --interval-minutes 5
.\ChargePilotAgent.exe status
.\ChargePilotAgent.exe start
.\ChargePilotAgent.exe stop
.\ChargePilotAgent.exe deregister
.\ChargePilotAgent.exe send-once
.\ChargePilotAgent.exe uninstall
```

`install` and `configure` prompt for the enrollment token without displaying
its characters. They accept an optional `--server-url https://api.example.test`
for a self-hosted API; if omitted, the saved server URL is reused, or the
ChargePilot public API is used for a new install. `ui` also accepts this option.
Do not pass tokens as CLI options; command-line arguments may be exposed in
process listings or shell history. The `status` and `send-once` commands can be run without elevation. Service
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
with the signing state recorded in release metadata. The ChargePilot API
provides the installable binary to customers. See the platform-agent
release-signing instructions for the required GitHub secrets.
Windows service installation and telemetry runtime behavior must be validated
on a Windows device; they cannot be run on macOS.

## Legacy PowerShell agent

`agent/BatteryAgent.ps1` and `agent/CreateAgentScheduledTask.ps1` remain in the
private repository for existing deployments. They are not part of public
downloads and are not used by the new service installer.
