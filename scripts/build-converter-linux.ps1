# Builds the Linux converter environment (relocatable Python + deps + code) inside
# Docker and extracts it as release-linux/converter-linux.tar.gz.
#
# Models (~1.4 GB after gemma was dropped) are NOT in the tar - platform-independent, reused
# from the Windows converter (converter/models). Copy them to the flash yourself
# (see the printed hint). tesseract is installed on the target (apt), not bundled.
#
# First run downloads torch/docling/llama wheels (~1-2 GB) - can take 15-30 min.
#
# Usage (from project root):
#   powershell -ExecutionPolicy Bypass -File scripts/build-converter-linux.ps1
#
# NOTE: keep this file ASCII-only (Windows PowerShell 5.1 reads no-BOM .ps1 as cp1251).

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$image = 'sberact-converter-linux'
$container = 'sberact-converter-extract'
$outDir = Join-Path $root 'release-linux'

Push-Location $root
try {
    Write-Host "Building Linux converter image (downloads torch/docling/llama, 15-30 min)..."
    docker build -f 'docker/converter-linux/Dockerfile' -t $image .
    if ($LASTEXITCODE -ne 0) { throw "docker build failed (exit $LASTEXITCODE)" }
}
finally {
    Pop-Location
}

New-Item -ItemType Directory -Force $outDir | Out-Null
$tar = Join-Path $outDir 'converter-linux.tar.gz'
if (Test-Path $tar) { Remove-Item -Force $tar }

# Extract the single tar (no symlinks on the Windows side -> safe docker cp).
if (docker ps -aq -f "name=^$container$") { docker rm -f $container | Out-Null }
docker create --name $container $image | Out-Null
if ($LASTEXITCODE -ne 0) { throw "docker create failed (exit $LASTEXITCODE)" }
docker cp "${container}:/out/converter-linux.tar.gz" $tar
$copyExit = $LASTEXITCODE
if (docker ps -aq -f "name=^$container$") { docker rm $container | Out-Null }
if ($copyExit -ne 0) { throw "docker cp failed (exit $copyExit)" }

if (-not (Test-Path $tar)) { throw "tar not produced: $tar" }
$sizeGb = (Get-Item $tar).Length / 1GB
Write-Host ""
Write-Host ("Done. Converter env: {0}  ({1:N2} GB)" -f $tar, $sizeGb)
Write-Host ""
Write-Host "For the flash you need (from release-linux) + models:"
Write-Host "  1) SberAct-*.AppImage"
Write-Host "  2) converter-linux.tar.gz"
Write-Host "  3) models/  (copy converter/models manually, ~1.4 GB, into release-linux/models)"
Write-Host "  + scripts/install-linux.sh"
Write-Host ""
$modelsSrc = Join-Path $root 'converter\models'
$modelsDst = Join-Path $outDir 'models'
Write-Host ("Copy models: robocopy " + $modelsSrc + " " + $modelsDst + " /E /NFL /NDL")
