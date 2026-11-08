# Pack an application-only update before the full OCR package is composed.
param(
    [Parameter(Mandatory=$true)][string]$SourceDir,
    [Parameter(Mandatory=$true)][string]$Destination
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$metadata = Get-Content -LiteralPath (Join-Path $SourceDir 'update-package.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ($metadata.schema -ne 1 -or $null -ne $metadata.converter) { throw 'Expected an application-only update' }
if ((Test-Path -LiteralPath (Join-Path $SourceDir 'converter.zip')) -or (Test-Path -LiteralPath (Join-Path $SourceDir 'converter-manifest.json'))) { throw 'OCR must not be included in the application-only archive' }
if (Test-Path -LiteralPath $Destination) { throw 'Application archive already exists' }
[IO.Compression.ZipFile]::CreateFromDirectory(
    [IO.Path]::GetFullPath($SourceDir),
    [IO.Path]::GetFullPath($Destination),
    [IO.Compression.CompressionLevel]::NoCompression,
    $false
)
Write-Host 'Application-only update archive created'
