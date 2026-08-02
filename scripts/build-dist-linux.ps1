# Полный сборщик Linux-комплекта: от исходников до готового носителя.
# Linux-аналог dist:win (фронт -> бэкенд -> конвертер -> установщик -> раздача).
#
# Что делает:
#   1) собирает React-фронт;
#   2) собирает AppImage в Docker (бэкенд PyInstaller + electron-builder) —
#      scripts/build-linux.ps1;
#   3) собирает окружение конвертера в Docker (tar.gz) —
#      scripts/build-converter-linux.ps1;
#   4) выкладывает модели (без кусков *.part*);
#   5) кладёт комплект на носитель вместе с install-linux.sh, Readme и SHA256SUMS;
#   6) перечитывает записанное МИМО кэша ОС и сверяет хеши.
#
# Пункт 6 — не перестраховка: Get-FileHash сразу после записи читает из кэша
# Windows и возвращает верный хеш даже с неисправного носителя (02.08 на это
# ушёл день). Настоящая проверка — только чтение с FILE_FLAG_NO_BUFFERING.
#
# Запуск из корня проекта:
#   npm run dist:linux -- -Destination F:\
#   powershell -ExecutionPolicy Bypass -File scripts/build-dist-linux.ps1 -Destination D:\SberAct-linux
#
# Полезные ключи:
#   -SkipApp         не пересобирать AppImage (берём из release-linux)
#   -SkipConverter   не пересобирать конвертер (~2 ГБ, 15-30 мин на пересборку)
#   -NoVerify        не перечитывать носитель (быстро, но без гарантий)
#
# Требуется Docker Desktop в режиме Linux-контейнеров. Первый прогон
# компилирует Python 3.12 и тянет torch/docling — от 30 минут и несколько ГБ.

param(
    # Куда положить готовый комплект: буква флешки (F:\) или любая папка.
    [Parameter(Mandatory = $true)]
    [string]$Destination,
    # Где держать промежуточные артефакты. По умолчанию release-linux в проекте.
    [string]$Staging,
    [switch]$SkipApp,
    [switch]$SkipConverter,
    [switch]$NoVerify
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (-not $Staging) { $Staging = Join-Path $root 'release-linux' }

# Чтение мимо кэша ОС. Обычный Get-FileHash после записи отвечает из кэша
# Windows (сотни МБ/с) и подтверждает целостность даже там, где носитель ничего
# не сохранил. FILE_FLAG_NO_BUFFERING заставляет читать с устройства.
Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Security.Cryptography;

public static class SberActUnbufferedHash
{
    private const FileOptions NoBuffering = (FileOptions)0x20000000;

    public static string Sha256(string path)
    {
        long remaining = new FileInfo(path).Length;
        byte[] buffer = new byte[1 << 20];
        using (FileStream stream = new FileStream(path, FileMode.Open, FileAccess.Read,
                   FileShare.Read, buffer.Length, NoBuffering | FileOptions.SequentialScan))
        using (SHA256 sha = SHA256.Create())
        {
            while (remaining > 0)
            {
                int read = stream.Read(buffer, 0, buffer.Length);
                if (read <= 0) throw new IOException("Unexpected end of file: " + path);
                int use = (int)Math.Min((long)read, remaining);
                sha.TransformBlock(buffer, 0, use, null, 0);
                remaining -= use;
            }
            sha.TransformFinalBlock(new byte[0], 0, 0);
            return BitConverter.ToString(sha.Hash).Replace("-", "").ToLowerInvariant();
        }
    }
}
'@

function Write-Step([int]$n, [string]$text) {
    Write-Host ""
    Write-Host ("[{0}/6] {1}" -f $n, $text) -ForegroundColor Cyan
}

function Invoke-Checked([string]$file, [string[]]$argv, [string]$what) {
    & $file @argv
    if ($LASTEXITCODE -ne 0) { throw "$what — код возврата $LASTEXITCODE" }
}

# Текстовый файл для Linux: UTF-8 без BOM и переводы строк LF. С CRLF bash
# спотыкается на самой первой строке («bad interpreter: /usr/bin/env bash\r»),
# а BOM ломает shebang — в репозитории install-linux.sh лежит с CRLF.
function Write-LinuxText([string]$path, [string]$text) {
    $lf = $text -replace "`r`n", "`n"
    [System.IO.File]::WriteAllText($path, $lf, (New-Object System.Text.UTF8Encoding($false)))
}

function Get-FreeBytes([string]$path) {
    $qualifier = try { Split-Path -Qualifier $path } catch { $null }
    if (-not $qualifier) { return $null }
    $disk = Get-CimInstance Win32_LogicalDisk -Filter ("DeviceID='{0}'" -f $qualifier) -ErrorAction SilentlyContinue
    if ($disk) { return [long]$disk.FreeSpace }
    return $null
}

# ─────────────────────────── Проверки до сборки ───────────────────────────
Write-Step 1 "Проверка окружения"

$needDocker = (-not $SkipApp) -or (-not $SkipConverter)
if ($needDocker) {
    $dockerVersion = & docker version --format '{{.Server.Version}}' 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw ("Docker не отвечает. Запустите Docker Desktop в режиме Linux-контейнеров " +
               "и повторите (или соберите с -SkipApp -SkipConverter, если артефакты уже есть). " +
               "Ответ docker: " + ($dockerVersion -join ' '))
    }
    Write-Host "  Docker: $dockerVersion"
}

