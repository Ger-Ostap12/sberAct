# Prepares a per-user installation before retiring the legacy installation.
param(
    [Parameter(Mandatory = $true)][ValidateSet('Prepare', 'Retire', 'RetireElevated')][string]$Mode,
    [Parameter(Mandatory = $true)][string]$Source,
    [Parameter(Mandatory = $true)][string]$Target,
    [Parameter(Mandatory = $true)][string]$AppExe,
    [ValidateSet('currentuser', 'allusers')][string]$Scope = 'currentuser',
    [string]$ExpectedSid
)
$ErrorActionPreference = 'Stop'
$logDir = Join-Path $env:LOCALAPPDATA 'SberAct\logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
Start-Transcript -Path (Join-Path $logDir ('install-migration-{0}.log' -f $PID)) -Append | Out-Null

function Get-SafeDirectory([string]$Directory) {
    $full = [IO.Path]::GetFullPath($Directory).TrimEnd('\')
    if ($full -eq [IO.Path]::GetPathRoot($full).TrimEnd('\')) { throw 'Drive root is not an application directory' }
    $cursor = $full
    while ($cursor) {
        if (Test-Path -LiteralPath $cursor) {
            $item = Get-Item -LiteralPath $cursor -Force
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Reparse point: $cursor" }
        }
        $cursor = Split-Path -Parent $cursor
    }
    return $full
}

function Copy-VerifiedTree([string]$From, [string]$To) {
    if (-not ('SberActVerifiedCopy' -as [type])) {
        Add-Type -Path (Join-Path $PSScriptRoot 'verified-copy.cs')
    }
    $progress = [Action[long,long,int,int,string]] {
        param($copied, $totalBytes, $done, $totalFiles, $phase)
        $percent = if ($totalFiles) { [int][math]::Floor(100.0 * $done / $totalFiles) } else { 0 }
        Write-Host ("{0}: {1}/{2} files ({3}%); {4:N0}/{5:N0} MiB" -f $phase, $done, $totalFiles, $percent, ($copied / 1MB), ($totalBytes / 1MB))
    }
    [SberActVerifiedCopy]::Copy($From, $To, $progress)
}

try {
    $sourceDir = Get-SafeDirectory $Source
    $targetDir = Get-SafeDirectory $Target
    if ($sourceDir -eq $targetDir -or $targetDir.StartsWith($sourceDir + '\', [StringComparison]::OrdinalIgnoreCase) -or
        $sourceDir.StartsWith($targetDir + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Installation directories overlap' }
    if ([IO.Path]::GetFileName($AppExe) -ne $AppExe -or $AppExe -notlike '*.exe') { throw 'Invalid application executable' }
    $uninstaller = Join-Path $sourceDir ('Uninstall ' + $AppExe)
    if (-not (Test-Path -LiteralPath $uninstaller -PathType Leaf)) { throw "Legacy uninstaller missing: $uninstaller" }
    $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value

    if ($Mode -eq 'Prepare') {
        $expectedTarget = Join-Path $env:LOCALAPPDATA 'Programs\SberAct'
        if ($targetDir -ne $expectedTarget) { throw 'Target must be the current user installation directory' }
        New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
        $probe = Join-Path $targetDir ([guid]::NewGuid().ToString() + '.write-test')
        [IO.File]::WriteAllText($probe, 'SberAct')
        Remove-Item -LiteralPath $probe
        # Preserve local documents from standalone backend runs, without merging user data.
        $backup = Join-Path $env:LOCALAPPDATA ('SberAct\migration-backups\' + [guid]::NewGuid())
        foreach ($relative in @('generated', 'resources\backend\generated')) {
            $documents = Join-Path $sourceDir $relative
            if (Test-Path -LiteralPath $documents) { Copy-VerifiedTree $documents (Join-Path $backup $relative) }
        }
        $converter = Join-Path $sourceDir 'resources\converter'
        if (Test-Path -LiteralPath $converter) {
            Copy-VerifiedTree $converter (Join-Path $targetDir 'resources\converter')
        }
        Write-Host 'Legacy installation retained. Converter copy verified; userData location unchanged.'
        exit 0
    }

    foreach ($relative in @($AppExe, 'resources\app.asar', 'resources\backend\SberAct.exe')) {
        $file = Join-Path $targetDir $relative
        if (-not (Test-Path -LiteralPath $file -PathType Leaf) -or (Get-Item -LiteralPath $file).Length -eq 0) {
            throw "New installation is incomplete: $relative"
        }
    }
    $converter = Join-Path $sourceDir 'resources\converter'
    if (Test-Path -LiteralPath $converter) {
        foreach ($relative in @('pyruntime\python.exe', 'docling_dev\api.py', 'vendor\tesseract\tesseract.exe')) {
            if (-not (Test-Path -LiteralPath (Join-Path $targetDir ('resources\converter\' + $relative)) -PathType Leaf)) {
                throw "New converter is incomplete: $relative"
            }
        }
    }
    if ($Mode -eq 'RetireElevated' -and $sid -ne $ExpectedSid) {
        throw 'Use elevation for the same Windows account; another administrator cannot migrate this user installation'
    }
    if ($Mode -eq 'Retire') {
        $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
        $needsElevation = $Scope -eq 'allusers'
        try {
            $probe = Join-Path $sourceDir ([guid]::NewGuid().ToString() + '.write-test')
            [IO.File]::WriteAllText($probe, 'SberAct')
            Remove-Item -LiteralPath $probe
        } catch [UnauthorizedAccessException] { $needsElevation = $true }
        if ($needsElevation -and -not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
            $arguments = '-NoProfile -ExecutionPolicy Bypass -File "{0}" -Mode RetireElevated -Source "{1}" -Target "{2}" -AppExe "{3}" -Scope {4} -ExpectedSid {5}' -f $PSCommandPath, $sourceDir, $targetDir, $AppExe, $Scope, $sid
            $child = Start-Process -FilePath 'powershell.exe' -ArgumentList $arguments -Verb RunAs -WindowStyle Hidden -Wait -PassThru
            exit $child.ExitCode
        }
    }
    # --updated prevents deletion of userData by older uninstallers.
    $arguments = '/S /KEEP_APP_DATA /{0} --updated _?={1}' -f $Scope, $sourceDir
    $child = Start-Process -FilePath $uninstaller -ArgumentList $arguments -WindowStyle Hidden -Wait -PassThru
    if ($child.ExitCode -ne 0) { throw "Legacy uninstaller failed: $($child.ExitCode)" }
    if (Test-Path -LiteralPath (Join-Path $sourceDir $AppExe)) { throw 'Legacy application executable was not removed' }
    Write-Host 'Legacy application removed. Its preserved converter remains as a backup in the previous directory.'
    exit 0
} catch {
    Write-Error -ErrorRecord $_ -ErrorAction Continue
    exit 2
} finally {
    Stop-Transcript | Out-Null
}
