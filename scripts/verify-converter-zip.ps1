# Verifies a converter.zip end to end: every entry is decompressed and .NET
# checks its CRC. Run it on the flash drive AFTER copying - that is the step
# where the distribution used to break silently.
#
# Usage: powershell -File scripts\verify-converter-zip.ps1 -Zip "F:\...\converter.zip"
#
# NOTE: keep this file ASCII-only. Windows PowerShell 5.1 reads .ps1 without a BOM
# as cp1251 and mangles non-ASCII, breaking the parser.

param([Parameter(Mandatory = $true)][string]$Zip)

$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $Zip)) { throw "archive not found: $Zip" }
Add-Type -AssemblyName System.IO.Compression.FileSystem

# Same list the installer checks after extraction - a technically valid archive
# that lacks the interpreter is still a broken distribution.
$required = @(
    'converter/main.py',
    'converter/run_converter.py',
    'converter/docling_dev/api.py',
    'converter/pyruntime/python.exe',
    'converter/vendor/tesseract/tesseract.exe'
)

Write-Host ("Verifying {0} ({1:N2} GB)..." -f $Zip, ((Get-Item -LiteralPath $Zip).Length / 1GB))
$archive = [System.IO.Compression.ZipFile]::OpenRead($Zip)
$buffer = New-Object byte[] (1024 * 1024)
$bad = 0
$count = 0
$bytes = 0L
$names = @{}
try {
    foreach ($e in $archive.Entries) {
        $names[$e.FullName] = $true
        if ([string]::IsNullOrEmpty($e.Name)) { continue }
        try {
            $s = $e.Open()
            try {
                while (($n = $s.Read($buffer, 0, $buffer.Length)) -gt 0) { $bytes += $n }
            } finally { $s.Dispose() }
        } catch {
            $bad++
            Write-Host ("CORRUPT: {0} -- {1}" -f $e.FullName, $_.Exception.Message)
        }
        $count++
        if ($count % 5000 -eq 0) { Write-Host ("  checked {0} entries..." -f $count) }
    }
} finally { $archive.Dispose() }

$missing = @($required | Where-Object { -not $names.ContainsKey($_) })
Write-Host ("Checked {0} entries, {1:N2} GB uncompressed, corrupt: {2}" -f $count, ($bytes / 1GB), $bad)
if ($bad -gt 0) { throw "$bad corrupted entries - recopy the archive" }
if ($missing.Count -gt 0) { throw ("Archive lacks required files: " + ($missing -join ', ')) }
Write-Host "ARCHIVE OK"
