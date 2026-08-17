# Готовит папку converter/ рядом с установщиком для раздачи на флешке.
#
# Конвертер не вшивается в exe (лимит NSIS 4 ГБ) — он едет отдельной папкой
# рядом с установщиком, а installer.nsh копирует его в приложение при установке.
# Здесь копируем converter/ (с pyruntime) в release/converter/, отсекая мусор.
#
# Запуск из корня: powershell -File scripts/stage-usb.ps1
#   опционально: -Destination "D:\SberAct-dist\converter"  (когда на системном
#   диске нет 6 ГБ под staging)
#
# NOTE: ASCII-only (PowerShell 5.1 без BOM ломает кириллицу).

param(
    # Куда собирать. По умолчанию release\converter рядом с проектом.
    [string]$Destination,
    # Дополнительно упаковать результат в converter.zip рядом с папкой. Это
    # основной формат раздачи: на флешке (exFAT) 37 000 мелких файлов пишутся
    # ~0.14 МБ/с, один архив — на порядок быстрее, плюс CRC на каждый файл.
    [switch]$Zip
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$src = Join-Path $root 'converter'
$dst = if ($Destination) { $Destination } else { Join-Path $root 'release\converter' }
if (-not (Test-Path $src)) { throw "converter/ not found: $src" }

# Runtime prerequisites. Without them the installed app dies with
# "converter not found" only on the user's machine (see main.py:_converter_command).
$required = @(
    'main.py',
    'run_converter.py',
    'docling_dev\api.py',
    'pyruntime\python.exe',
    '.venv\Lib\site-packages',
    'vendor\tesseract\tesseract.exe',
    'models\docling'
)
$missingSrc = @($required | Where-Object { -not (Test-Path (Join-Path $src $_)) })
if ($missingSrc.Count -gt 0) {
    throw ("converter/ is incomplete, cannot stage. Missing: " + ($missingSrc -join ', ') +
           ". Run: npm run pack:converter (assembles pyruntime) and tools\install_offline.bat (creates .venv).")
}

if (Test-Path $dst) { Remove-Item -Recurse -Force $dst }

Write-Host "Staging converter -> $dst (this copies several GB)..."
# robocopy: fast, handles large trees; exclude build junk. Exit codes 0-7 are success.
# /R:2 /W:2 — не залипать на сбойном файле; без них обрыв тянется часами.
# node_modules нужен только для пересборки фронта конвертера; в рантайме
# main.py раздаёт готовый frontend/dist. Это ~39 000 мелких файлов — на USB
# они дают несоразмерный вклад во время копирования.
robocopy $src $dst /E /XD __pycache__ tests pdf_to_convert node_modules /XF *.pyc *.log /R:2 /W:2 /NFL /NDL /NJH /NJS /NP | Out-Null
$rc = $LASTEXITCODE
$global:LASTEXITCODE = 0
if ($rc -ge 8) { throw "robocopy failed with code $rc" }

# .part файлы моделей (куски для склейки) в дистрибутив не нужны
$models = Join-Path $dst 'models'
if (Test-Path $models) {
    Get-ChildItem $models -Filter '*.part*' -Force -EA SilentlyContinue | Remove-Item -Force -EA SilentlyContinue
}

# --- Post-check: тихо неполная раздача — главный источник битых установок ---
# robocopy может вернуть "успех" на частично скопированном дереве (обрыв USB,
# нехватка места). Сверяем и обязательные файлы, и объём: расхождение > 1%
# означает, что копия оборвалась.
$missingDst = @($required | Where-Object { -not (Test-Path (Join-Path $dst $_)) })
if ($missingDst.Count -gt 0) {
    throw ("Staging incomplete, missing in destination: " + ($missingDst -join ', '))
}

function Get-TreeStats([string]$path, [string[]]$excludeDirs) {
    $files = Get-ChildItem $path -Recurse -File -Force -EA SilentlyContinue | Where-Object {
        $rel = $_.FullName.Substring($path.TrimEnd('\').Length + 1)
        $parts = $rel.Split('\')
        $skip = $false
        foreach ($d in $excludeDirs) { if ($parts -contains $d) { $skip = $true; break } }
        if (-not $skip -and ($_.Extension -eq '.pyc' -or $_.Extension -eq '.log')) { $skip = $true }
        if (-not $skip -and $_.Name -like '*.part*' -and $rel -like 'models\*') { $skip = $true }
        -not $skip
    }
    $sum = ($files | Measure-Object Length -Sum)
    return @{ Count = $sum.Count; Bytes = [long]$sum.Sum }
}

$exclude = @('__pycache__', 'tests', 'pdf_to_convert', 'node_modules')
$srcStats = Get-TreeStats $src $exclude
$dstStats = Get-TreeStats $dst $exclude
$deltaBytes = [math]::Abs($srcStats.Bytes - $dstStats.Bytes)
$tolerance = [math]::Max(1MB, $srcStats.Bytes * 0.01)
Write-Host ("Source: {0} files, {1:N2} GB" -f $srcStats.Count, ($srcStats.Bytes / 1GB))
Write-Host ("Staged: {0} files, {1:N2} GB" -f $dstStats.Count, ($dstStats.Bytes / 1GB))
if ($deltaBytes -gt $tolerance) {
    throw ("Staging size mismatch: source {0:N2} GB vs staged {1:N2} GB. The copy was truncated." -f `
           ($srcStats.Bytes / 1GB), ($dstStats.Bytes / 1GB))
}

if (-not $Zip) {
    Write-Host "Done: $dst ready for USB (place next to SberAct-Setup exe)"
    return
}

# --- Упаковка в архив ---
# Compress-Archive не используем: в PowerShell 5.1 он держит всё дерево в памяти
# и спотыкается на многогигабайтных наборах. ZipFile пишет потоком и сам
# включает ZIP64, когда объём переваливает за 4 ГБ.
$zipPath = Join-Path (Split-Path -Parent $dst) 'converter.zip'
if (Test-Path $zipPath) { Remove-Item -Force $zipPath }
Write-Host "Packing $dst -> $zipPath (compressing, several minutes)..."
Add-Type -AssemblyName System.IO.Compression.FileSystem
# includeBaseDirectory=$true: внутри архива будет папка converter\, её и ждёт
# extract-converter.ps1 при распаковке в $INSTDIR\resources.
[System.IO.Compression.ZipFile]::CreateFromDirectory(
    $dst, $zipPath, [System.IO.Compression.CompressionLevel]::Optimal, $true)

$zipSize = (Get-Item $zipPath).Length
Write-Host ("Archive: {0:N2} GB (from {1:N2} GB)" -f ($zipSize / 1GB), ($dstStats.Bytes / 1GB))

# Сверяем состав архива с папкой: молча потерянный при упаковке файл — тот же
# класс дефекта, от которого мы уходим.
$archive = [System.IO.Compression.ZipFile]::OpenRead($zipPath)
try {
    $entryFiles = @($archive.Entries | Where-Object { $_.Name -ne '' }).Count
} finally {
    $archive.Dispose()
}
$dstFiles = (Get-ChildItem $dst -Recurse -File -Force | Measure-Object).Count
if ($entryFiles -ne $dstFiles) {
    throw "Archive is incomplete: $entryFiles entries vs $dstFiles files in $dst"
}
Write-Host "Archive verified: $entryFiles files"
Write-Host "Done: put converter.zip next to SberAct-Setup exe on the flash drive"
