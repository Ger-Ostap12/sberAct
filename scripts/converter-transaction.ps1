# Installs a verified converter beside the active copy and keeps a recovery journal.
param(
    [ValidateSet('Install','Prepare','Activate','Recover','Rollback','Confirm','Status','Check')][string]$Action = 'Install',
    [Parameter(Mandatory=$true)][string]$Dest,
    [string]$Zip,
    [string]$SourceDir,
    [string]$ManifestFile,
    [ValidateRange(0,2147483647)][long]$ReserveKB = 0,
    [string]$LegacyDir
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$progressClock = [Diagnostics.Stopwatch]::StartNew()
function Write-UpdateProgress([string]$Phase, [int]$Done, [int]$Total) {
    if ($Done -eq 0 -or $Done -eq $Total -or $progressClock.ElapsedMilliseconds -ge 1000) {
        Write-Host ("{0}: {1}/{2}" -f $Phase, $Done, $Total)
        $progressClock.Restart()
    }
}
function Assert-SafePath([string]$Value) {
    $full = [IO.Path]::GetFullPath($Value).TrimEnd('\')
    if ($full -eq [IO.Path]::GetPathRoot($full).TrimEnd('\')) { throw 'Drive root is not a converter destination' }
    $cursor = $full
    while ($cursor) {
        if (Test-Path -LiteralPath $cursor) {
            if ((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "Reparse point is not supported: $cursor"
            }
        }
        $cursor = Split-Path -Parent $cursor
    }
    return $full
}
function Assert-RelativePath([string]$Value) {
    if (-not $Value -or $Value.Contains('\') -or $Value -match '(^/|[:<>\"|?*\x00-\x1f])') { throw "Invalid converter path: $Value" }
    foreach ($part in $Value.Split('/')) {
        if (-not $part -or $part -eq '.' -or $part -eq '..' -or $part.EndsWith('.') -or $part.EndsWith(' ') -or
            $part -match '^(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.|$)') { throw "Invalid converter path: $Value" }
    }
}
function Assert-Manifest($result) {
    if (-not $result.files -or $result.files.Count -eq 0) { throw 'Empty converter manifest' }
    $seen = @{}
    foreach ($item in $result.files) {
        if ($item.path -isnot [string]) { throw 'Converter path must be a string' }
        Assert-RelativePath $item.path
        if ($item.path -eq 'converter-manifest.json' -or $seen.ContainsKey($item.path) -or
            $item.sha256 -notmatch '^[a-fA-F0-9]{64}$' -or $null -eq $item.size -or
            $item.size -lt 0 -or [double]$item.size -ne [math]::Floor([double]$item.size)) { throw 'Invalid converter manifest entry' }
        $seen[$item.path] = $true
    }
    return $result
}
function Read-Manifest([string]$File) {
    return Assert-Manifest (Get-Content -LiteralPath $File -Raw -Encoding UTF8 | ConvertFrom-Json)
}
function Write-State([string]$Phase, [bool]$HadTarget) {
    $json = @{ schema=1; phase=$Phase; hadTarget=$HadTarget } | ConvertTo-Json
    [IO.File]::WriteAllText($stateTemp, $json, (New-Object Text.UTF8Encoding($false)))
    Move-Item -LiteralPath $stateTemp -Destination $stateFile -Force
}
function Remove-OwnedTree([string]$Directory) {
    $checked = Assert-SafePath $Directory
    if ($checked -ne $next -and $checked -ne $previous) { throw 'Refusing to remove a non-transaction directory' }
    if (Test-Path -LiteralPath $checked) {
        foreach ($item in Get-ChildItem -LiteralPath $checked -Force -Recurse) {
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Refusing to remove a transaction tree containing a reparse point' }
        }
        Remove-Item -LiteralPath $checked -Recurse -Force
    }
}
function Read-State {
    if (-not (Test-Path -LiteralPath $stateFile)) { return $null }
    $value = Get-Content -LiteralPath $stateFile -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($value.schema -ne 1 -or $value.phase -notin @('preparing','prepared','switching','pending','confirmed') -or
        $value.hadTarget -isnot [bool]) { throw 'Invalid converter recovery journal' }
    return $value
}
function Clear-State {
    if (Test-Path -LiteralPath $stateFile) { Remove-Item -LiteralPath $stateFile }
}
function Restore-Previous($state) {
    if (Test-Path -LiteralPath $previous) {
        if (Test-Path -LiteralPath $target) {
            Remove-OwnedTree $next
            Move-Item -LiteralPath $target -Destination $next
        }
        Move-Item -LiteralPath $previous -Destination $target
        Remove-OwnedTree $next
    } elseif (-not $state.hadTarget) {
        # There is no working older converter on a first installation.
        if (Test-Path -LiteralPath $target) {
            Remove-OwnedTree $next
            Move-Item -LiteralPath $target -Destination $next
            Remove-OwnedTree $next
        }
    } elseif ($state.phase -eq 'pending') {
        throw 'Previous converter is missing; refusing an incomplete rollback'
    }
    Remove-OwnedTree $next
    Clear-State
}
function Recover-Transaction {
    $state = Read-State
    if (-not $state) {
        if ((Test-Path -LiteralPath $previous) -or (Test-Path -LiteralPath $next)) { throw 'Unclaimed converter recovery directory; manual recovery required' }
        return
    }
    switch ($state.phase) {
        'switching' { Restore-Previous $state }
        'preparing' { Remove-OwnedTree $next; Clear-State }
        'prepared' { Remove-OwnedTree $next; Clear-State }
        'confirmed' { try { Remove-OwnedTree $previous; Clear-State } catch { Write-Warning 'Previous converter retained; cleanup will be retried' } }
        'pending' {
            if (-not (Test-Path -LiteralPath $target)) { Restore-Previous $state }
        }
    }
}
function Assert-Required([string]$Directory) {
    foreach ($relative in @('main.py','run_converter.py','docling_dev/api.py','pyruntime/python.exe','vendor/tesseract/tesseract.exe')) {
        if (-not (Test-Path -LiteralPath (Join-Path $Directory $relative) -PathType Leaf)) { throw "Converter file missing: $relative" }
    }
    foreach ($relative in @('.venv/Lib/site-packages','models/docling')) {
        if (-not (Test-Path -LiteralPath (Join-Path $Directory $relative) -PathType Container)) { throw "Converter directory missing: $relative" }
    }
}
function Test-IgnoredConverterPath([string]$Relative) {
    foreach ($part in $Relative.Split('/')) {
        if ($part.ToLowerInvariant() -in @('.git','.gitignore','.gitattributes','.gitmodules','__pycache__','node_modules','tests','pdf_to_convert','converter-manifest.json')) { return $true }
    }
    return $Relative -match '\.(pyc|log)$' -or
        ($Relative.StartsWith('models/', [StringComparison]::OrdinalIgnoreCase) -and $Relative -match '\.part\d*$') -or
        $Relative -match '^\.converter-manifest-[0-9a-f-]{36}\.tmp$' -or $Relative -match '(^|/)\.sbc-[0-9a-f]{16}$'
}
function Test-InstalledManifest($manifest) {
    if (-not $manifest -or -not [IO.Directory]::Exists($target)) { return $false }
    $expected = @{}
    foreach ($file in $manifest.files) { $expected[$file.path] = $file }
    $actual = @{}
    $pending = New-Object 'Collections.Generic.Stack[string]'
    $pending.Push('')
    while ($pending.Count) {
        $relative = $pending.Pop()
        foreach ($item in Get-ChildItem -LiteralPath (Join-Path $target $relative) -Force) {
            $name = if ($relative) { "$relative/$($item.Name)" } else { $item.Name }
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Converter contains a link: $name" }
            if (Test-IgnoredConverterPath $name) { continue }
            if ($item.PSIsContainer) { $pending.Push($name) }
            elseif (-not $expected.ContainsKey($name)) { return $false }
            else { $actual[$name] = $item }
        }
    }
    if ($actual.Count -ne $expected.Count) { return $false }
    $checked = 0
    Write-UpdateProgress 'Checking installed converter' 0 $manifest.files.Count
    foreach ($file in $manifest.files) {
        $item = $actual[$file.path]
        if ($item.Length -ne $file.size -or (Get-FileHash -LiteralPath $item.FullName).Hash -ne $file.sha256) { return $false }
        $after = Get-Item -LiteralPath $item.FullName -Force
        if ($after.Attributes -band [IO.FileAttributes]::ReparsePoint -or $after.Length -ne $item.Length -or
            $after.LastWriteTimeUtc -ne $item.LastWriteTimeUtc) { return $false }
        $checked++
        Write-UpdateProgress 'Checking installed converter' $checked $manifest.files.Count
    }
    Assert-Required $target
    return $true
}
function Save-InstalledManifest($manifest) {
    $temporary = Join-Path $target ('.converter-manifest-' + [Guid]::NewGuid().ToString() + '.tmp')
    $destination = Join-Path $target 'converter-manifest.json'
    $null = Assert-SafePath $destination
    try {
        [IO.File]::WriteAllText($temporary, ($manifest | ConvertTo-Json -Depth 10), (New-Object Text.UTF8Encoding($false)))
        if ([IO.File]::Exists($destination)) { [IO.File]::Replace($temporary, $destination, $null) }
        else { [IO.File]::Move($temporary, $destination) }
    } finally {
        if ([IO.File]::Exists($temporary)) { [IO.File]::Delete($temporary) }
    }
}
function Check-ArchiveContent($archive, $manifest, $sourceItems) {
    $expected = @{}
    if ($manifest) { foreach ($file in $manifest.files) { $expected[$file.path] = $file } }
    $found = @{}
    if ($archive) {
        $checkedEntries = 0
        Write-UpdateProgress 'Checking archive' 0 $archive.Entries.Count
        foreach ($entry in $archive.Entries) {
            $checkedEntries++
            Write-UpdateProgress 'Checking archive' $checkedEntries $archive.Entries.Count
            if (-not $entry.Name) { continue }
            $relative = $entry.FullName.Replace('\','/').Substring(10)
            if ($relative -eq 'converter-manifest.json') { continue }
            $found[$relative] = $true
            $input = $entry.Open()
            $hash = [Security.Cryptography.SHA256]::Create()
            try { $actual = ([BitConverter]::ToString($hash.ComputeHash($input))).Replace('-','') }
            finally { $input.Dispose(); $hash.Dispose() }
            if ($manifest -and (-not $expected.ContainsKey($relative) -or $expected[$relative].size -ne $entry.Length -or $expected[$relative].sha256 -ne $actual)) {
                throw "Archive hash mismatch: $relative"
            }
        }
        foreach ($name in @('main.py','run_converter.py','docling_dev/api.py','pyruntime/python.exe','vendor/tesseract/tesseract.exe')) {
            if (-not $found.ContainsKey($name)) { throw "Archive is incomplete: $name" }
        }
        foreach ($prefix in @('.venv/Lib/site-packages/','models/docling/')) {
            if (-not @($found.Keys | Where-Object { $_.StartsWith($prefix) }).Count) { throw "Archive is incomplete: $prefix" }
        }
        if ($manifest -and $found.Count -ne $expected.Count) { throw 'Archive file count does not match manifest' }
    } else {
        Assert-Required $SourceDir
        if ($manifest) {
            $actualFiles = @($sourceItems | Where-Object { -not $_.PSIsContainer -and $_.Name -ne 'converter-manifest.json' })
            if ($actualFiles.Count -ne $expected.Count) { throw 'Source file count does not match manifest' }
            foreach ($file in $manifest.files) {
                $candidate = Join-Path $SourceDir $file.path
                if (-not (Test-Path -LiteralPath $candidate -PathType Leaf) -or (Get-Item -LiteralPath $candidate).Length -ne $file.size -or
                    (Get-FileHash -LiteralPath $candidate).Hash -ne $file.sha256) { throw "Source hash mismatch: $($file.path)" }
            }
        }
    }
}
function Prepare-Converter {
    Recover-Transaction
    if (Read-State) { throw 'A converter update is still awaiting startup confirmation' }
    if ((-not $Zip -and -not $SourceDir) -or ($Zip -and $SourceDir)) { throw 'Specify either Zip or SourceDir' }
    $archive = $null
    $hadTarget = Test-Path -LiteralPath $target
    $manifest = $null
    try {
        $unpacked = [long]0
        if ($Zip) {
            $archive = [IO.Compression.ZipFile]::OpenRead([IO.Path]::GetFullPath($Zip))
            $seen = @{}
            foreach ($entry in $archive.Entries) {
                $relative = $entry.FullName.Replace('\','/')
                if (-not $relative.StartsWith('converter/', [StringComparison]::Ordinal)) { throw "Unexpected archive root: $relative" }
                $relative = $relative.Substring(10).TrimEnd('/')
                if (-not $relative) { continue }
                Assert-RelativePath $relative
                if ($seen.ContainsKey($relative)) { throw "Duplicate archive entry: $relative" }
                $seen[$relative] = $true
                # Reject Unix symbolic links in ZIP archives.
                if ((($entry.ExternalAttributes -shr 16) -band 0xF000) -eq 0xA000) { throw 'Archive contains a symbolic link' }
                $unpacked += $entry.Length
            }
        } else {
            $SourceDir = Assert-SafePath $SourceDir
            if ($SourceDir.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase) -or $root.StartsWith($SourceDir + '\', [StringComparison]::OrdinalIgnoreCase) -or $SourceDir -eq $root) {
                throw 'Source and destination overlap'
            }
            $sourceItems = @(Get-ChildItem -LiteralPath $SourceDir -Force -Recurse)
            foreach ($item in $sourceItems) {
                if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Source contains a reparse point' }
                if (-not $item.PSIsContainer) { $unpacked += $item.Length }
            }
        }
        if ($ManifestFile) { $manifest = Read-Manifest $ManifestFile }
        elseif ($archive) {
            $entry = $archive.GetEntry('converter/converter-manifest.json')
            if ($entry) {
                $reader = New-Object IO.StreamReader($entry.Open())
                try { $manifest = Assert-Manifest ($reader.ReadToEnd() | ConvertFrom-Json) }
                finally { $reader.Dispose() }
            }
        }
        elseif ($SourceDir) {
            $sourceManifest = Join-Path $SourceDir 'converter-manifest.json'
            if (Test-Path -LiteralPath $sourceManifest) { $manifest = Read-Manifest $sourceManifest }
        }
        if (Test-InstalledManifest $manifest) {
            if ($Action -ne 'Check') {
                try { Save-InstalledManifest $manifest }
                catch { Write-Warning "Converter files match, but manifest could not be saved: $_" }
            }
            if ($Action -eq 'Check') {
                $drive = New-Object IO.DriveInfo([IO.Path]::GetPathRoot($root))
                if ($drive.AvailableFreeSpace -lt ($reserveBytes + 64MB)) { throw 'Not enough free space for the application' }
            }
            return $false
        }
        $drive = New-Object IO.DriveInfo([IO.Path]::GetPathRoot($root))
        if ($drive.AvailableFreeSpace -lt ($unpacked + 64MB + $reserveBytes)) { throw "Not enough free space; required bytes: $($unpacked + 64MB + $reserveBytes)" }
        if ($Action -eq 'Check') { Check-ArchiveContent $archive $manifest $sourceItems; return $false }
        Write-State 'preparing' $hadTarget
        New-Item -ItemType Directory -Path $next | Out-Null
        if ($archive) {
            $extracted = 0
            Write-UpdateProgress 'Extracting converter' 0 $archive.Entries.Count
            foreach ($entry in $archive.Entries) {
                $extracted++
                Write-UpdateProgress 'Extracting converter' $extracted $archive.Entries.Count
                $relative = $entry.FullName.Replace('\','/').Substring(10).TrimEnd('/')
                if (-not $relative) { continue }
                $destination = Join-Path $next $relative
                if (-not $entry.Name) {
                    [IO.Directory]::CreateDirectory($destination) | Out-Null
                } else {
                    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($destination)) | Out-Null
                    [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $destination, $false)
                }
            }
        } else {
            foreach ($item in $sourceItems) {
                $relative = $item.FullName.Substring($SourceDir.Length + 1)
                $destination = Join-Path $next $relative
                if ($item.PSIsContainer) {
                    [IO.Directory]::CreateDirectory($destination) | Out-Null
                } else {
                    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($destination)) | Out-Null
                    Copy-Item -LiteralPath $item.FullName -Destination $destination
                    if ((Get-FileHash -LiteralPath $item.FullName).Hash -ne (Get-FileHash -LiteralPath $destination).Hash) { throw "Copy mismatch: $relative" }
                }
            }
        }
        $internal = Join-Path $next 'converter-manifest.json'
        if (-not $manifest -and (Test-Path -LiteralPath $internal)) { $manifest = Read-Manifest $internal }
        if ($manifest) {
            $actual = @(Get-ChildItem -LiteralPath $next -Force -Recurse -File | Where-Object { $_.FullName -ne $internal })
            if ($actual.Count -ne $manifest.files.Count) { throw 'Archive file count does not match manifest' }
            $verified = 0
            Write-UpdateProgress 'Verifying converter' 0 $manifest.files.Count
            foreach ($item in $manifest.files) {
                $verified++
                Write-UpdateProgress 'Verifying converter' $verified $manifest.files.Count
                $file = Join-Path $next $item.path
                if (-not (Test-Path -LiteralPath $file -PathType Leaf) -or
                    (Get-Item -LiteralPath $file).Length -ne $item.size -or
                    (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ne $item.sha256) { throw "Converter hash mismatch: $($item.path)" }
            }
            [IO.File]::WriteAllText($internal, ($manifest | ConvertTo-Json -Depth 6), (New-Object Text.UTF8Encoding($false)))
        }
        Assert-Required $next
        Write-State 'prepared' $hadTarget
        return $true
    } catch {
        $state = Read-State
        if ($state -and $state.phase -eq 'preparing') {
            Remove-OwnedTree $next
            Clear-State
        }
        throw
    } finally {
        if ($archive) { $archive.Dispose() }
    }
}
function Activate-Converter {
    $state = Read-State
    if (-not $state -or $state.phase -ne 'prepared') { throw 'No prepared converter update' }
    Write-State 'switching' $state.hadTarget
    try {
        if ($state.hadTarget) { Move-Item -LiteralPath $target -Destination $previous }
        Move-Item -LiteralPath $next -Destination $target
        Write-State 'pending' $state.hadTarget
    } catch {
        Restore-Previous (Read-State)
        throw
    }
}

$reserveBytes = $ReserveKB * 1KB
if ($LegacyDir) {
    $legacy = Assert-SafePath $LegacyDir
    foreach ($relative in @('resources\converter','generated','resources\backend\generated')) {
        $directory = Assert-SafePath (Join-Path $legacy $relative)
        if (Test-Path -LiteralPath $directory) {
            foreach ($item in Get-ChildItem -LiteralPath $directory -Force -Recurse) {
                if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Legacy installation contains a reparse point' }
                if (-not $item.PSIsContainer) { $reserveBytes += $item.Length }
            }
        }
    }
}
$root = Assert-SafePath $Dest
New-Item -ItemType Directory -Force -Path $root | Out-Null
$target = Join-Path $root 'converter'
$next = Join-Path $root '.converter-next'
$previous = Join-Path $root '.converter-previous'
$stateFile = Join-Path $root '.converter-update.json'
$stateTemp = Join-Path $root '.converter-update.tmp'
$lockFile = Join-Path $root '.converter-update.lock'
foreach ($item in @($target,$next,$previous,$stateFile,$stateTemp,$lockFile)) { $null = Assert-SafePath $item }
$lock = $null
try {
    $lock = [IO.File]::Open($lockFile, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    switch ($Action) {
        'Check' {
            if ($Zip -or $SourceDir) { $null = Prepare-Converter }
            else {
                Recover-Transaction
                $drive = New-Object IO.DriveInfo([IO.Path]::GetPathRoot($root))
                if ($drive.AvailableFreeSpace -lt ($reserveBytes + 64MB)) { throw 'Not enough free space for the application' }
            }
        }
        'Prepare' { $prepared = Prepare-Converter; @{prepared=[bool]$prepared} | ConvertTo-Json -Compress }
        'Install' { if (Prepare-Converter) { Activate-Converter } }
        'Activate' { Activate-Converter }
        'Recover' { Recover-Transaction }
        'Rollback' { $state = Read-State; if ($state) { Restore-Previous $state } }
        'Confirm' {
            $state = Read-State
            if ($state -and $state.phase -eq 'pending') {
                Assert-Required $target
                Write-State 'confirmed' $state.hadTarget
                try { Remove-OwnedTree $previous; Clear-State }
                catch { Write-Warning 'Previous converter retained; cleanup will be retried' }
            }
        }
        'Status' { $state = Read-State; if ($state) { $state | ConvertTo-Json -Compress } else { '{}' } }
    }
} catch {
    Write-Error -ErrorRecord $_ -ErrorAction Continue
    exit 2
} finally {
    if ($lock) { $lock.Dispose() }
}
