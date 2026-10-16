param(
    [string]$WatershedRoot = 'C:\CWMS\watershed\ResSimMaster',
    [string]$BackupRoot = "$env:LOCALAPPDATA\CWMS_Migration_Backups"
)
$ErrorActionPreference = 'Stop'
$target = Join-Path $WatershedRoot 'scripts\ExternalPython'
if (-not (Test-Path -LiteralPath (Join-Path $target 'workflow_simple.py'))) {
    throw "Expected an existing RTS workflow installation: $target"
}
$names = @('run_archive.py','run_data_cache.py','baseline_versions.py','workflow_simple.py',
    'prepare_rts_augmentation.py','load_rts_augmentation.py','plot_rts_augmentation.py',
    'plot_rts_runs.py','rts_workflow.py')
foreach ($name in $names) {
    if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot "ExternalPython\$name"))) {
        throw "Missing installation source: $name"
    }
}
$backup = Join-Path $BackupRoot ('compact-run-archives-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $backup | Out-Null
$items = @()
foreach ($name in $names) {
    $destination = Join-Path $target $name
    $exists = Test-Path -LiteralPath $destination
    $items += [pscustomobject]@{Name=$name;Target=$destination;Existed=$exists}
    if ($exists) {
        $saved = Join-Path $backup $name
        Copy-Item -LiteralPath $destination -Destination $saved
        if ((Get-FileHash -LiteralPath $saved).Hash -ne (Get-FileHash -LiteralPath $destination).Hash) {
            throw "Backup verification failed: $name"
        }
    }
}
$items | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $backup 'files.json') -Encoding UTF8
try {
    foreach ($item in $items) {
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot "ExternalPython\$($item.Name)") -Destination $item.Target -Force
        if ((Get-FileHash -LiteralPath $item.Target).Hash -ne (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot "ExternalPython\$($item.Name)")).Hash) {
            throw "Installed checksum mismatch: $($item.Name)"
        }
    }
} catch {
    foreach ($item in $items) {
        if ($item.Existed) { Copy-Item -LiteralPath (Join-Path $backup $item.Name) -Destination $item.Target -Force }
        elseif (Test-Path -LiteralPath $item.Target) { Remove-Item -LiteralPath $item.Target }
    }
    throw
}
Write-Host "Installed compact run archiving. Script backup: $backup"
Write-Host 'No JARs, rule scripts, configurations, DSS files, or existing archives changed.'
Write-Host 'Close the workflow menu before installing; reopen it afterward. Reuse the existing test forecast.'
