# Makes the converter portable for distribution.
#
# The converter .venv is not self-contained: it has its own python.exe but takes
# python3xx.dll and the stdlib from the base Python via 'home' in pyvenv.cfg.
# The user machine has no base Python, so we bundle a full Python 3.12 alongside
# (pyruntime) and, in production, add the converter deps from .venv/site-packages
# via PYTHONPATH (see resolveConverterCommand in main.js).
#
# Run from project root: powershell -File scripts/assemble-converter.ps1
#   optionally: -BasePython "C:\Path\To\Python312"
#
# NOTE: keep this file ASCII-only. Windows PowerShell 5.1 reads .ps1 without a BOM
# as cp1251 and mangles non-ASCII, breaking the parser.

param(
    # Base Python 3.12 x64 to bundle. Default: 'home' from pyvenv.cfg, then any
    # local 3.12. Needed because pyvenv.cfg points at the BUILD machine's Python,
    # which does not exist on another developer's box.
    [string]$BasePython
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$converter = Join-Path $root 'converter'
$venvCfg = Join-Path $converter '.venv\pyvenv.cfg'
if (-not (Test-Path $venvCfg)) { throw "converter .venv not found: $venvCfg" }

# Candidate base Pythons, in order of preference.
$candidates = New-Object System.Collections.Generic.List[string]
if ($BasePython) { $candidates.Add($BasePython.Trim()) }

$homeLine = Select-String -Path $venvCfg -Pattern '^home\s*=\s*(.+)$'
if ($homeLine) { $candidates.Add($homeLine.Matches[0].Groups[1].Value.Trim()) }

# Locally installed 3.12 (py launcher, then the default per-user location).
try {
    $pyPath = (& py -3.12 -c "import sys; print(sys.base_prefix)" 2>$null)
    if ($LASTEXITCODE -eq 0 -and $pyPath) { $candidates.Add($pyPath.Trim()) }
} catch { }
$global:LASTEXITCODE = 0
$candidates.Add((Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312'))

# First candidate that is a usable 3.12 x64 interpreter wins.
$basePython = $null
foreach ($c in $candidates) {
    if (-not $c) { continue }
    $exe = Join-Path $c 'python.exe'
    if (-not (Test-Path $exe)) { continue }
    $probe = (& $exe -c "import sys,struct; print('%d.%d %d' % (sys.version_info[0], sys.version_info[1], struct.calcsize('P')*8))" 2>$null)
    if ($LASTEXITCODE -ne 0 -or -not $probe) { $global:LASTEXITCODE = 0; continue }
    $global:LASTEXITCODE = 0
    if ($probe.Trim() -ne '3.12 64') {
        Write-Host "Skipping $c (found '$($probe.Trim())', need '3.12 64')"
        continue
    }
    $basePython = $c
    break
}
if (-not $basePython) {
    throw ("No usable base Python 3.12 x64 found. Tried: " + ($candidates -join '; ') +
           ". Install Python 3.12 x64 or pass -BasePython <dir>.")
}
Write-Host "Base Python: $basePython"

$pyruntime = Join-Path $converter 'pyruntime'
if (Test-Path $pyruntime) { Remove-Item -Recurse -Force $pyruntime }
Write-Host "Copying Python 3.12: $basePython -> $pyruntime"
Copy-Item -Recurse -Force $basePython $pyruntime

# The base Python's global site-packages (torch, gradio, scipy, ...) are NOT needed:
# converter deps come from .venv via PYTHONPATH (.venv has include-system-site-packages=false).
# Shipping them bloats the installer by gigabytes and drags in junk files that break NSIS.
# Keep only pip/setuptools essentials so the interpreter stays usable.
$sitePkgs = Join-Path $pyruntime 'Lib\site-packages'
if (Test-Path $sitePkgs) {
    $keepPrefixes = @('pip', 'setuptools', '_distutils_hack', 'pkg_resources', 'wheel')
    Get-ChildItem $sitePkgs -Force | Where-Object {
        $n = $_.Name
        $keepIt = $false
        foreach ($p in $keepPrefixes) {
            if ($n -eq $p -or $n -like "$p-*") { $keepIt = $true; break }
        }
        -not $keepIt
    } | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "Pruned pyruntime site-packages (kept pip/setuptools only)"
}

# Launcher: backend sources are absent in production, ship a copy next to converter
$launcherSrc = Join-Path $root 'python-backend\app\run_converter.py'
Copy-Item -Force $launcherSrc (Join-Path $converter 'run_converter.py')

# Smoke check: the bundled interpreter must import the converter deps through
# PYTHONPATH exactly the way the backend launches it (_converter_env in main.py).
# Without this the failure surfaces only on the user's machine as "converter not found".
$runtimeExe = Join-Path $pyruntime 'python.exe'
if (-not (Test-Path $runtimeExe)) { throw "assembled pyruntime has no python.exe: $runtimeExe" }
$sitePkgsVenv = Join-Path $converter '.venv\Lib\site-packages'
if (-not (Test-Path $sitePkgsVenv)) { throw "converter .venv site-packages not found: $sitePkgsVenv" }
$env:PYTHONPATH = $sitePkgsVenv
# User site-packages must not shadow the venv ones on the target machine.
$env:PYTHONNOUSERSITE = '1'
$probe = (& $runtimeExe -c "import torch, llama_cpp, fastapi, uvicorn; print('deps ok')" 2>&1)
$rc = $LASTEXITCODE
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
Remove-Item Env:PYTHONNOUSERSITE -ErrorAction SilentlyContinue
if ($rc -ne 0 -or "$probe" -notmatch 'deps ok') {
    throw "pyruntime cannot import converter deps: $probe"
}

Write-Host "Done: pyruntime assembled and verified, run_converter.py copied into converter\"
