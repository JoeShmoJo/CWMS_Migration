param([string]$WatershedRoot = 'C:\CWMS\watershed\ResSimMaster', [string]$BackupRoot = "$env:LOCALAPPDATA\CWMS_Migration_Backups")
$ErrorActionPreference = 'Stop'
if ($WatershedRoot -notlike '*\watershed\*') { throw 'Install into an imported RTS watershed, not the standalone model.' }
$scripts = Join-Path $WatershedRoot 'scripts'
$modules = @('DeepDrawdown','SpringSpill','NoDraft','SecondaryFloodDraftLimit','FIRO_SPACE','MinFlowPlusWithdrawal','DiversionFromCSV','IRRM','DraftToRC','FillLOPfirst','HCR_LOP_Balance')
$backup = Join-Path $BackupRoot ('baseline-' + [Guid]::NewGuid().ToString())
New-Item -ItemType Directory -Path $backup -Force | Out-Null
$items = @()
foreach ($module in $modules) {
    $original = Join-Path $scripts "externalRules\$module.py"
    if (-not (Test-Path -LiteralPath $original)) { throw "Missing existing imported rule: $original" }
    $preserved = Join-Path $scripts "_rts_baseline_originals\externalRules\$module.py"
    $items += [pscustomobject]@{Source=Join-Path $PSScriptRoot "baseline-runtime\$module.py"; Target=$original}
    # Preserve the installed implementation on first installation; never replace
    # it with the adapter wrapper during an update.
    $isAdapter = Select-String -LiteralPath $original -Pattern 'from rts_baseline_runtime import' -SimpleMatch -Quiet
    if ((Test-Path -LiteralPath $preserved) -and -not $isAdapter) {
        Copy-Item -LiteralPath $preserved -Destination (Join-Path $backup ($module + '.previous-original.py'))
        Copy-Item -LiteralPath $original -Destination $preserved
        if ((Get-FileHash $original).Hash -ne (Get-FileHash $preserved).Hash) { throw "Original refresh failed: $module" }
    }
    if (-not (Test-Path -LiteralPath $preserved)) {
        if (Select-String -LiteralPath $original -Pattern 'from rts_baseline_runtime import' -SimpleMatch -Quiet) { throw "Original implementation missing: $module" }
        New-Item -ItemType Directory -Path (Split-Path $preserved) -Force | Out-Null
        Copy-Item -LiteralPath $original -Destination $preserved
        if ((Get-FileHash $original).Hash -ne (Get-FileHash $preserved).Hash) { throw "Preservation failed: $module" }
    }
}
$setup = Join-Path $scripts 'externalSVs\Alternative_Setup.py'
if (-not (Test-Path -LiteralPath $setup)) { throw "Missing Alternative_Setup: $setup" }
# Preserve the actual imported setup script, and inject the adapter into it.
# Refuse unknown initialization code instead of replacing it with a snapshot.
$setupSource = Join-Path $backup 'Alternative_Setup.adapted.py'
$content = [IO.File]::ReadAllText($setup)
$needle = '        configDict.update(parseConfigListJSON(altConfigList))'
if (-not $content.Contains('from rts_baseline_runtime import alternative_overrides')) {
    if (-not $content.Contains($needle)) { throw 'Alternative_Setup initialization differs; review before adapting.' }
    $content = $content.Replace($needle, $needle + "`n        from rts_baseline_runtime import alternative_overrides`n        configDict.update(alternative_overrides(network))")
}
[IO.File]::WriteAllText($setupSource, $content, (New-Object Text.UTF8Encoding($false)))
$items += [pscustomobject]@{Source=$setupSource;Target=$setup}
$items += [pscustomobject]@{Source=Join-Path $PSScriptRoot 'baseline-runtime\rts_baseline_runtime.py';Target=Join-Path $scripts 'rts_baseline_runtime.py'}
$items += [pscustomobject]@{Source=Join-Path $PSScriptRoot 'ExternalPython\baseline_configuration.py';Target=Join-Path $scripts 'ExternalPython\baseline_configuration.py'}
$items += [pscustomobject]@{Source=Join-Path $PSScriptRoot 'baseline-editor-design\editor-mockup.html';Target=Join-Path $scripts 'ExternalPython\baseline-editor.html'}
$items += [pscustomobject]@{Source=Join-Path $PSScriptRoot 'baseline-editor-design\baseline-configuration.example.json';Target=Join-Path $scripts 'ExternalPython\baseline-configuration.example.json'}
$items += [pscustomobject]@{Source=Join-Path $PSScriptRoot 'RTS_WORKFLOW_MENU.py';Target=Join-Path $scripts 'RTS_WORKFLOW_MENU.py'}
$items += [pscustomobject]@{Source=Join-Path $PSScriptRoot 'ExternalPython\workflow_simple.py';Target=Join-Path $scripts 'ExternalPython\workflow_simple.py'}
$index = 0
foreach ($item in $items) {
    if (-not (Test-Path -LiteralPath $item.Source)) { throw "Missing adapter source: $($item.Source)" }
    if (Test-Path -LiteralPath $item.Target) {
        $saved = Join-Path $backup ("$index-" + (Split-Path $item.Target -Leaf))
        Copy-Item -LiteralPath $item.Target -Destination $saved
        if ((Get-FileHash $saved).Hash -ne (Get-FileHash $item.Target).Hash) { throw "Backup verification failed: $($item.Target)" }
    }
    $index++
}
foreach ($item in $items) { Copy-Item -LiteralPath $item.Source -Destination $item.Target -Force }
# Stale Jython compiled adapters must not hide new source after installation.
foreach ($module in ($modules + 'Alternative_Setup')) {
    $folder = if ($module -eq 'Alternative_Setup') { 'externalSVs' } else { 'externalRules' }
    $compiled = Join-Path $scripts ($folder + '\' + $module + '$py.class')
    if (Test-Path -LiteralPath $compiled) { Copy-Item $compiled (Join-Path $backup ($module + '$py.class')); Remove-Item -LiteralPath $compiled }
}
Write-Host "Installed RTS baseline adapters. Backup: $backup"
Write-Host 'Restart RTS once, then open Baseline Configuration. Apply closes no forecast automatically; finish compute and close the forecast first.'
