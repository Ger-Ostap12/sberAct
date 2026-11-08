# Reassemble the downloaded Release assets into an offline SberAct-Update folder.
param([string]$Directory = $PSScriptRoot)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath($Directory).TrimEnd('\')
$component = Get-Content -LiteralPath (Join-Path $root 'ocr-assets.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$package = Get-Content -LiteralPath (Join-Path $root 'update-package.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ($package.schema -ne 1 -or $package.converter.archive -ne 'converter.zip' -or $package.converter.version -ne $component.version) { throw 'Invalid update metadata' }
$expected = @($package.files | Where-Object { $_.path -eq 'converter.zip' })
if ($expected.Count -ne 1 -or $expected[0].sha256 -ne $component.archive.sha256 -or $expected[0].size -ne $component.archive.size) { throw 'OCR metadata mismatch' }
$archive = Join-Path $root 'converter.zip'
$pending = Join-Path $root ('converter.pending-' + [guid]::NewGuid() + '.zip')
if (Test-Path -LiteralPath $archive) {
    if ((Get-Item -LiteralPath $archive).Length -ne $component.archive.size -or (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $component.archive.sha256) { throw 'Existing converter.zip differs; use a separate folder' }
} else {
    $output = [IO.File]::Open($pending, [IO.FileMode]::CreateNew)
    try {
        $index = 0
        foreach ($part in $component.parts) {
            $name = 'converter.zip.part-' + $index.ToString('000')
            if ($part.name -ne $name -or $part.sha256 -notmatch '^[a-fA-F0-9]{64}$') { throw 'Invalid OCR part metadata' }
            $file = Join-Path $root $name
            Write-Host "Checking and joining: $name"
            if ((Get-Item -LiteralPath $file).Length -ne $part.size -or (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ne $part.sha256) { throw "OCR part differs: $name" }
            $input = [IO.File]::OpenRead($file)
            try { $input.CopyTo($output) } finally { $input.Dispose() }
            $index++
        }
    } finally { $output.Dispose() }
    if ((Get-Item -LiteralPath $pending).Length -ne $component.archive.size -or (Get-FileHash -LiteralPath $pending -Algorithm SHA256).Hash -ne $component.archive.sha256) { throw 'Combined OCR archive differs' }
    Move-Item -LiteralPath $pending -Destination $archive
}
foreach ($file in $package.files) {
    if ($file.path -notmatch '^[a-zA-Z0-9_.-]+$' -or $file.path -in @('.', '..') -or $file.sha256 -notmatch '^[a-fA-F0-9]{64}$') { throw 'Invalid update file metadata' }
    $full = Join-Path $root $file.path
    if ((Get-Item -LiteralPath $full).Length -ne $file.size -or (Get-FileHash -LiteralPath $full -Algorithm SHA256).Hash -ne $file.sha256) { throw "Update file differs: $($file.path)" }
}
Write-Host 'Offline package verified. Select this folder in SberAct to update.'
