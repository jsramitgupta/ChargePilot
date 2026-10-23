[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$OutputPath,
    [string]$AgentVersion = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ($env:OS -ne "Windows_NT") {
    throw "Set OS=Windows_NT and build this executable on a Windows runner."
}

$dotnet = Get-Command dotnet -ErrorAction SilentlyContinue
if (-not $dotnet) {
    throw "Install the .NET 10 SDK before building the ChargePilot Windows agent."
}
if ([string]::IsNullOrWhiteSpace($AgentVersion)) {
    $AgentVersion = (Get-Content -Raw (Join-Path $PSScriptRoot "../VERSION")).Trim()
}

$projectPath = Join-Path $PSScriptRoot "ChargePilotAgent.csproj"
$outputFullPath = [System.IO.Path]::GetFullPath($OutputPath)
$outputDirectory = Split-Path -Parent $outputFullPath
$publishDirectory = Join-Path ([System.IO.Path]::GetTempPath()) "ChargePilotAgent-$([guid]::NewGuid().ToString('N'))"

try {
    New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
    & $dotnet.Source publish $projectPath `
        --configuration Release `
        --runtime win-x64 `
        --self-contained true `
        "-p:Version=$AgentVersion" `
        "-p:EnableWindowsTargeting=true" `
        --output $publishDirectory
    if ($LASTEXITCODE -ne 0) {
        throw "The .NET publish command failed with exit code $LASTEXITCODE."
    }

    $publishedExecutable = Join-Path $publishDirectory "ChargePilotAgent.exe"
    if (-not (Test-Path -LiteralPath $publishedExecutable)) {
        throw "The .NET publish output did not contain ChargePilotAgent.exe."
    }

    Copy-Item -LiteralPath $publishedExecutable -Destination $outputFullPath -Force
    $bytes = [System.IO.File]::ReadAllBytes($outputFullPath)
    if ($bytes.Length -lt 256 -or $bytes[0] -ne 0x4D -or $bytes[1] -ne 0x5A) {
        throw "The generated file does not have a valid Windows executable header."
    }

    $peOffset = [BitConverter]::ToInt32($bytes, 0x3C)
    if ($peOffset -lt 64 -or $peOffset + 4 -gt $bytes.Length -or
        $bytes[$peOffset] -ne 0x50 -or $bytes[$peOffset + 1] -ne 0x45 -or
        $bytes[$peOffset + 2] -ne 0 -or $bytes[$peOffset + 3] -ne 0) {
        throw "The generated file does not contain a valid Windows PE header."
    }

    Write-Output "Built self-contained Windows service and UI: $outputFullPath"
}
finally {
    if (Test-Path -LiteralPath $publishDirectory) {
        Remove-Item -LiteralPath $publishDirectory -Recurse -Force
    }
}
