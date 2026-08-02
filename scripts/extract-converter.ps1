# Unpacks converter.zip into the installed app (called from installer.nsh).
#
# Why an archive instead of a plain folder: the converter is ~37 000 files. On a
# USB flash drive (exFAT) that copies at ~0.14 MB/s - hours - and any interruption
# leaves a half-populated folder that the app only notices at first conversion.
# One archive writes sequentially (~12x faster here), carries a CRC per entry, and
# cannot be "half installed": extraction either succeeds or fails loudly.
#
# NOTE: keep this file ASCII-only. Windows PowerShell 5.1 reads .ps1 without a BOM
# as cp1251 and mangles non-ASCII, breaking the parser.

param(
    [Parameter(Mandatory = $true)][string]$Zip,
    # Parent folder: the archive holds a top-level converter\ directory.
    [Parameter(Mandatory = $true)][string]$Dest
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $Zip)) { throw "archive not found: $Zip" }
if (-not (Test-Path -LiteralPath $Dest)) { New-Item -ItemType Directory -Force $Dest | Out-Null }

Add-Type -AssemblyName System.IO.Compression.FileSystem

$target = Join-Path $Dest 'converter'
# Leftovers from a previous, possibly truncated install must not survive: a stale
# file would keep its old size and silently shadow the new one.
if (Test-Path -LiteralPath $target) {
    Write-Host "Removing previous converter..."
    Remove-Item -LiteralPath $target -Recurse -Force
}

$archive = [System.IO.Compression.ZipFile]::OpenRead($Zip)
try {
    $entries = $archive.Entries
    $total = $entries.Count
    Write-Host "Extracting $total entries..."
    $done = 0
    $nextReport = 5
    foreach ($e in $entries) {
        $destPath = Join-Path $Dest $e.FullName
        if ([string]::IsNullOrEmpty($e.Name)) {
            # Directory entry.
            if (-not (Test-Path -LiteralPath $destPath)) {
                New-Item -ItemType Directory -Force $destPath | Out-Null
            }
        } else {
            $parent = Split-Path -Parent $destPath
            if (-not (Test-Path -LiteralPath $parent)) {
                New-Item -ItemType Directory -Force $parent | Out-Null
            }
            [System.IO.Compression.ZipFileExtensions]::ExtractToFile($e, $destPath, $true)
        }
        $done++
        $pct = [int](100 * $done / $total)
        if ($pct -ge $nextReport) {
            Write-Host "  $pct% ($done/$total)"
            $nextReport = $pct + 5
        }
    }
} finally {
    $archive.Dispose()
}

# Same gate as stage-usb.ps1: without these the app reports "converter not found"
# and the user has no idea why.
$required = @(
    'main.py',
    'run_converter.py',
    'docling_dev\api.py',
    'pyruntime\python.exe',
    '.venv\Lib\site-packages',
    'vendor\tesseract\tesseract.exe',
    'models\docling'
)
$missing = @($required | Where-Object { -not (Test-Path -LiteralPath (Join-Path $target $_)) })
if ($missing.Count -gt 0) {
    throw ("Extracted converter is incomplete. Missing: " + ($missing -join ', '))
}

$stats = Get-ChildItem -LiteralPath $target -Recurse -File -Force | Measure-Object Length -Sum
Write-Host ("Converter installed: {0} files, {1:N2} GB" -f $stats.Count, ($stats.Sum / 1GB))
exit 0
