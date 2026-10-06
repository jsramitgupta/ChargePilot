[CmdletBinding()]
param(
    [string]$ServerUrl = "http://localhost:8000",
    [string]$EndpointToken = "test-endpoint-token",
    [string]$AgentVersion = "1.0.0",
    [int]$IntervalMinutes = 5,
    [string]$TaskName = "ChargePilotBatteryAgent",
    [string]$InstallDir = "",
    [switch]$DeleteExisting,
    [switch]$DeleteOnly
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ([string]::IsNullOrWhiteSpace($InstallDir)) {
    $InstallDir = Join-Path $env:LOCALAPPDATA "ChargePilot\Agent"
}

$ConfigPath = Join-Path $env:LOCALAPPDATA "ChargePilot\agent-config.json"
$LegacyConfigPath = Join-Path $env:ProgramData "ChargePilot\agent-config.json"

function Get-CurrentTaskUserId {
    $currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    if (-not [string]::IsNullOrWhiteSpace($currentUser)) {
        return $currentUser
    }

    if (-not [string]::IsNullOrWhiteSpace($env:USERDOMAIN) -and -not [string]::IsNullOrWhiteSpace($env:USERNAME)) {
        return "$env:USERDOMAIN\$env:USERNAME"
    }

    if (-not [string]::IsNullOrWhiteSpace($env:USERNAME)) {
        return $env:USERNAME
    }

    throw "Unable to resolve the current Windows user for the scheduled task principal."
}

function Remove-ChargePilotTask {
    param(
        [string]$TaskNameToRemove
    )

    $taskExists = Get-ScheduledTask -TaskName $TaskNameToRemove -ErrorAction SilentlyContinue
    if (-not $taskExists) {
        return
    }

    Unregister-ScheduledTask -TaskName $TaskNameToRemove -Confirm:$false -ErrorAction Stop | Out-Null
}

function Remove-ChargePilotFiles {
    param(
        [string]$DestinationDir,
        [string]$ConfigFilePath,
        [string]$LegacyConfigFilePath
    )

    if (Test-Path -LiteralPath $DestinationDir) {
        Remove-Item -LiteralPath $DestinationDir -Recurse -Force -ErrorAction SilentlyContinue
    }

    if (Test-Path -LiteralPath $ConfigFilePath) {
        Remove-Item -LiteralPath $ConfigFilePath -Force -ErrorAction SilentlyContinue
    }

    if (Test-Path -LiteralPath $LegacyConfigFilePath) {
        Remove-Item -LiteralPath $LegacyConfigFilePath -Force -ErrorAction SilentlyContinue
    }
}

function Sanitize-ConfigValue {
    param(
        [AllowEmptyString()]
        [string]$Value
    )

    if ($null -eq $Value) {
        return ""
    }

    return $Value.Trim().Trim("'").Trim('"')
}

function Install-ChargePilotAgent {
    param(
        [string]$DestinationDir,
        [string]$SourceScriptPath,
        [string]$ConfigFilePath,
        [string]$ServerUrlValue,
        [string]$EndpointTokenValue,
        [string]$AgentVersionValue
    )

    Remove-ChargePilotFiles -DestinationDir $DestinationDir -ConfigFilePath $ConfigFilePath -LegacyConfigFilePath $LegacyConfigPath

    New-Item -ItemType Directory -Path $DestinationDir -Force | Out-Null

    $agentDestination = Join-Path $DestinationDir "BatteryAgent.ps1"
    Copy-Item -Path $SourceScriptPath -Destination $agentDestination -Force

    $configDir = Split-Path -Parent $ConfigFilePath
    if (-not (Test-Path -Path $configDir)) {
        New-Item -ItemType Directory -Path $configDir -Force | Out-Null
    }

    $config = [ordered]@{
        serverUrl = Sanitize-ConfigValue -Value $ServerUrlValue
        endpointToken = Sanitize-ConfigValue -Value $EndpointTokenValue
        agentVersion = Sanitize-ConfigValue -Value $AgentVersionValue
    }

    $config | ConvertTo-Json -Depth 5 | Set-Content -Path $ConfigFilePath -Encoding UTF8

    Write-Host "Agent installed to: $DestinationDir"
    Write-Host "Config stored at: $ConfigFilePath"
}

$scriptPath = Join-Path $PSScriptRoot "BatteryAgent.ps1"
if (-not (Test-Path -LiteralPath $scriptPath)) {
    throw "BatteryAgent.ps1 was not found at '$scriptPath'."
}

if ($DeleteOnly) {
    Remove-ChargePilotTask -TaskNameToRemove $TaskName
    Remove-ChargePilotFiles -DestinationDir $InstallDir -ConfigFilePath $ConfigPath -LegacyConfigFilePath $LegacyConfigPath
    Write-Host "Scheduled task '$TaskName' and local agent files removed."
    return
}

if ($DeleteExisting) {
    Remove-ChargePilotTask -TaskNameToRemove $TaskName
}
else {
    $existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existingTask) {
        Remove-ChargePilotTask -TaskNameToRemove $TaskName
    }
}

Install-ChargePilotAgent -DestinationDir $InstallDir -SourceScriptPath $scriptPath -ConfigFilePath $ConfigPath -ServerUrlValue $ServerUrl -EndpointTokenValue $EndpointToken -AgentVersionValue $AgentVersion

$installedScriptPath = Join-Path $InstallDir "BatteryAgent.ps1"
$taskAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument (
    ('-NoProfile -ExecutionPolicy Bypass -File "{0}" -ServerUrl "{1}" -EndpointToken "{2}" -AgentVersion "{3}"' -f
        $installedScriptPath,
        $ServerUrl,
        $EndpointToken,
        $AgentVersion)
)

$firstRunTime = (Get-Date).AddSeconds(10)
$taskTrigger = New-ScheduledTaskTrigger -Once -At $firstRunTime -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes)
$currentTaskUser = Get-CurrentTaskUserId
$taskPrincipal = New-ScheduledTaskPrincipal -UserId $currentTaskUser -LogonType S4U -RunLevel Limited
$taskSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
$task = New-ScheduledTask -Action $taskAction -Trigger $taskTrigger -Principal $taskPrincipal -Settings $taskSettings -Description "ChargePilot battery telemetry agent"

Register-ScheduledTask -TaskName $TaskName -InputObject $task -Force | Out-Null

Write-Host "Scheduled task '$TaskName' created."
Write-Host "The agent will run after 10 seconds and then every $IntervalMinutes minutes."
Write-Host "Installed script: $installedScriptPath"