$modelsSrc = Join-Path $root 'converter\models'
if (-not (Test-Path $modelsSrc)) { throw "Нет папки моделей: $modelsSrc" }
$modelFiles = @(Get-ChildItem $modelsSrc -Recurse -File -Force | Where-Object { $_.Name -notlike '*.part*' })
if ($modelFiles.Count -eq 0) {
    throw "В $modelsSrc только куски *.part* — модели не склеены. Запустите конвертер один раз на Windows."
}
Write-Host ("  Модели: {0} файлов, {1:N2} ГБ" -f $modelFiles.Count,
            (($modelFiles | Measure-Object Length -Sum).Sum / 1GB))

$installer = Join-Path $PSScriptRoot 'install-linux.sh'
if (-not (Test-Path $installer)) { throw "Нет установщика: $installer" }

$version = (Get-Content (Join-Path $root 'package.json') -Raw | ConvertFrom-Json).version
Write-Host "  Версия: $version"

New-Item -ItemType Directory -Force $Staging | Out-Null

# ───────────────────────────── Сборка приложения ─────────────────────────────
Write-Step 2 "AppImage (фронт + бэкенд + electron-builder в Docker)"
if ($SkipApp) {
    Write-Host "  Пропущено (-SkipApp)"
} else {
    Write-Host "  Сборка React-фронта..."
    Push-Location $root
    try { Invoke-Checked 'npm.cmd' @('run', 'build') 'npm run build' }
    finally { Pop-Location }
    & (Join-Path $PSScriptRoot 'build-linux.ps1')
}
$appImage = Get-ChildItem $Staging -Filter '*.AppImage' -File -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $appImage) {
    throw "AppImage не найден в $Staging. Уберите -SkipApp, чтобы собрать его."
}
Write-Host ("  AppImage: {0} ({1:N1} МБ)" -f $appImage.Name, ($appImage.Length / 1MB))

# ───────────────────────────── Сборка конвертера ─────────────────────────────
Write-Step 3 "Окружение конвертера (Python + tesseract, tar.gz в Docker)"
if ($SkipConverter) {
    Write-Host "  Пропущено (-SkipConverter)"
} else {
    & (Join-Path $PSScriptRoot 'build-converter-linux.ps1')
}
$converterTar = Join-Path $Staging 'converter-linux.tar.gz'
if (-not (Test-Path $converterTar)) {
    throw "Нет $converterTar. Уберите -SkipConverter, чтобы собрать конвертер."
}
Write-Host ("  Конвертер: {0:N2} ГБ" -f ((Get-Item $converterTar).Length / 1GB))

# ─────────────────────────────────── Модели ───────────────────────────────────
Write-Step 4 "Модели конвертера"
$modelsStaged = Join-Path $Staging 'models'
# *.part* — куски для хранения в git, склеенный файл лежит рядом. В комплекте
# они только занимают место (и вводят в заблуждение при проверке размера).
robocopy $modelsSrc $modelsStaged /E /XF *.part* /R:2 /W:2 /NFL /NDL /NJH /NJS /NP | Out-Null
$rc = $LASTEXITCODE
$global:LASTEXITCODE = 0
if ($rc -ge 8) { throw "robocopy моделей завершился с кодом $rc" }
$stagedModelFiles = @(Get-ChildItem $modelsStaged -Recurse -File -Force)
if ($stagedModelFiles.Count -ne $modelFiles.Count) {
    throw ("Модели скопированы не полностью: {0} из {1}" -f $stagedModelFiles.Count, $modelFiles.Count)
}
Write-Host ("  Готово: {0} файлов, {1:N2} ГБ" -f $stagedModelFiles.Count,
            (($stagedModelFiles | Measure-Object Length -Sum).Sum / 1GB))

# Установщик и памятка — в staging, чтобы попасть на носитель тем же путём и с
# теми же проверками, что и остальные файлы.
Write-LinuxText (Join-Path $Staging 'install-linux.sh') (Get-Content $installer -Raw)

$readme = @"
SberAct — установка на Linux (Astra Linux 1.7 / Ubuntu), версия $version

В комплекте:
  $($appImage.Name)   — приложение
  converter-linux.tar.gz          — OCR-конвертер (Python и tesseract внутри)
  models/                         — модели конвертера
  install-linux.sh                — установщик
  SHA256SUMS                      — контрольные суммы

