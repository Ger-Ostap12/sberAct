# Делает конвертер портируемым для дистрибутива.
#
# .venv конвертера не самодостаточен: свой python.exe есть, но python312.dll и
# стандартная библиотека берутся из базового Python по пути home в pyvenv.cfg.
# На машине пользователя базового Python нет, поэтому бандлим полноценный
# Python 3.12 рядом (pyruntime), а зависимости конвертера в проде подключаем
# из .venv/site-packages через PYTHONPATH (см. resolveConverterCommand в main.js).
#
# Запуск из корня проекта: powershell -File scripts/assemble-converter.ps1

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$converter = Join-Path $root 'converter'
$venvCfg = Join-Path $converter '.venv\pyvenv.cfg'
if (-not (Test-Path $venvCfg)) { throw ".venv конвертера не найден: $venvCfg" }

# Базовый Python — из home в pyvenv.cfg
$homeLine = Select-String -Path $venvCfg -Pattern '^home\s*=\s*(.+)$'
if (-not $homeLine) { throw "В pyvenv.cfg не найдена строка home" }
$basePython = $homeLine.Matches[0].Groups[1].Value.Trim()
if (-not (Test-Path (Join-Path $basePython 'python.exe'))) {
    throw "Базовый Python не найден: $basePython"
}

$pyruntime = Join-Path $converter 'pyruntime'
if (Test-Path $pyruntime) { Remove-Item -Recurse -Force $pyruntime }
Write-Host "Копирую Python 3.12: $basePython -> $pyruntime"
Copy-Item -Recurse -Force $basePython $pyruntime

# Лаунчер: в проде исходников бэкенда нет, кладём копию рядом с конвертером
$launcherSrc = Join-Path $root 'python-backend\app\run_converter.py'
Copy-Item -Force $launcherSrc (Join-Path $converter 'run_converter.py')

Write-Host "Готово: pyruntime собран, run_converter.py скопирован в converter\"
