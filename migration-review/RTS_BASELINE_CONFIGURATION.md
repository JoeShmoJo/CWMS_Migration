# RTS baseline configuration: first implementation

The workflow menu now opens **Baseline Configuration** in a browser. It imports the installed settings for the eleven scripted baseline rules. Augmentation remains separate. Save Configuration automatically stores a new named version in `scripts/baseline-configuration-library` in the imported watershed. Open Saved Configuration selects from that library without browsing folders. Saved sets embed validated CSV schedule values for reuse in other forecasts. Export JSON downloads a portable copy; readable HTML exports an inspection copy. The editor can also run independently with `baseline_configuration.py --editor`.

Apply validates settings, snapshots linked CSV contents, stages generated tables and script provenance beneath the selected forecast, and disables augmentation. It does not rewrite the standalone model or its source configurations. Close the forecast before Apply, then reopen and compute manually in RTS. Do not run extraction again just to apply configuration changes.

## Install and first test

Finish compute and close RTS. Pull and run this **single PowerShell line**:

```powershell
Set-Location "C:\Projects\A_REPOSITORIES\CWMS_Migration"; git pull --ff-only; if ($LASTEXITCODE -ne 0) { throw "Git pull failed" }; & .\migration-review\Install-BaselineConfiguration.ps1 -WatershedRoot "C:\CWMS\watershed\ResSimMaster"
```

Restart RTS once after installing. Open your forecast and workflow menu, then Baseline Configuration. Save an unchanged configuration first. Close the forecast, Apply, close the editor with its Close Editor button, reopen the forecast and compute an unaugmented baseline. Start with the unchanged settings so the expected outputs are familiar. After compute, use the existing workflow action to accept completed results.

The log should contain `RTS baseline configuration:` and `RTS baseline init:` messages for the adapted rules in the active stack. Accepting a configured baseline requires initialization receipts for all selected historical and synthetic ensemble members. These receipts prove loading at initialization; the user still confirms successful compute. Real RTS initialization order and compute performance require this Windows test. The installed adapter appends initialization logic to the preserved source and leaves the original timestep function unchanged; no Python module is retrieved through Java rule state during evaluation.

On later edits, Apply stages a fresh immutable set. Rules reload settings at their next initialization without requiring another RTS restart. Existing rules retain their current settings until reinitialized. Do not apply settings during compute.

## Archives and boundaries

Each accepted configured compute archives its resolved settings, linked source bytes, generated CSVs and script snapshots. Existing baseline comparison behavior retains the baseline ID when relevant outputs match; changed outputs create a new baseline and mark older augmented results as belonging to a previous baseline.

Installation preserves the actual imported implementations in `scripts/_rts_baseline_originals/externalRules` and backs up replaced files under the printed backup directory. It patches the installed Alternative_Setup initialization rather than replacing it with a standalone snapshot. A later model reimport requires rerunning the installer to adapt the new imported scripts.

This first version exposes existing rule settings; it does not generalize reservoir-specific rule logic or change stack order. Native rules and embedded constants outside these eleven external modules remain governed by the imported model. Follow-up work for standalone: consider per-reservoir applicability and reusable configuration readers after the RTS adapter is validated; do not copy these RTS wrappers into standalone.

Validation: Python workflow suite, HTTP editor checks, and Jython 2.7.3 initialization/reload smoke test. PowerShell installation and actual ResSim compute must be verified on Windows.

## Slow-compute diagnostic

After canceling normally and closing RTS, run `ExternalPython/diagnose_baseline_execution.py --watershed <imported watershed> --forecast-root <forecast model folder> --mode original` from the repository. This backs up the current eleven adapters and active pointer, restores the preserved pre-editor rule implementations, and disables baseline configuration overrides. It leaves DSS and augmentation inputs unchanged. Restart RTS and compute the same forecast; do not extract, Apply, or accept these diagnostic results as baseline. Close RTS before restoring with the same command and `--mode configured`. The switch affects all forecasts using this imported watershed while active.

The first timing comparison restores both the original execution path and the original baseline settings. A faster run implicates that combination; it does not by itself distinguish adapter overhead from settings differences. Restore configured mode before continuing baseline workflow. The diagnostic does not recover the pre-test simulation outputs; recompute the desired configuration before accepting future results.

Performance revision: the original dispatch adapter caused a severe slowdown in the RTS test even with matching settings. The revised installer keeps the original per-timestep source function and adds only an initialization footer. Actual compute speed must be retested. Stop and restart RTS around any script installation or diagnostic mode change. When restoring from original diagnostic mode, restore configured mode first, then run the revised installer so it replaces the archived older adapter.
