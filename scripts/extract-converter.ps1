# Backwards-compatible installer entry point.
param(
    [Parameter(Mandatory=$true)][string]$Zip,
    [Parameter(Mandatory=$true)][string]$Dest
)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'converter-transaction.ps1') -Action Install -Zip $Zip -Dest $Dest
exit $LASTEXITCODE
