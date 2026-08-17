# Builds a SHA-256 manifest of the packed application (release\win-unpacked).
#
# Why: a half-written file on the target machine is indistinguishable from a
# healthy one until something refuses to start. A truncated SberAct.exe, for
# instance, makes Windows say "unsupported 16-bit application" (error 193,
# BAD_EXE_FORMAT) - the message points nowhere near the real cause. With this
# manifest on the flash drive, "Check install.cmd" answers the question in
# seconds, before and after a reinstall.
#
# The converter is skipped on purpose: it ships as converter.zip (per-file CRC,
# verified on extraction) and hashing 3.6 GB from a flash drive is pointless.
#
# Run from project root: powershell -File scripts/make-install-manifest.ps1
#
# NOTE: keep this file ASCII-only. Windows PowerShell 5.1 reads a .ps1 without a
# BOM as cp1251 and mangles non-ASCII, breaking the parser.

param(
    [string]$Source,
    [string]$OutFile
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (-not $Source)  { $Source  = Join-Path $root 'release\win-unpacked' }
if (-not $OutFile) { $OutFile = Join-Path $root 'release\install-manifest.txt' }

if (-not (Test-Path $Source)) { throw "packed app not found: $Source" }

$version = (Get-Content (Join-Path $root 'package.json') -Raw | ConvertFrom-Json).version

$files = Get-ChildItem $Source -Recurse -File |
    Where-Object { $_.FullName -notlike '*\resources\converter\*' } |
    Sort-Object FullName

$lines = New-Object System.Collections.Generic.List[string]
$lines.Add("# SberAct install manifest")
$lines.Add("# version=$version")
$lines.Add("# built=" + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
$lines.Add("# format: sha256 <TAB> size <TAB> path relative to install dir")

$prefix = (Resolve-Path $Source).Path.TrimEnd('\') + '\'
$total = 0
foreach ($f in $files) {
    $rel = $f.FullName.Substring($prefix.Length)
    # -LiteralPath is mandatory: the package contains [Content_Types].xml, and
    # without it the brackets are taken as a wildcard - Get-FileHash then quietly
    # yields an empty hash and the target machine reports a defect that is not there.
    $sha = (Get-FileHash -LiteralPath $f.FullName -Algorithm SHA256).Hash
    if (-not $sha) { throw "cannot hash: $($f.FullName)" }
    $lines.Add("$sha`t$($f.Length)`t$rel")
    $total += $f.Length
}

# UTF-8 without BOM: the checker reads it with an explicit encoding, and paths
# here are ASCII anyway.
[System.IO.File]::WriteAllLines($OutFile, $lines, (New-Object System.Text.UTF8Encoding($false)))
Write-Host ("Manifest: {0}  ({1} files, {2:N0} bytes)" -f $OutFile, $files.Count, $total)
