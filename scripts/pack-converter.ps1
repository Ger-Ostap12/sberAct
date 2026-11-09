# Packs a complete converter from an already staged production directory.
param([Parameter(Mandatory=$true)][string]$SourceDir, [Parameter(Mandatory=$true)][string]$Zip, [Parameter(Mandatory=$true)][string]$ManifestFile, [string]$RuntimeDir)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$source = [IO.Path]::GetFullPath($SourceDir).TrimEnd('\')
if (Test-Path -LiteralPath $Zip) { throw "Archive already exists: $Zip" }
$manifest = Get-Content -LiteralPath $ManifestFile -Raw -Encoding UTF8 | ConvertFrom-Json
$packed = 0
$progress = [Diagnostics.Stopwatch]::StartNew()
$archive = [IO.Compression.ZipFile]::Open($Zip, [IO.Compression.ZipArchiveMode]::Create)
try {
    Write-Host ("Packing converter: {0} files" -f $manifest.files.Count)
    foreach ($file in $manifest.files) {
        if ($progress.ElapsedMilliseconds -gt 2000) {
            Write-Host ("Packing converter: {0}/{1} files" -f $packed, $manifest.files.Count)
            $progress.Restart()
        }
        $entry = $archive.CreateEntry('converter/' + $file.path, [IO.Compression.CompressionLevel]::Optimal)
        $sourceFile = Join-Path $source $file.path
        if ($RuntimeDir -and ($file.path -match '^(pyruntime|\.venv/Lib/site-packages/torch/lib)/([^/]+\.dll)$')) {
            $runtimeFile = Join-Path $RuntimeDir $matches[2]
            if (Test-Path -LiteralPath $runtimeFile -PathType Leaf) { $sourceFile = $runtimeFile }
        }
        $input = [IO.File]::OpenRead($sourceFile)
        $output = $entry.Open()
        $hash = [Security.Cryptography.SHA256]::Create()
        $stream = New-Object Security.Cryptography.CryptoStream($output, $hash, [Security.Cryptography.CryptoStreamMode]::Write)
        try {
            if ($input.Length -ne $file.size) { throw "Source size changed: $($file.path)" }
            $input.CopyTo($stream)
            $stream.FlushFinalBlock()
            $actual = ([BitConverter]::ToString($hash.Hash)).Replace('-','').ToLowerInvariant()
            if ($actual -ne $file.sha256) { throw "Source changed while packing: $($file.path)" }
        } finally { $input.Dispose(); $stream.Dispose(); $output.Dispose(); $hash.Dispose() }
        $packed++
    }
    $entry = $archive.CreateEntry('converter/converter-manifest.json')
    $output = $entry.Open()
    try {
        $bytes = [IO.File]::ReadAllBytes($ManifestFile)
        $output.Write($bytes, 0, $bytes.Length)
    } finally { $output.Dispose() }
} finally { $archive.Dispose() }
