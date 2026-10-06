#Requires -Version 5.1
<#
.SYNOPSIS
    ChargePilot battery telemetry agent.

.DESCRIPTION
    Reads battery/AC state, decides the desired charger switch state, and posts
    telemetry to the ChargePilot server.

    Setting precedence: explicit command-line parameter > agent-config.json > error.
    Exit codes: 0 = sent (or skipped: no battery), 1 = failed (visible in Task Scheduler "Last Run Result").
#>
[CmdletBinding()]
param(
    [string]$ServerUrl,
    [string]$EndpointToken,
    [string]$AgentVersion,
    [string]$ConfigPath = (Join-Path $env:ProgramData "ChargePilot\agent-config.json"),
    [ValidateRange(0, 300)][int]$MaxJitterSeconds = 15,
    [ValidateRange(0, 100)][int]$LowThreshold = 79,    # at or below -> switch ON (charge)
    [ValidateRange(0, 100)][int]$HighThreshold = 99    # at or above -> switch OFF (stop charging)
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$script:LogPath = Join-Path $env:ProgramData "ChargePilot\logs\agent.log"
$script:LogMaxBytes = 1MB

# ---------------------------------------------------------------- logging
function Write-Log {
    param(
        [Parameter(Mandatory)][string]$Message,
        [ValidateSet("INFO", "WARN", "ERROR")][string]$Level = "INFO"
    )

    $line = "{0} [{1}] {2}" -f (Get-Date).ToString("yyyy-MM-dd HH:mm:ss"), $Level, $Message
    Write-Host $line

    # Logging must never be the reason the agent fails.
    try {
        $dir = Split-Path -Parent $script:LogPath
        if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }

        if ((Test-Path $script:LogPath) -and (Get-Item $script:LogPath).Length -gt $script:LogMaxBytes) {
            Move-Item -Path $script:LogPath -Destination "$($script:LogPath).1" -Force
        }
        Add-Content -Path $script:LogPath -Value $line -Encoding UTF8
    }
    catch { }
}

# ---------------------------------------------------------------- config
function Read-ConfigFile {
    param([string]$Path)

    $result = @{}
    if (-not (Test-Path -Path $Path)) { return $result }

    try {
        $json = Get-Content -Path $Path -Raw | ConvertFrom-Json
        foreach ($key in "serverUrl", "endpointToken", "agentVersion") {
            $prop = $json.PSObject.Properties[$key]
            if ($prop -and -not [string]::IsNullOrWhiteSpace([string]$prop.Value)) {
                $result[$key] = [string]$prop.Value
            }
        }
    }
    catch {
        Write-Log "Config file '$Path' is unreadable or invalid: $($_.Exception.Message)" "WARN"
    }
    return $result
}

function Resolve-Setting {
    param([string]$CliValue, [hashtable]$FileConfig, [string]$Key, [string]$Default = "")

    if (-not [string]::IsNullOrWhiteSpace($CliValue)) { return $CliValue }
    if ($FileConfig.ContainsKey($Key)) { return $FileConfig[$Key] }
    return $Default
}

# ---------------------------------------------------------------- system info
function Get-IpAddress {
    # Prefer the interface that owns the default route (skips Docker/VPN/virtual adapters).
    try {
        $route = Get-NetRoute -DestinationPrefix "0.0.0.0/0" -ErrorAction Stop |
            Sort-Object { $_.RouteMetric + $_.InterfaceMetric } |
            Select-Object -First 1

        if ($route) {
            $ip = Get-NetIPAddress -InterfaceIndex $route.ifIndex -AddressFamily IPv4 -ErrorAction Stop |
                Where-Object { $_.IPAddress -notmatch "^169\.254\." } |
                Select-Object -First 1
            if ($ip) { return $ip.IPAddress }
        }
    }
    catch { }

    try {
        $ip = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
            Where-Object { $_.IPAddress -notmatch "^(127\.|169\.254\.)" } |
            Select-Object -First 1
        if ($ip) { return $ip.IPAddress }
    }
    catch { }

    return "0.0.0.0"
}

if (-not ("ChargePilot.NativePower" -as [type])) {
    Add-Type -TypeDefinition @"
using System.Runtime.InteropServices;
namespace ChargePilot {
    [StructLayout(LayoutKind.Sequential)]
    public struct PowerStatus {
        public byte ACLineStatus;
        public byte BatteryFlag;
        public byte BatteryLifePercent;
        public byte SystemStatusFlag;
        public int BatteryLifeTime;
        public int BatteryFullLifeTime;
    }
    public static class NativePower {
        [DllImport("kernel32.dll", SetLastError = true)]
        public static extern bool GetSystemPowerStatus(out PowerStatus status);
    }
}
"@
}

function Get-BatteryStatusFromCim {
    $battery = Get-CimInstance Win32_Battery -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $battery) { return $null }

    $code = if ($null -ne $battery.BatteryStatus) { [int]$battery.BatteryStatus } else { 0 }
    $percent = if ($null -ne $battery.EstimatedChargeRemaining) { [int]$battery.EstimatedChargeRemaining } else { $null }

    # Win32_Battery.BatteryStatus: 2 = AC, 3 = fully charged, 6-9 = charging, 11 = partially charged
    return @{
        HasBattery        = $true
        BatteryPercentage = $percent
        Charging          = [bool]($code -in 6, 7, 8, 9)
        AcConnected       = [bool]($code -in 2, 3, 6, 7, 8, 9, 11)
    }
}

