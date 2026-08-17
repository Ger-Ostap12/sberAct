# Replaces the installer on the USB stick, safely.
#
# Why not a plain Copy-Item: the flash drive is the only distribution channel,
# and a copy that dies halfway leaves the user with no working installer at all.
# Worse, re-reading a file right after writing it usually hits the OS cache and
# "verifies" data that never reached the flash. So:
#
#   1. write next to the target as <name>.new;
#   2. read it back UNBUFFERED (FILE_FLAG_NO_BUFFERING) and compare SHA-256 with
#      the source - this bypasses the cache and really touches the medium;
#   3. only then delete the old file and rename .new into place;
#   4. verify the final file the same unbuffered way.
#
# The old installer stays intact until the new one has been proven readable.
#
# Run from project root, target dir is mandatory (it has a Cyrillic name and
# this file must stay ASCII-only - PowerShell 5.1 reads a .ps1 without a BOM as
# cp1251 and mangles non-ASCII):
#
#   powershell -File scripts/publish-usb-installer.ps1 -UsbDir "F:\<folder>"

param(
    [Parameter(Mandatory = $true)]
    [string]$UsbDir,
    # Installer to publish. Default: release\SberAct-Setup-<version>.exe
    [string]$Source
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

if (-not $Source) {
    $version = (Get-Content (Join-Path $root 'package.json') -Raw | ConvertFrom-Json).version
    $Source = Join-Path $root ("release\SberAct-Setup-{0}.exe" -f $version)
}
if (-not (Test-Path -LiteralPath $Source)) { throw "installer not found: $Source" }
if (-not (Test-Path -LiteralPath $UsbDir)) { throw "USB folder not found: $UsbDir" }

# SHA-256 over an unbuffered stream: 1 MiB chunks are sector-aligned, which
# FILE_FLAG_NO_BUFFERING demands. The trailing partial sector is allowed.
function Get-UnbufferedSha256([string]$path) {
    $NO_BUFFERING = [System.IO.FileOptions]0x20000000
    $chunk = 1MB
    $fs = New-Object System.IO.FileStream(
        $path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read,
        [System.IO.FileShare]::Read, $chunk, $NO_BUFFERING)
    try {
        $sha = [System.Security.Cryptography.SHA256]::Create()
        $buf = New-Object byte[] $chunk
        while (($read = $fs.Read($buf, 0, $chunk)) -gt 0) {
            [void]$sha.TransformBlock($buf, 0, $read, $null, 0)
        }
        [void]$sha.TransformFinalBlock((New-Object byte[] 0), 0, 0)
        return ([BitConverter]::ToString($sha.Hash) -replace '-', '')
    } finally {
        $fs.Dispose()
    }
}

$srcItem = Get-Item -LiteralPath $Source
$srcHash = (Get-FileHash -LiteralPath $Source -Algorithm SHA256).Hash
$name    = $srcItem.Name
$target  = Join-Path $UsbDir $name
$staged  = "$target.new"

Write-Host ("Source: {0}" -f $Source)
Write-Host ("        {0:N0} bytes, SHA-256 {1}" -f $srcItem.Length, $srcHash)
Write-Host ("Target: {0}" -f $target)

# Free space: the staged copy lives next to the old file, so both must fit.
$drive = (Get-Item -LiteralPath $UsbDir).PSDrive
$free = (Get-PSDrive $drive.Name).Free
$oldSize = 0
if (Test-Path -LiteralPath $target) { $oldSize = (Get-Item -LiteralPath $target).Length }
if ($free -lt $srcItem.Length + 50MB) {
    throw ("not enough free space on {0}: {1:N0} bytes free, need {2:N0}" -f $drive.Name, $free, $srcItem.Length + 50MB)
}

if (Test-Path -LiteralPath $staged) { Remove-Item -LiteralPath $staged -Force }
Write-Host 'Copying to <name>.new ...'
Copy-Item -LiteralPath $Source -Destination $staged -Force

Write-Host 'Verifying the staged copy past the OS cache ...'
$stagedHash = Get-UnbufferedSha256 $staged
if ($stagedHash -ne $srcHash) {
    Remove-Item -LiteralPath $staged -Force -ErrorAction SilentlyContinue
    throw "staged copy is corrupt (SHA-256 $stagedHash), the old installer is left untouched"
}
Write-Host 'Staged copy matches the source.'

if (Test-Path -LiteralPath $target) {
    Write-Host ("Replacing the old installer ({0:N0} bytes) ..." -f $oldSize)
    Remove-Item -LiteralPath $target -Force
}
Rename-Item -LiteralPath $staged -NewName $name

Write-Host 'Verifying the published file past the OS cache ...'
$finalHash = Get-UnbufferedSha256 $target
if ($finalHash -ne $srcHash) { throw "published file is corrupt (SHA-256 $finalHash)" }

Write-Host ''
Write-Host ("Done: {0}" -f $target)
Write-Host ("      {0:N0} bytes, SHA-256 {1}" -f (Get-Item -LiteralPath $target).Length, $finalHash)
