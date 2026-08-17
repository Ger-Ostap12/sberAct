# Проверяет целостность установленного приложения по манифесту SHA-256.
#
# Зачем: недописанный файл на целевой машине внешне неотличим от здорового —
# приложение просто «не работает». Так, обрезанный SberAct.exe Windows встречает
# сообщением «Неподдерживаемое 16-разрядное приложение» (ошибка 193), которое на
# настоящую причину не указывает никак. Скрипт отвечает на вопрос за полминуты.
#
# Файл ОБЯЗАН быть в UTF-8 С BOM: Windows PowerShell 5.1 читает .ps1 без BOM как
# cp1251 и ломает кириллицу вместе с разбором скрипта.

param(
    # Куда установлено приложение. По умолчанию — штатный путь per-user установки.
    [string]$InstallDir,
    [string]$Manifest,
    # Сколько расхождений печатать подробно.
    [int]$ShowMax = 15
)

$ErrorActionPreference = 'Stop'
if (-not $InstallDir) { $InstallDir = Join-Path $env:LOCALAPPDATA 'Programs\SberAct Document Generator' }
if (-not $Manifest)   { $Manifest   = Join-Path $PSScriptRoot 'install-manifest.txt' }

Write-Host ''
Write-Host '============================================================'
Write-Host ' Проверка установки SberAct'
Write-Host '============================================================'
Write-Host ''

if (-not (Test-Path $Manifest)) {
    Write-Host "[ОШИБКА] Не найден манифест: $Manifest"
    Write-Host 'Положи check-install.ps1 и install-manifest.txt в одну папку.'
    exit 2
}
if (-not (Test-Path $InstallDir)) {
    Write-Host "[ОШИБКА] Приложение не найдено: $InstallDir"
    Write-Host 'Если оно установлено в другое место, запусти с параметром -InstallDir "путь".'
    exit 2
}

Write-Host "Приложение: $InstallDir"
$header = Get-Content $Manifest -TotalCount 3 -Encoding UTF8
foreach ($h in $header) { if ($h -match '^#\s*(version|built)=(.+)$') { Write-Host ("Манифест:   {0} = {1}" -f $Matches[1], $Matches[2]) } }
Write-Host ''
Write-Host 'Считаю контрольные суммы (полминуты)...'

$missing  = New-Object System.Collections.Generic.List[string]
$badSize  = New-Object System.Collections.Generic.List[string]
$badHash  = New-Object System.Collections.Generic.List[string]
$checked  = 0

foreach ($line in [System.IO.File]::ReadLines($Manifest, [System.Text.Encoding]::UTF8)) {
    if ($line.StartsWith('#') -or $line.Trim() -eq '') { continue }
    $parts = $line.Split("`t")
    if ($parts.Count -lt 3) { continue }
    $sha = $parts[0]; $size = [int64]$parts[1]; $rel = $parts[2]
    $full = Join-Path $InstallDir $rel
    $checked++

    $item = Get-Item -LiteralPath $full -ErrorAction SilentlyContinue
    if (-not $item) { $missing.Add($rel); continue }
    if ($item.Length -ne $size) {
        $badSize.Add(("{0}  (ожидалось {1:N0} Б, на диске {2:N0} Б)" -f $rel, $size, $item.Length))
        continue
    }
    # Размер сошёлся — проверяем содержимое.
    if ((Get-FileHash -LiteralPath $full -Algorithm SHA256).Hash -ne $sha) { $badHash.Add($rel) }
}

function Show-Problems([string]$title, $list) {
    if ($list.Count -eq 0) { return }
    Write-Host ''
    Write-Host ("{0}: {1}" -f $title, $list.Count)
    $n = [Math]::Min($ShowMax, $list.Count)
    for ($i = 0; $i -lt $n; $i++) { Write-Host ("    " + $list[$i]) }
    if ($list.Count -gt $n) { Write-Host ("    ... и ещё " + ($list.Count - $n)) }
}

Write-Host ("Проверено файлов: {0}" -f $checked)

