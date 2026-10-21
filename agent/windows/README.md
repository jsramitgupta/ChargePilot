# ChargePilot Windows executable

The Windows download is a 64-bit executable wrapper around the existing
PowerShell telemetry agent. It preserves the same enrollment, Windows
user-protected credential, telemetry, and scheduled-task behavior; it is not a
native rewrite and does not hide the embedded script. The executable is
unsigned, so Windows SmartScreen may show a warning.

Builds run on a Windows GitHub Actions runner. A Windows executable cannot run
natively on macOS; from a Mac, use the **Build endpoint agent artifacts**
workflow to build it remotely. The workflow uploads a 90-day Actions artifact
for branch builds and includes the executable in GitHub Releases for
`agents-v*` tags.

To build locally on Windows, use Windows PowerShell 5.1:

```powershell
.\agent\windows\BuildAgentExe.ps1 -OutputPath .\ChargePilotAgent.exe
```

The build script installs the pinned PS2EXE 1.0.18 module from PowerShell
Gallery. The resulting agent expects the per-user
`%LOCALAPPDATA%\ChargePilot\agent-config.json` created by the ChargePilot
installer. For a new device, use the authenticated **Set up a device** page:
the setup command enrolls the device, protects its per-install credential with
Windows user-scoped DPAPI, downloads the executable, and registers the
recurring scheduled task.

Do not embed enrollment tokens or endpoint credentials in the executable.
Only the Windows device should hold its DPAPI-protected credential.