function Get-BatteryStatus {
    # Primary: GetSystemPowerStatus (what Windows itself uses; reliable AC detection).
    try {
        $s = New-Object ChargePilot.PowerStatus
        if ([ChargePilot.NativePower]::GetSystemPowerStatus([ref]$s)) {
            if (($s.BatteryFlag -band 128) -or $s.BatteryFlag -eq 255) {
                # 128 = no system battery, 255 = unknown. Confirm via CIM before giving up.
                $cim = Get-BatteryStatusFromCim
                if (-not $cim) { return @{ HasBattery = $false } }
                return $cim
            }

            $percent = if ($s.BatteryLifePercent -le 100) { [int]$s.BatteryLifePercent } else { $null }
            if ($null -eq $percent) {
                $cim = Get-BatteryStatusFromCim
                if ($cim) { $percent = $cim.BatteryPercentage }
            }

            return @{
                HasBattery        = $true
                BatteryPercentage = $percent
                Charging          = [bool]($s.BatteryFlag -band 8)
                AcConnected       = [bool]($s.ACLineStatus -eq 1)
            }
        }
    }
    catch {
        Write-Log "GetSystemPowerStatus failed, falling back to WMI: $($_.Exception.Message)" "WARN"
    }

    $fallback = Get-BatteryStatusFromCim
    if ($fallback) { return $fallback }
    return @{ HasBattery = $false }
}

function Get-SwitchState {
    param([int]$BatteryPercentage)

    if ($BatteryPercentage -ge $HighThreshold) { return $false }
    if ($BatteryPercentage -le $LowThreshold) { return $true }
    return $null    # inside the hysteresis band: server keeps the current state
}

# ---------------------------------------------------------------- transport
function Send-Telemetry {
    param(
        [string]$Uri,
        [hashtable]$Headers,
        [string]$Body,
        [int]$MaxAttempts = 3
    )

    $bytes = [Text.Encoding]::UTF8.GetBytes($Body)

    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        try {
            return Invoke-RestMethod -Uri $Uri -Method Post -Headers $Headers -Body $bytes `
                -ContentType "application/json; charset=utf-8" -TimeoutSec 30
        }
        catch {
            $statusCode = $null
            $resp = $_.Exception.PSObject.Properties["Response"]
            if ($resp -and $resp.Value) { $statusCode = [int]$resp.Value.StatusCode }

            # Retry network errors, 408, 429 and 5xx. Fail fast on other 4xx (bad token, bad payload).
            $retryable = ($null -eq $statusCode) -or ($statusCode -ge 500) -or ($statusCode -in 408, 429)
            if (-not $retryable -or $attempt -eq $MaxAttempts) { throw }

            $delay = [math]::Pow(2, $attempt) + (Get-Random -Minimum 0 -Maximum 3)
            Write-Log "Attempt $attempt failed ($($_.Exception.Message)); retrying in ${delay}s." "WARN"
            Start-Sleep -Seconds $delay
        }
    }
}

# ---------------------------------------------------------------- main
function Invoke-Agent {
    $fileConfig = Read-ConfigFile -Path $ConfigPath

    $server = (Resolve-Setting $ServerUrl $fileConfig "serverUrl").TrimEnd("/")
    $token = Resolve-Setting $EndpointToken $fileConfig "endpointToken"
    $version = Resolve-Setting $AgentVersion $fileConfig "agentVersion" "1.0.0"

    if ([string]::IsNullOrWhiteSpace($server) -or [string]::IsNullOrWhiteSpace($token)) {
        Write-Log "ServerUrl/EndpointToken missing. Provide them as parameters or in '$ConfigPath'." "ERROR"
        return 1
    }

    $uri = $null
    if (-not [Uri]::TryCreate($server, [UriKind]::Absolute, [ref]$uri) -or $uri.Scheme -notin "http", "https") {
        Write-Log "ServerUrl '$server' is not a valid http(s) URL." "ERROR"
        return 1
    }
    if ($uri.Scheme -eq "http" -and $uri.Host -notin "localhost", "127.0.0.1", "::1") {
        Write-Log "ServerUrl uses plain HTTP; the bearer token is sent unencrypted. Use HTTPS." "WARN"
    }

    # Older Windows PowerShell defaults to TLS 1.0/1.1 on some builds.
    try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch { }

    $status = Get-BatteryStatus
    if (-not $status.HasBattery -or $null -eq $status.BatteryPercentage) {
        Write-Log "No usable battery detected (desktop/VM?); nothing to report."
        return 0
    }

    # Spread fleet check-ins so thousands of endpoints don't hit the server on the same second.
    if ($MaxJitterSeconds -gt 0) { Start-Sleep -Seconds (Get-Random -Minimum 0 -Maximum ($MaxJitterSeconds + 1)) }

    $payload = [ordered]@{
        hostname           = $env:COMPUTERNAME
        ip_address         = Get-IpAddress
        battery_percentage = $status.BatteryPercentage
        charging           = $status.Charging
        ac_connected       = $status.AcConnected
        switch_state       = Get-SwitchState -BatteryPercentage $status.BatteryPercentage
        timestamp          = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
        agent_version      = $version
    }

    try {
        $response = Send-Telemetry -Uri "$server/api/v1/telemetry" `
            -Headers @{ Authorization = "Bearer $token" } `
            -Body ($payload | ConvertTo-Json -Compress)

        Write-Log ("Telemetry sent: battery={0}% charging={1} ac={2} switch={3} server_status={4}" -f
            $payload.battery_percentage, $payload.charging, $payload.ac_connected, $payload.switch_state, $response.status)
        return 0
    }
    catch {
        Write-Log "Failed to send telemetry: $($_.Exception.Message)" "ERROR"
        return 1
    }
}

try { $code = Invoke-Agent }
catch {
    Write-Log "Unhandled error: $($_.Exception.Message)" "ERROR"
    $code = 1
}
exit $code
