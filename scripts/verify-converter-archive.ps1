# Verify the published payload against the manifest, not the staging directory.
param(
    [Parameter(Mandatory=$true)][string]$Zip,
    [Parameter(Mandatory=$true)][string]$ManifestFile
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
$manifest = Get-Content -LiteralPath $ManifestFile -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $manifest.files -or $manifest.files.Count -eq 0) { throw 'Empty converter manifest' }
$expected = @{}
foreach ($file in $manifest.files) {
    if (-not $file.path -or $file.path -match '(^|/)\.\.?(/|$)|\\|^/|:' -or
        $file.path -eq 'converter-manifest.json' -or $expected.ContainsKey($file.path) -or
        $null -eq $file.size -or $file.size -lt 0 -or $file.sha256 -notmatch '^[a-fA-F0-9]{64}$') {
        throw 'Invalid converter manifest entry'
    }
    $expected[$file.path] = $file
}
$expected['converter-manifest.json'] = @{
    size = (Get-Item -LiteralPath $ManifestFile).Length
    sha256 = (Get-FileHash -LiteralPath $ManifestFile -Algorithm SHA256).Hash
}
$archive = [IO.Compression.ZipFile]::OpenRead([IO.Path]::GetFullPath($Zip))
try {
    $seen = @{}
    $progress = [Diagnostics.Stopwatch]::StartNew()
    Write-Host ("Checking converter archive: 0/{0}" -f $expected.Count)
    foreach ($entry in $archive.Entries) {
        if (-not $entry.FullName.StartsWith('converter/', [StringComparison]::Ordinal)) {
            throw "Unexpected archive root: $($entry.FullName)"
        }
        $relative = $entry.FullName.Substring(10)
        if (-not $entry.Name) { continue }
        if ($seen.ContainsKey($relative)) { throw "Duplicate archive entry: $relative" }
        if (-not $expected.ContainsKey($relative)) { throw "Unexpected archive entry: $relative" }
        $file = $expected[$relative]
        if ($entry.Length -ne $file.size) { throw "Archive size mismatch: $relative" }
        $input = $entry.Open()
        $hash = [Security.Cryptography.SHA256]::Create()
        try { $actual = ([BitConverter]::ToString($hash.ComputeHash($input))).Replace('-','') }
        finally { $input.Dispose(); $hash.Dispose() }
        if ($actual -ne $file.sha256) { throw "Archive hash mismatch: $relative" }
        $seen[$relative] = $true
        if ($progress.ElapsedMilliseconds -ge 2000) {
            Write-Host ("Checking converter archive: {0}/{1}" -f $seen.Count, $expected.Count)
            $progress.Restart()
        }
    }
    foreach ($relative in $expected.Keys) {
        if (-not $seen.ContainsKey($relative)) { throw "Archive is incomplete: $relative" }
    }
    Write-Host ("Archive verified: {0} files" -f $seen.Count)
} finally { $archive.Dispose() }
