[CmdletBinding()]
param(
    [string]$ServerUrl = "http://localhost:8000",
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
    param([string]$TaskNameToRemove)

    $taskExists = Get-ScheduledTask -TaskName $TaskNameToRemove -ErrorAction SilentlyContinue
    if ($taskExists) {
        Unregister-ScheduledTask -TaskName $TaskNameToRemove -Confirm:$false -ErrorAction Stop | Out-Null
    }
}

function Remove-ChargePilotFiles {
    param(
        [string]$DestinationDir,
        [string]$ConfigFilePath,
        [string]$LegacyConfigFilePath
    )

    foreach ($path in @($DestinationDir, $ConfigFilePath, $LegacyConfigFilePath)) {
        if (Test-Path -LiteralPath $path) {
            Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction Stop
        }
    }
}

function Protect-AgentCredential {
    param([string]$Value)

    $secureValue = ConvertTo-SecureString -String $Value -AsPlainText -Force
    return ConvertFrom-SecureString -SecureString $secureValue
}

function ConvertFrom-SecureInput {
    param([Security.SecureString]$Value)

    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
}

function Set-PrivateConfigPermissions {
    param([string]$ConfigDirectory, [string]$ConfigFilePath)

    $userSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $userGrant = "*${userSid}:(OI)(CI)F"
    & icacls.exe $ConfigDirectory /inheritance:r /grant:r $userGrant | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to restrict access to the ChargePilot credential directory."
    }
    if (Test-Path -LiteralPath $ConfigFilePath) {
        & icacls.exe $ConfigFilePath /inheritance:r /grant:r "*${userSid}:F" | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Unable to restrict access to the ChargePilot credential file."
        }
    }
}

function Get-EnrolledAgentConfig {
    param([string]$ServerUrlValue, [string]$ConfigFilePath, [string]$AgentVersionValue)

    if (Test-Path -LiteralPath $ConfigFilePath) {
        $existing = Get-Content -LiteralPath $ConfigFilePath -Raw | ConvertFrom-Json
        if (
            $existing.endpointId -and
            $existing.installationId -and
            $existing.protectedEndpointToken -and
            ([string]$existing.serverUrl).TrimEnd("/") -eq $ServerUrlValue.TrimEnd("/")
        ) {
            $existing.agentVersion = $AgentVersionValue
            return $existing
        }
    }

    $serverUri = [Uri]$ServerUrlValue
    $isLocalhost = $serverUri.Host -in @("localhost", "127.0.0.1", "::1")
    if ($serverUri.Scheme -ne "https" -and -not $isLocalhost) {
        throw "Enrollment requires HTTPS. Plain HTTP is allowed only for localhost development."
    }

    $secureCode = Read-Host "Paste the 24-hour ChargePilot enrollment token" -AsSecureString
    try {
        $enrollmentCode = ConvertFrom-SecureInput -Value $secureCode
    }
    finally {
        $secureCode.Dispose()
    }
    if ([string]::IsNullOrWhiteSpace($enrollmentCode)) {
        throw "An enrollment token is required."
    }

    $installationId = [guid]::NewGuid().ToString("D").ToLowerInvariant()
    $requestBody = @{
        code = $enrollmentCode
        platform = "windows"
        installation_id = $installationId
        hostname = $env:COMPUTERNAME
        device_class = "laptop"
    } | ConvertTo-Json -Compress
    $enrollmentCode = $null

    try {
        $result = Invoke-RestMethod `
            -Uri "$($ServerUrlValue.TrimEnd('/'))/api/v1/endpoint-enrollment/exchange" `
            -Method Post `
            -ContentType "application/json" `
            -Body $requestBody `
            -TimeoutSec 30
    }
    catch {
        $statusCode = $null
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
            $statusCode = [int]$_.Exception.Response.StatusCode
        }
        if ($statusCode) {
            throw "Enrollment failed with HTTP $statusCode. Check the token, expiry, server URL, and enabled platform settings."
        }
        throw "Enrollment failed: $($_.Exception.Message)"
    }
    finally {
        $requestBody = $null
    }

    if (-not $result.endpoint_id -or -not $result.installation_id -or -not $result.credential) {
        throw "The server returned an incomplete endpoint credential response."
    }

    return [pscustomobject]@{
        serverUrl = $ServerUrlValue.TrimEnd("/")
        endpointId = [string]$result.endpoint_id
        installationId = [string]$result.installation_id
        platform = "windows"
        protectedEndpointToken = Protect-AgentCredential -Value ([string]$result.credential)
        agentVersion = $AgentVersionValue
    }
}

function Install-ChargePilotAgent {
    param(
        [string]$DestinationDir,
        [string]$SourceScriptPath,
        [string]$ConfigFilePath,
        [string]$ServerUrlValue,
        [string]$AgentVersionValue
    )

    $agentConfig = Get-EnrolledAgentConfig `
        -ServerUrlValue $ServerUrlValue `
        -ConfigFilePath $ConfigFilePath `
        -AgentVersionValue $AgentVersionValue

    if (Test-Path -LiteralPath $DestinationDir) {
        Remove-Item -LiteralPath $DestinationDir -Recurse -Force -ErrorAction Stop
    }
    New-Item -ItemType Directory -Path $DestinationDir -Force | Out-Null

    $agentDestination = Join-Path $DestinationDir "BatteryAgent.ps1"
    if (-not [string]::IsNullOrWhiteSpace($SourceScriptPath) -and (Test-Path -LiteralPath $SourceScriptPath)) {
        Copy-Item -Path $SourceScriptPath -Destination $agentDestination -Force
    }
    else {
        $agentScriptUri = "$($ServerUrlValue.TrimEnd('/'))/agent/BatteryAgent.ps1"
        Invoke-WebRequest -Uri $agentScriptUri -OutFile $agentDestination -UseBasicParsing
    }

    $configDir = Split-Path -Parent $ConfigFilePath
    if (-not (Test-Path -LiteralPath $configDir)) {
        New-Item -ItemType Directory -Path $configDir -Force | Out-Null
    }

    $agentConfig | ConvertTo-Json -Depth 5 | Set-Content -Path $ConfigFilePath -Encoding UTF8
    Set-PrivateConfigPermissions -ConfigDirectory $configDir -ConfigFilePath $ConfigFilePath
    if (Test-Path -LiteralPath $LegacyConfigPath) {
        Remove-Item -LiteralPath $LegacyConfigPath -Force -ErrorAction Stop
    }

    Write-Host "Agent installed to: $DestinationDir"
    Write-Host "Per-install credential stored with Windows user protection at: $ConfigFilePath"
}

$scriptPath = if (-not [string]::IsNullOrWhiteSpace($PSScriptRoot)) {
    Join-Path $PSScriptRoot "BatteryAgent.ps1"
}
else {
    ""
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

Install-ChargePilotAgent `
    -DestinationDir $InstallDir `
    -SourceScriptPath $scriptPath `
    -ConfigFilePath $ConfigPath `
    -ServerUrlValue $ServerUrl `
    -AgentVersionValue $AgentVersion

$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Remove-ChargePilotTask -TaskNameToRemove $TaskName
}

$installedScriptPath = Join-Path $InstallDir "BatteryAgent.ps1"
$taskArguments = '-NoProfile -ExecutionPolicy Bypass -File "{0}" -ServerUrl "{1}" -AgentVersion "{2}" -ConfigPath "{3}"' -f `
    $installedScriptPath,
    $ServerUrl,
    $AgentVersion,
    $ConfigPath
$taskAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $taskArguments

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
