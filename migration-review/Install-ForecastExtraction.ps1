param(
    [string]$WatershedRoot = 'C:\CWMS\watershed\ResSimMaster',
    [string]$BackupRoot = "$env:LOCALAPPDATA\CWMS_Migration_Backups"
)
$ErrorActionPreference = 'Stop'
$target = Join-Path $WatershedRoot 'scripts\ExternalPython'
if (-not (Test-Path -LiteralPath (Join-Path $target 'CONFIG.py'))) {
    throw "Expected an existing imported ExternalPython folder: $target"
}
$names = @('RFC_Downloader_Module.py', 'CWMS_Downloader_Module.py',
    'Dummy_0_and_WY_Abundant_Module.py', 'OSI_Ensemble_Year.py',
    'extraction_context.py', 'run_extraction.py', 'windows_ca.py', 'diagnose_cwms.py', 'cwms_time.py',
    'write_rule_curves.py', 'CON_SEASON_RULE_CURVES.csv', 'write_ensemble_dummies.py',
    'write_ensemble_shared_inputs.py', 'ensemble_ids.py', 'catalog_forecast_outputs.py', 'plot_rts_forecast.py',
    'check_augmentation_inputs.py', 'augmentation_mapping.py',
    'prepare_rts_augmentation.py', 'load_rts_augmentation.py', 'plot_rts_augmentation.py', 'rts_workflow.py', 'baseline_versions.py', 'workflow_simple.py', 'plot_rts_runs.py')
foreach ($name in $names) {
    if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot "ExternalPython\$name"))) {
        throw "Missing installation source: $name"
    }
}
$backup = Join-Path $BackupRoot ([Guid]::NewGuid().ToString())
New-Item -ItemType Directory -Path $backup -Force | Out-Null
$items = @()
foreach ($name in $names) {
    $items += [pscustomobject]@{ Source = Join-Path $PSScriptRoot "ExternalPython\$name"; Target = Join-Path $target $name; Backup = Join-Path $backup $name }
}
$items += [pscustomobject]@{
    Source = Join-Path $PSScriptRoot 'RTS_FORECAST_EXTRACT.py'
    Target = Join-Path $WatershedRoot 'scripts\RTS_FORECAST_EXTRACT.py'
    Backup = Join-Path $backup 'RTS_FORECAST_EXTRACT.py'
}
$items += [pscustomobject]@{
    Source = Join-Path $PSScriptRoot 'RTS_WORKFLOW_MENU.py'
    Target = Join-Path $WatershedRoot 'scripts\RTS_WORKFLOW_MENU.py'
    Backup = Join-Path $backup 'RTS_WORKFLOW_MENU.py'
}
$svTarget = Join-Path $WatershedRoot 'scripts\externalSVs\MainstemFlowAugSV.py'
if (-not (Test-Path -LiteralPath $svTarget)) {
    throw "Expected existing state-variable module: $svTarget"
}
$items += [pscustomobject]@{
    Source = Join-Path $PSScriptRoot 'externalSVs\MainstemFlowAugSV.py'
    Target = $svTarget
    Backup = Join-Path $backup 'MainstemFlowAugSV.py'
}
# Complete and verify all backups before overwriting any installed file.
foreach ($item in $items) {
    if (Test-Path -LiteralPath $item.Target) {
        Copy-Item -LiteralPath $item.Target -Destination $item.Backup
        if ((Get-FileHash -LiteralPath $item.Target).Hash -ne (Get-FileHash -LiteralPath $item.Backup).Hash) {
            throw "Backup verification failed: $($item.Target)"
        }
    }
}
foreach ($item in $items) {
    Copy-Item -LiteralPath $item.Source -Destination $item.Target -Force
}
Write-Host "Installed for testing. Previous files backed up to: $backup"
Write-Host "Open scripts\RTS_FORECAST_EXTRACT.py in RTS and run its default plan mode."
