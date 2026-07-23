# Assembles the USB update folder (release/SberAct-Update) from a finished build.
#
# App + backend ship as the electron-updater artifacts (latest.yml + installer
# .exe + .blockmap) produced by `npx electron-builder --win` (publish: generic in
# package.json makes electron-builder emit them). The end user's app reads these
# over a local HTTP server rooted at the flash folder (see electron-app/updater.js).
#
# The converter (~6 GB, outside the NSIS payload) syncs separately by a SHA-256
# manifest: only changed/new files go into SberAct-Update/converter, and the full
# manifest (converter-manifest.json) rides along. The delta is computed against a
# stored baseline (release/converter-manifest.baseline.json) from the last build.
#
# Usage (from project root, AFTER a full build):
#   npm run build; npm run pack:backend; npx electron-builder --win; npm run stage:converter
#   powershell -ExecutionPolicy Bypass -File scripts/build-update.ps1 [-IncludeConverter]
#
# -IncludeConverter also hashes the converter (~1-2 min) and includes changed
# files. Omit it for an app-only update (converter unchanged).
#
# NOTE: keep this file ASCII-only. Windows PowerShell 5.1 reads .ps1 without a BOM
# as cp1251 and mangles non-ASCII, breaking the parser.

param(
    [switch]$IncludeConverter
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$release = Join-Path $root 'release'

$pkg = Get-Content (Join-Path $root 'package.json') -Raw | ConvertFrom-Json
$version = $pkg.version

# --- 1. Locate electron-updater artifacts ---
$yml = Join-Path $release 'latest.yml'
$exe = Join-Path $release ("SberAct-Setup-{0}.exe" -f $version)
$blockmap = "$exe.blockmap"

if (-not (Test-Path $yml)) {
    throw "Not found: $yml. Ensure 'publish' is set in package.json and run: npx electron-builder --win"
}
if (-not (Test-Path $exe)) {
    throw "Not found: $exe. Run the full build first (npm run build; npm run pack:backend; npx electron-builder --win)."
}

# --- 2. Fresh output folder ---
$outDir = Join-Path $release 'SberAct-Update'
if (Test-Path $outDir) { Remove-Item -Recurse -Force $outDir }
New-Item -ItemType Directory -Force $outDir | Out-Null

Copy-Item $yml $outDir
Copy-Item $exe $outDir
if (Test-Path $blockmap) {
    Copy-Item $blockmap $outDir
} else {
    Write-Host "WARNING: no .blockmap next to installer (differential download disabled)."
}
Write-Host ("App update staged: v{0}" -f $version)

# --- 3. Converter delta (optional) ---
$converterSrc = Join-Path $release 'converter'
$baselinePath = Join-Path $release 'converter-manifest.baseline.json'

if ($IncludeConverter) {
    if (-not (Test-Path $converterSrc)) {
        throw "Converter not found at $converterSrc. Run: npm run stage:converter"
    }

    # Converter version = submodule short SHA (meaningful), fallback to app version.
    $convVersion = $version
    try {
        $sha = (& git -C (Join-Path $root 'converter') rev-parse --short HEAD 2>$null)
        if ($sha) { $convVersion = $sha.Trim() }
    } catch { }

    Write-Host "Hashing converter (this can take a minute)..."
    $rootLen = ($converterSrc.TrimEnd('\')).Length + 1
    $manifestFiles = New-Object System.Collections.Generic.List[object]
    foreach ($f in (Get-ChildItem $converterSrc -Recurse -File)) {
        $rel = $f.FullName.Substring($rootLen).Replace('\', '/')
        if ($rel -eq 'converter-manifest.json') { continue }  # do not hash the manifest itself
        $hash = (Get-FileHash -Algorithm SHA256 -Path $f.FullName).Hash.ToLower()
        $manifestFiles.Add([pscustomobject]@{ path = $rel; sha256 = $hash; size = $f.Length })
    }
    $manifest = [pscustomobject]@{ version = $convVersion; files = $manifestFiles }

    # Diff against baseline.
    $baseByPath = @{}
    if (Test-Path $baselinePath) {
        $baseline = Get-Content $baselinePath -Raw | ConvertFrom-Json
        if ($baseline.files) {
            foreach ($bf in $baseline.files) { $baseByPath[$bf.path] = $bf.sha256 }
        }
    }

    $convOut = Join-Path $outDir 'converter'
    $changed = 0
    foreach ($mf in $manifestFiles) {
        $prev = $null
        if ($baseByPath.ContainsKey($mf.path)) { $prev = $baseByPath[$mf.path] }
        if ($prev -ne $mf.sha256) {
            $relWin = $mf.path.Replace('/', '\')
            $dst = Join-Path $convOut $relWin
            New-Item -ItemType Directory -Force (Split-Path $dst) | Out-Null
            Copy-Item (Join-Path $converterSrc $relWin) $dst
            $changed++
        }
    }

    $json = $manifest | ConvertTo-Json -Depth 5
    # Full manifest into the update folder (converter-sync treats it as truth).
    $json | Out-File -Encoding utf8 (Join-Path $outDir 'converter-manifest.json')
    # Ship the manifest inside the full-install converter too, so a first install
    # carries a baseline for future deltas.
    $json | Out-File -Encoding utf8 (Join-Path $converterSrc 'converter-manifest.json')
    # Update the baseline for the next build's delta.
    $json | Out-File -Encoding utf8 $baselinePath

    Write-Host ("Converter delta: {0} changed file(s), version {1}" -f $changed, $convVersion)
    if ($changed -eq 0) {
        if (Test-Path $convOut) { Remove-Item -Recurse -Force $convOut }
        Remove-Item -Force (Join-Path $outDir 'converter-manifest.json') -ErrorAction SilentlyContinue
        Write-Host "No converter changes -> converter omitted from update folder."
    }
} else {
    Write-Host "Converter not included (pass -IncludeConverter to check/include converter changes)."
}

Write-Host ""
Write-Host "Done. Copy this folder to the root of the USB flash drive:"
Write-Host ("  {0}" -f $outDir)
Write-Host "On the target PC: open the app -> update icon in the header -> Install and restart."
