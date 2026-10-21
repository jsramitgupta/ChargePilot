[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$OutputPath,
    [string]$AgentVersion = "1.0.0"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ($env:OS -ne "Windows_NT") {
    throw "Build the Windows executable on Windows. Use the GitHub Actions Windows runner from macOS."
}

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Set-PSRepository -Name PSGallery -InstallationPolicy Trusted
Install-Module -Name ps2exe -RequiredVersion 1.0.18 -Scope CurrentUser -Force -AllowClobber
Import-Module ps2exe -RequiredVersion 1.0.18 -Force

$sourcePath = [System.IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..\BatteryAgent.ps1")
)
$destinationPath = [System.IO.Path]::GetFullPath($OutputPath)
$destinationDirectory = Split-Path -Parent $destinationPath

if (-not (Test-Path -LiteralPath $destinationDirectory)) {
    New-Item -ItemType Directory -Path $destinationDirectory -Force | Out-Null
}

Invoke-PS2EXE `
    -inputFile $sourcePath `
    -outputFile $destinationPath `
    -x64 `
    -title "ChargePilot Agent" `
    -description "ChargePilot Windows battery telemetry agent" `
    -company "ChargePilot" `
    -product "ChargePilot Agent" `
    -version $AgentVersion

$stream = [System.IO.File]::OpenRead($destinationPath)
try {
    $firstByte = $stream.ReadByte()
    $secondByte = $stream.ReadByte()
}
finally {
    $stream.Dispose()
}

if ($firstByte -ne 0x4D -or $secondByte -ne 0x5A) {
    throw "The generated file does not have a valid Windows executable header."
}

Write-Output "Built Windows executable: $destinationPath"
