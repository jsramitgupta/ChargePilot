[CmdletBinding()]
param(
    [string]$ServerUrl = "http://localhost:8000",
    [string]$EndpointToken = "test-endpoint-token",
    [string]$AgentVersion = "1.0.0",
    [string]$ConfigPath = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Normalize-ConfigValue {
    param(
        [AllowEmptyString()]
        [string]$Value
    )

    if ($null -eq $Value) {
        return ""
    }

    $trimmed = $Value.Trim()

    if ($trimmed.Length -ge 2) {
        if (($trimmed.StartsWith("'") -and $trimmed.EndsWith("'")) -or ($trimmed.StartsWith('"') -and $trimmed.EndsWith('"'))) {
            $trimmed = $trimmed.Substring(1, $trimmed.Length - 2)
        }
    }

    return $trimmed
}

function Get-AgentConfig {
    param(
        [string]$Path
    )

    $legacyConfigPath = Join-Path $env:ProgramData "ChargePilot\agent-config.json"
    $defaultConfigPath = Join-Path $env:LOCALAPPDATA "ChargePilot\agent-config.json"

    $resolvedPath = if (-not [string]::IsNullOrWhiteSpace($Path)) {
        $Path
    }
    elseif (Test-Path -LiteralPath $defaultConfigPath) {
        $defaultConfigPath
    }
    elseif (Test-Path -LiteralPath $legacyConfigPath) {
        $legacyConfigPath
    }
    else {
        $defaultConfigPath
    }

    if (Test-Path -LiteralPath $resolvedPath) {
        try {
            $config = Get-Content -LiteralPath $resolvedPath -Raw | ConvertFrom-Json
            return @{
                ServerUrl = if ($null -ne $config.serverUrl) { Normalize-ConfigValue -Value ([string]$config.serverUrl) } else { Normalize-ConfigValue -Value $ServerUrl }
                EndpointToken = if ($null -ne $config.endpointToken) { Normalize-ConfigValue -Value ([string]$config.endpointToken) } else { Normalize-ConfigValue -Value $EndpointToken }
                AgentVersion = if ($null -ne $config.agentVersion) { Normalize-ConfigValue -Value ([string]$config.agentVersion) } else { Normalize-ConfigValue -Value $AgentVersion }
            }
        }
        catch {
            Write-Warning "Unable to read config at '$resolvedPath'; falling back to parameters."
        }
    }

    return @{
        ServerUrl = Normalize-ConfigValue -Value $ServerUrl
        EndpointToken = Normalize-ConfigValue -Value $EndpointToken
        AgentVersion = Normalize-ConfigValue -Value $AgentVersion
    }
}

function Get-IpAddress {
    try {
        $adapter = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
            Where-Object { $_.IPAddress -and $_.IPAddress -notmatch "^169\.254\." } |
            Select-Object -First 1

        if ($adapter) {
            return $adapter.IPAddress
        }
    }
    catch {
        # Fall through to alternate detection.
    }

    try {
        $nic = Get-WmiObject Win32_NetworkAdapterConfiguration -Filter "IPEnabled = True" -ErrorAction Stop |
            Select-Object -First 1

        if ($nic -and $nic.IPAddress) {
            return $nic.IPAddress[0]
        }
    }
    catch {
        # Fall through to default.
    }

    return "0.0.0.0"
}

function Get-BatteryStatus {
    $battery = Get-CimInstance Win32_Battery -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $battery) {
        return @{
            BatteryPercentage = 100
            Charging = $false
            AcConnected = $false
        }
    }

    $batteryProperties = @($battery.PSObject.Properties.Name)
    $statusCode = if ($batteryProperties -contains "BatteryStatus") { [int]$battery.BatteryStatus } else { 0 }
    $powerCapabilities = @($battery.PowerManagementCapabilities)

    $batteryPercentage = if ($batteryProperties -contains "EstimatedChargeRemaining") {
        [int]$battery.EstimatedChargeRemaining
    }
    else {
        100
    }

    $charging = [bool]($statusCode -in 6, 7, 8, 9)
    $acConnected = [bool]($statusCode -eq 2 -or $powerCapabilities -contains 1)

    return @{
        BatteryPercentage = $batteryPercentage
        Charging = $charging
        AcConnected = $acConnected
    }
}

function Get-StatePath {
    $dir = Join-Path $env:LOCALAPPDATA "ChargePilot"
    if (-not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    return Join-Path $dir "switch-state.json"
}

function Get-LastSwitchState {
    $path = Get-StatePath
    if (Test-Path -LiteralPath $path) {
        try {
            $saved = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
            return [bool]$saved.switchState
        }
        catch { }
    }
    return $false   # default: false until battery reaches 30%
}

function Save-SwitchState {
    param([bool]$State)
    @{ switchState = $State } | ConvertTo-Json -Compress |
        Set-Content -LiteralPath (Get-StatePath) -Encoding UTF8
}

function Get-SwitchState {
    param(
        [int]$BatteryPercentage,
        [bool]$CurrentState = $false
    )

    if ($BatteryPercentage -le 30) { return $true }    # turn on at or below 30
    if ($BatteryPercentage -ge 90) { return $false }   # turn off at or above 90
    return $CurrentState                               # in between: hold previous state
}

$config = Get-AgentConfig -Path $ConfigPath
$ServerUrl = $config.ServerUrl
$EndpointToken = $config.EndpointToken
$AgentVersion = $config.AgentVersion

$hostname = $env:COMPUTERNAME
$ipAddress = Get-IpAddress
$status = Get-BatteryStatus
$batteryPercentage = $status.BatteryPercentage
$charging = $status.Charging
$acConnected = $status.AcConnected
$lastState   = Get-LastSwitchState
$switchState = Get-SwitchState -BatteryPercentage $batteryPercentage -CurrentState $lastState
Save-SwitchState -State $switchState

$payload = [ordered]@{
    hostname = $hostname
    ip_address = $ipAddress
    battery_percentage = $batteryPercentage
    charging = $charging
    ac_connected = $acConnected
    switch_state = $switchState
    timestamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    agent_version = $AgentVersion
}

$body = $payload | ConvertTo-Json -Compress

$headers = @{
    Authorization = "Bearer $EndpointToken"
    "Content-Type" = "application/json"
}

try {
    $uri = "$ServerUrl/api/v1/telemetry"
    $response = Invoke-RestMethod -Uri $uri -Method Post -Headers $headers -Body $body -TimeoutSec 30
    Write-Host "Telemetry sent successfully: $($response.status)"
    exit 0
}
catch {
    $message = $_.Exception.Message
    Write-Warning "Failed to send telemetry: $message"
    exit 0
}