Установка (терминал, из папки с этими файлами):

  1. Скопируйте комплект с флешки на диск — с флешки установка идёт медленно:
       mkdir -p ~/sberact-dist && cp -r ./* ~/sberact-dist/ && cd ~/sberact-dist

  2. Проверьте, что всё доехало целым:
       sha256sum -c SHA256SUMS

  3. Установите:
       chmod +x install-linux.sh
       ./install-linux.sh $($appImage.Name) converter-linux.tar.gz models

Ярлык «SberAct Document Generator» появится в меню приложений.
Интернет не нужен — приложение и конвертер работают полностью офлайн.

Обновление только приложения (конвертер и модели сохраняются):
       ./install-linux.sh <новый>.AppImage

Удаление:
       rm -rf ~/.local/opt/SberAct ~/.local/share/applications/sberact.desktop
"@
Write-LinuxText (Join-Path $Staging 'Readme-linux.txt') ($readme + "`n")

# ────────────────────────────── Раздача на носитель ──────────────────────────────
Write-Step 5 "Запись комплекта: $Destination"

$kit = @(
    @{ Source = $appImage.FullName;                        Relative = $appImage.Name },
    @{ Source = $converterTar;                             Relative = 'converter-linux.tar.gz' },
    @{ Source = (Join-Path $Staging 'install-linux.sh');   Relative = 'install-linux.sh' },
    @{ Source = (Join-Path $Staging 'Readme-linux.txt');   Relative = 'Readme-linux.txt' }
)
foreach ($file in $stagedModelFiles) {
    $kit += @{
        Source   = $file.FullName
        Relative = 'models/' + $file.FullName.Substring($modelsStaged.Length + 1).Replace('\', '/')
    }
}

$totalBytes = ($kit | ForEach-Object { (Get-Item $_.Source).Length } | Measure-Object -Sum).Sum
$free = Get-FreeBytes $Destination
if ($null -ne $free -and $free -lt $totalBytes) {
    throw ("На {0} свободно {1:N2} ГБ, комплекту нужно {2:N2} ГБ" -f
           $Destination, ($free / 1GB), ($totalBytes / 1GB))
}
Write-Host ("  Объём комплекта: {0:N2} ГБ, файлов: {1}" -f ($totalBytes / 1GB), $kit.Count)

New-Item -ItemType Directory -Force $Destination | Out-Null
$expected = New-Object 'System.Collections.Generic.List[object]'
foreach ($item in $kit) {
    $target = Join-Path $Destination ($item.Relative -replace '/', '\')
    New-Item -ItemType Directory -Force (Split-Path -Parent $target) | Out-Null
    Write-Host ("  {0,-46} {1,8:N1} МБ" -f $item.Relative, ((Get-Item $item.Source).Length / 1MB))
    Copy-Item $item.Source $target -Force
    $expected.Add([pscustomobject]@{
        Relative = $item.Relative
        Target   = $target
        Sha256   = (Get-FileHash $item.Source -Algorithm SHA256).Hash.ToLowerInvariant()
    })
}

# SHA256SUMS в формате coreutils: на целевой машине проверяется одной командой
# `sha256sum -c SHA256SUMS`, без наших скриптов.
$sums = ($expected | ForEach-Object { "{0}  {1}" -f $_.Sha256, $_.Relative }) -join "`n"
Write-LinuxText (Join-Path $Destination 'SHA256SUMS') ($sums + "`n")

# ───────────────────────── Проверка записанного мимо кэша ─────────────────────────
Write-Step 6 "Проверка носителя (чтение мимо кэша ОС)"
if ($NoVerify) {
    Write-Host "  Пропущено (-NoVerify). Комплект не проверен — носитель может лгать." -ForegroundColor Yellow
} else {
    $qualifier = try { Split-Path -Qualifier $Destination } catch { $null }
    if ($qualifier) {
        try { Write-VolumeCache -DriveLetter $qualifier.TrimEnd(':') -ErrorAction Stop }
        catch { Write-Host "  (сброс кэша тома недоступен: $($_.Exception.Message))" }
    }
    $bad = @()
    foreach ($entry in $expected) {
        $actual = [SberActUnbufferedHash]::Sha256($entry.Target)
        $ok = ($actual -eq $entry.Sha256)
        if (-not $ok) { $bad += $entry.Relative }
        Write-Host ("  {0,-46} {1}" -f $entry.Relative, $(if ($ok) { 'OK' } else { 'ПОВРЕЖДЁН' })) `
            -ForegroundColor $(if ($ok) { 'Green' } else { 'Red' })
    }
    if ($bad.Count -gt 0) {
        throw (("Носитель отдал не то, что записано. Повреждено файлов: {0} ({1}). " +
                "Это отказ накопителя, а не сборки: возьмите другой.") -f $bad.Count, ($bad -join ', '))
    }
    Write-Host "  Все файлы прочитаны с носителя и совпали с оригиналом."
}

Write-Host ""
Write-Host ("Готово. Комплект {0} на {1}" -f $version, $Destination) -ForegroundColor Green
Write-Host "На целевой машине: sha256sum -c SHA256SUMS, затем ./install-linux.sh (см. Readme-linux.txt)"
