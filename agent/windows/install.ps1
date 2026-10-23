[CmdletBinding()]
param(
    [string]$AgentVersion = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$serverUrl = "https://api-chargepilot.endusercompute.in"

$temporaryExecutable = Join-Path `
    ([System.IO.Path]::GetTempPath()) `
    "ChargePilotAgent-$([guid]::NewGuid().ToString('N')).exe"

try {
    $downloadUrl = "$($ServerUrl.TrimEnd('/'))/agent/ChargePilotAgent.exe"
    Invoke-WebRequest -Uri $downloadUrl -OutFile $temporaryExecutable -UseBasicParsing
    if (-not (Test-Path -LiteralPath $temporaryExecutable)) {
        throw "The ChargePilot Windows agent executable could not be downloaded."
    }

    $fileInfo = Get-Item -LiteralPath $temporaryExecutable
    if ($fileInfo.Length -lt 256 -or $fileInfo.Length -gt 250MB) {
        throw "The downloaded ChargePilot agent has an invalid file size."
    }
    $stream = [System.IO.File]::OpenRead($temporaryExecutable)
    try {
        $header = New-Object byte[] 64
        $bytesRead = $stream.Read($header, 0, $header.Length)
        if ($bytesRead -lt $header.Length -or $header[0] -ne 0x4D -or $header[1] -ne 0x5A) {
            throw "The downloaded ChargePilot agent is not a valid Windows executable."
        }
        $peOffset = [BitConverter]::ToInt32($header, 0x3C)
        if ($peOffset -lt 64) {
            throw "The downloaded ChargePilot agent has an invalid PE header offset."
        }
        $stream.Position = $peOffset
        $peSignature = New-Object byte[] 4
        if ($stream.Read($peSignature, 0, $peSignature.Length) -ne 4 -or
            $peSignature[0] -ne 0x50 -or $peSignature[1] -ne 0x45 -or
            $peSignature[2] -ne 0 -or $peSignature[3] -ne 0) {
            throw "The downloaded ChargePilot agent is not a valid Windows PE executable."
        }
    }
    finally {
        $stream.Dispose()
    }

    $arguments = 'ui --agent-version "{0}"' -f $AgentVersion
    Start-Process `
        -FilePath $temporaryExecutable `
        -ArgumentList $arguments `
        -Verb RunAs `
        -Wait
}
finally {
    if (Test-Path -LiteralPath $temporaryExecutable) {
        Remove-Item -LiteralPath $temporaryExecutable -Force -ErrorAction SilentlyContinue
    }
}
