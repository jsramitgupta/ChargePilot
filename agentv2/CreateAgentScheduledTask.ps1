#Requires -Version 5.1
#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Installs (or removes) the ChargePilot battery agent and its scheduled task.

.EXAMPLE
    .\CreateAgentScheduledTask.ps1 -ServerUrl https://chargepilot.example.com -EndpointToken abc123 -RunNow

.EXAMPLE
    .\CreateAgentScheduledTask.ps1 -DeleteOnly -RemoveFiles
#>
[CmdletBinding()]
param(
    [string]$ServerUrl,
    [string]$EndpointToken,
    [string]$AgentVersion = "1.0.0",
    [ValidateRange(1, 1440)][int]$IntervalMinutes = 5,
    [string]$TaskName = "ChargePilotBatteryAgent",
    [string]$InstallDir = "C:\Program Files\ChargePilot\Agent",
    [switch]$DeleteOnly,      # remove the scheduled task and stop
    [switch]$RemoveFiles,     # with -DeleteOnly: also delete agent files, config and logs
    [switch]$RunNow           # start the task right after install and report the result
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$dataDir = Join-Path $env:ProgramData "ChargePilot"
$configPath = Join-Path $dataDir "agent-config.json"

function Remove-ChargePilotTask {
    param([string]$Name)

    if (Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $Name -Confirm:$false
        Write-Host "Scheduled task '$Name' removed."
    }
    else {
        Write-Host "Scheduled task '$Name' not found; nothing to remove."
    }
}

function Set-RestrictedAcl {
    # Only SYSTEM and Administrators may read the config (it contains the endpoint token).
    param([string]$Path)

    & icacls.exe $Path /inheritance:r /grant:r "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Failed to restrict permissions on '$Path' (icacls exit $LASTEXITCODE)." }
}

function Install-ChargePilotAgent {
    param([string]$SourceScript)

    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    New-Item -ItemType Directory -Path $dataDir -Force | Out-Null
    Set-RestrictedAcl -Path $dataDir

    Copy-Item -Path $SourceScript -Destination (Join-Path $InstallDir "BatteryAgent.ps1") -Force

    $config = [ordered]@{
        serverUrl     = $ServerUrl.TrimEnd("/")
        endpointToken = $EndpointToken
        agentVersion  = $AgentVersion
    }

    # Write to a temp file then move, so a crash can't leave a half-written config.
    $tmp = "$configPath.tmp"
    $config | ConvertTo-Json | Set-Content -Path $tmp -Encoding UTF8
    Move-Item -Path $tmp -Destination $configPath -Force

    Write-Host "Agent installed to: $InstallDir"
    Write-Host "Config stored at:   $configPath (SYSTEM/Administrators only)"
}

# ---------------------------------------------------------------- remove
if ($DeleteOnly) {
    Remove-ChargePilotTask -Name $TaskName
    if ($RemoveFiles) {
        foreach ($p in $InstallDir, $dataDir) {
            if (Test-Path $p) { Remove-Item -Path $p -Recurse -Force; Write-Host "Deleted $p" }
        }
    }
    return
}

# ---------------------------------------------------------------- validate
if ([string]::IsNullOrWhiteSpace($ServerUrl) -or [string]::IsNullOrWhiteSpace($EndpointToken)) {
    throw "-ServerUrl and -EndpointToken are required."
}

$parsed = $null
if (-not [Uri]::TryCreate($ServerUrl, [UriKind]::Absolute, [ref]$parsed) -or $parsed.Scheme -notin "http", "https") {
    throw "-ServerUrl '$ServerUrl' is not a valid http(s) URL."
}
if ($parsed.Scheme -eq "http" -and $parsed.Host -notin "localhost", "127.0.0.1", "::1") {
    Write-Warning "ServerUrl uses plain HTTP; the endpoint token will travel unencrypted. Use HTTPS in production."
}

$sourceScript = Join-Path $PSScriptRoot "BatteryAgent.ps1"
if (-not (Test-Path -Path $sourceScript)) {
    throw "BatteryAgent.ps1 was not found next to this installer ('$sourceScript')."
}

# ---------------------------------------------------------------- install
Install-ChargePilotAgent -SourceScript $sourceScript

$installedScript = Join-Path $InstallDir "BatteryAgent.ps1"

# The token and URL live only in the ACL-protected config file, NOT in the task arguments,
# because task definitions are readable by any local user.
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument (
    '-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}"' -f $installedScript)

$triggers = @(
    New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes)
    New-ScheduledTaskTrigger -AtStartup
)

# Run as SYSTEM: works with nobody logged in and doesn't depend on the installing admin's account.
$principal = New-ScheduledTaskPrincipal -UserId "NT AUTHORITY\SYSTEM" -LogonType ServiceAccount -RunLevel Highest

# Critical for a battery agent: by default tasks do NOT start on battery and are killed when
# the laptop unplugs, which is exactly when telemetry matters most.
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 3) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)

# -Force makes registration idempotent: it replaces an existing task in place.
Register-ScheduledTask -TaskName $TaskName `
    -Action $action -Trigger $triggers -Principal $principal -Settings $settings `
    -Description "ChargePilot battery telemetry agent" -Force | Out-Null

Write-Host "Scheduled task '$TaskName' registered (every $IntervalMinutes min + at startup, runs as SYSTEM)."

if ($RunNow) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "Started task; waiting for it to finish..."
    $deadline = (Get-Date).AddSeconds(90)
    do {
        Start-Sleep -Seconds 2
        $state = (Get-ScheduledTask -TaskName $TaskName).State
    } while ($state -eq "Running" -and (Get-Date) -lt $deadline)

    $info = Get-ScheduledTaskInfo -TaskName $TaskName
    if ($info.LastTaskResult -eq 0) {
        Write-Host "First run succeeded."
    }
    else {
        Write-Warning "First run returned $($info.LastTaskResult). See $(Join-Path $dataDir 'logs\agent.log')"
    }
}
