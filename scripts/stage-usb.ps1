# Готовит папку converter/ рядом с установщиком для раздачи на флешке.
#
# Конвертер не вшивается в exe (лимит NSIS 4 ГБ) — он едет отдельной папкой
# рядом с установщиком, а installer.nsh копирует его в приложение при установке.
# Здесь копируем converter/ (с pyruntime) в release/converter/, отсекая мусор.
#
# Запуск из корня: powershell -File scripts/stage-usb.ps1
# NOTE: ASCII-only (PowerShell 5.1 без BOM ломает кириллицу).

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$src = Join-Path $root 'converter'
$dst = Join-Path $root 'release\converter'
if (-not (Test-Path $src)) { throw "converter/ not found: $src" }
if (Test-Path $dst) { Remove-Item -Recurse -Force $dst }

Write-Host "Staging converter -> release\converter (this copies several GB)..."
# robocopy: fast, handles large trees; exclude build junk. Exit codes 0-7 are success.
robocopy $src $dst /E /XD __pycache__ tests pdf_to_convert /XF *.pyc *.log /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed with code $LASTEXITCODE" }

# .part файлы моделей (куски для склейки) в дистрибутив не нужны
$models = Join-Path $dst 'models'
if (Test-Path $models) {
    Get-ChildItem $models -Filter '*.part*' -Force -EA SilentlyContinue | Remove-Item -Force -EA SilentlyContinue
}
$global:LASTEXITCODE = 0
Write-Host "Done: release\converter ready for USB (place next to SberAct-Setup exe)"