# Пустая папка — это НЕ повреждение: приложение удалили либо поставили в другое
# место, а каталог остался. Разница принципиальна, потому что лечение разное:
# в одном случае «поставить», в другом «освободить место и переустановить».
$notInstalled = ($checked -gt 0 -and $missing.Count -eq $checked)
if ($notInstalled) {
    Write-Host ''
    Write-Host 'ОТСУТСТВУЮТ ВСЕ ФАЙЛЫ — приложение по этому пути НЕ установлено.'
    Write-Host '(папка осталась после удаления либо установка выполнена в другое место)'
    # Настоящий путь установки, если приложение зарегистрировано в системе.
    $uninstallRoot = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall'
    $reg = Get-ChildItem $uninstallRoot -ErrorAction SilentlyContinue | ForEach-Object {
        $props = Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue
        if ($props.DisplayName -like '*SberAct*') { $props }
    }
    if ($reg) {
        foreach ($r in $reg) {
            Write-Host ''
            Write-Host ("Система знает об установке: {0}" -f $r.DisplayName)
            # InstallLocation electron-builder не пишет, зато UninstallString —
            # это полный путь к деинсталлятору, а лежит он в папке установки.
            $where = $r.InstallLocation
            if (-not $where -and $r.UninstallString -match '^"([^"]+)"') {
                $where = Split-Path -Parent $Matches[1]
            }
            if ($where) {
                Write-Host ("    путь: {0}" -f $where)
                Write-Host '    если он отличается от проверенного, перезапусти так:'
                Write-Host ('    powershell -NoProfile -ExecutionPolicy Bypass -File "check-install.ps1" -InstallDir "{0}"' -f $where)
            }
        }
    } else {
        Write-Host 'В списке установленных программ SberAct тоже нет — значит, он удалён.'
    }
}
if (-not $notInstalled) { Show-Problems 'ОТСУТСТВУЮТ' $missing }
Show-Problems 'НЕВЕРНЫЙ РАЗМЕР (файл недописан)' $badSize
Show-Problems 'НЕ СОВПАЛА КОНТРОЛЬНАЯ СУММА' $badHash

# --- Конвертер и рантайм MSVC (то, из-за чего не запускалась конвертация) -----
$conv = Join-Path $InstallDir 'resources\converter'
$convProblem = $false
if ($notInstalled) {
    # Приложения нет вовсе — отдельная строка про конвертер только сбивает с толку.
} elseif (-not (Test-Path (Join-Path $conv 'pyruntime\python.exe'))) {
    Write-Host ''
    Write-Host '--- Модуль конвертации PDF ---'
    Write-Host '    конвертер НЕ установлен (ставится из converter.zip рядом с установщиком)'
    $convProblem = $true
} else {
    Write-Host ''
    Write-Host '--- Модуль конвертации PDF ---'
    Write-Host '    конвертер на месте'
    foreach ($pair in @(
        @{ Path = Join-Path $conv 'pyruntime\msvcp140.dll';                                   Name = 'msvcp140.dll в pyruntime' },
        @{ Path = Join-Path $conv '.venv\Lib\site-packages\torch\lib\msvcp140.dll';           Name = 'msvcp140.dll в torch\lib' }
    )) {
        if (Test-Path $pair.Path) {
            Write-Host ("    {0} - есть" -f $pair.Name)
        } else {
            Write-Host ("    {0} - НЕТ" -f $pair.Name)
            $convProblem = $true
        }
    }
}

# --- Вердикт ------------------------------------------------------------------
$broken = $missing.Count + $badSize.Count + $badHash.Count
Write-Host ''
Write-Host '============================================================'
if ($notInstalled) {
    Write-Host '[РЕЗУЛЬТАТ] Приложение не установлено — проверять нечего.'
    Write-Host 'Что делать: запустить SberAct-Setup-2.0.1.exe с флешки, положив'
    Write-Host 'converter.zip в ту же папку. Нужно ~7 ГБ свободного места.'
    $code = 1
} elseif ($broken -eq 0 -and -not $convProblem) {
    Write-Host '[РЕЗУЛЬТАТ] Установка целая. Можно работать.'
    $code = 0
} elseif ($broken -eq 0) {
    Write-Host '[РЕЗУЛЬТАТ] Файлы приложения целы, но с модулем конвертации есть проблема (см. выше).'
    $code = 1
} else {
    Write-Host ("[РЕЗУЛЬТАТ] Установка повреждена: {0} файл(ов) не совпадает." -f $broken)
    Write-Host 'Что делать: закрыть приложение и все окна SberAct, освободить место'
    Write-Host 'на диске (нужно ~7 ГБ), при необходимости отключить антивирус'
    Write-Host 'и установить заново с флешки.'
    $code = 1
}
Write-Host '============================================================'
exit $code
