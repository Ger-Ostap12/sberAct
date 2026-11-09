# Builds a complete, baseline-independent USB package. Use -AppOnly explicitly to omit OCR.
param([switch]$IncludeConverter, [switch]$AppOnly, [switch]$BaselineOnly, [string]$ConverterDir)
$ErrorActionPreference = 'Stop'
if ($BaselineOnly) { throw 'Baselines are no longer used. Run build:update to create a complete package.' }
$argsForBuild = @((Join-Path $PSScriptRoot 'build-update.js'))
if ($AppOnly) { $argsForBuild += '-AppOnly' }
if ($ConverterDir) { $argsForBuild += @('-ConverterDir', $ConverterDir) }
& node @argsForBuild
exit $LASTEXITCODE
