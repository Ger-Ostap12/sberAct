# Builds the full Linux distributable (AppImage) inside Docker and extracts the
# flat artifacts (*.AppImage, latest-linux.yml, *.blockmap) to release-linux/.
#
# Everything runs in a Linux container (backend PyInstaller + electron-builder);
# only the symlink-free .AppImage is copied to the Windows filesystem.
#
# Prereq: frontend build present (npm run build) and Docker Desktop in Linux mode.
# First run compiles Python 3.12 (reused from the cached backend stage) and does
# npm install + electron download (~10-20 min); later runs are much faster.
#
# Usage (from project root):
#   npm run build            # ensure electron-app/build is fresh
#   powershell -ExecutionPolicy Bypass -File scripts/build-linux.ps1
#
# NOTE: keep this file ASCII-only (Windows PowerShell 5.1 reads no-BOM .ps1 as cp1251).

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$image = 'sberact-linux'
$container = 'sberact-linux-extract'
$outDir = Join-Path $root 'release-linux'

if (-not (Test-Path (Join-Path $root 'electron-app/build/index.html'))) {
    throw "Frontend build missing. Run 'npm run build' first."
}

Push-Location $root
try {
    Write-Host "Building Linux image (backend stage cached; npm install + electron-builder)..."
    docker build -f 'docker/linux/Dockerfile' -t $image .
    if ($LASTEXITCODE -ne 0) { throw "docker build failed (exit $LASTEXITCODE)" }
}
finally {
    Pop-Location
}

# Clear only our own artifacts. release-linux/ is shared with
# build-converter-linux.ps1 (converter-linux.tar.gz, ~2 GB, 15-30 min to rebuild)
# and with the staged models/ - wiping the whole folder destroyed them.
New-Item -ItemType Directory -Force $outDir | Out-Null
foreach ($pattern in @('*.AppImage', '*.AppImage.blockmap', 'latest-linux.yml')) {
    Get-ChildItem $outDir -Filter $pattern -File -ErrorAction SilentlyContinue | Remove-Item -Force
}

# Extract the flat /out artifacts (no symlinks) from a throwaway container.
if (docker ps -aq -f "name=^$container$") { docker rm -f $container | Out-Null }
docker create --name $container $image | Out-Null
if ($LASTEXITCODE -ne 0) { throw "docker create failed (exit $LASTEXITCODE)" }

# docker cp of a directory's contents: copy /out then flatten.
docker cp "${container}:/out/." $outDir
$copyExit = $LASTEXITCODE
if (docker ps -aq -f "name=^$container$") { docker rm $container | Out-Null }
if ($copyExit -ne 0) { throw "docker cp failed (exit $copyExit)" }

$appimage = Get-ChildItem $outDir -Filter '*.AppImage' -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $appimage) { throw "No .AppImage produced in $outDir" }
Write-Host ""
Write-Host "Done. Linux artifacts in: $outDir"
Get-ChildItem $outDir -File | ForEach-Object { "  {0}  ({1:N1} MB)" -f $_.Name, ($_.Length / 1MB) }
