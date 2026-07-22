# Makes the converter portable for distribution.
#
# The converter .venv is not self-contained: it has its own python.exe but takes
# python3xx.dll and the stdlib from the base Python via 'home' in pyvenv.cfg.
# The user machine has no base Python, so we bundle a full Python 3.12 alongside
# (pyruntime) and, in production, add the converter deps from .venv/site-packages
# via PYTHONPATH (see resolveConverterCommand in main.js).
#
# Run from project root: powershell -File scripts/assemble-converter.ps1
#
# NOTE: keep this file ASCII-only. Windows PowerShell 5.1 reads .ps1 without a BOM
# as cp1251 and mangles non-ASCII, breaking the parser.

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$converter = Join-Path $root 'converter'
$venvCfg = Join-Path $converter '.venv\pyvenv.cfg'
if (-not (Test-Path $venvCfg)) { throw "converter .venv not found: $venvCfg" }

# Base Python from 'home' in pyvenv.cfg
$homeLine = Select-String -Path $venvCfg -Pattern '^home\s*=\s*(.+)$'
if (-not $homeLine) { throw "no 'home' line in pyvenv.cfg" }
$basePython = $homeLine.Matches[0].Groups[1].Value.Trim()
if (-not (Test-Path (Join-Path $basePython 'python.exe'))) {
    throw "base Python not found: $basePython"
}

$pyruntime = Join-Path $converter 'pyruntime'
if (Test-Path $pyruntime) { Remove-Item -Recurse -Force $pyruntime }
Write-Host "Copying Python 3.12: $basePython -> $pyruntime"
Copy-Item -Recurse -Force $basePython $pyruntime

# Launcher: backend sources are absent in production, ship a copy next to converter
$launcherSrc = Join-Path $root 'python-backend\app\run_converter.py'
Copy-Item -Force $launcherSrc (Join-Path $converter 'run_converter.py')

Write-Host "Done: pyruntime assembled, run_converter.py copied into converter\"
