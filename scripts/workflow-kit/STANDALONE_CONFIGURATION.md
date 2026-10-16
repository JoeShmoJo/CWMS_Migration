# One standalone alternative, reusable baseline configurations

This adds the same baseline configuration format and browser editor used by RTS
to standalone ResSim. Use one model alternative such as **Con_Season**. Import
old alternative-named settings as presets, then save/load named configuration sets
instead of cloning alternatives to change scripted-rule settings.

This provides baseline settings plus named standalone result capture/plotting. Existing standalone extraction,
augmentation calculation, trial conventions and plotting scripts remain in place.
Standalone archives reuse compact storage but keep their own identity/pairing metadata;
this does not port RTS scheme activation,
change native operation sets or DSS mappings, or modify any application JAR.
Use the original ResSim application and start native validation with serial compute.

## Install into the existing standalone test watershed

Finish computes and close standalone ResSim. No new watershed copy is needed.
The installer backs up only files it changes and retains the old alt_config files,
CSV schedules, CONFIG.py and simulation outputs unchanged. It unwraps recognized standalone/RTS adapters using their preserved sources and
rejects missing originals or unknown Alternative_Setup initialization structures.
For a portable kit and RTS import steps, see [package instructions](WORKFLOW_PACKAGE.md).

PowerShell one line (paste the standalone test watershed root when prompted):

```powershell
Set-Location "C:\Projects\A_Recent_Projects\CWMS_Migration"; git pull --ff-only; if ($LASTEXITCODE -ne 0) { throw "Git pull failed" }; $ws = Read-Host "Existing standalone test watershed root"; & "$env:LOCALAPPDATA\miniconda3\envs\hydro39\python.exe" ".\migration-review\Install-StandaloneConfiguration.py" --watershed $ws
```

This requires the existing eleven external rule modules, Alternative_Setup, and
ExternalPython directory. It is intended for the current scripted Willamette model,
not the older 3.5 snapshot missing some of these modules.

Restart ResSim, open that watershed, and open/run
`scripts\STANDALONE_WORKFLOW_MENU.py` in the Script Editor. Alternatively paste this
single launcher line into the editor:

```python
from hec.script import ClientAppWrapper; import os; execfile(os.path.join(str(ClientAppWrapper.getWatershed().getWkspDir()), 'scripts', 'STANDALONE_WORKFLOW_MENU.py'))
```

## Operator steps

1. Open the intended simulation in ResSim and note the simulation folder and
   model alternative shown in Simulation Control. The directory must exist under `rss`.
2. In the menu, explicitly select **Baseline target simulation** and enter
   **Baseline target alternative**. Neither field defaults to CONFIG.py or Con_Season.
   For example, select `Flood_96_3hour` and enter `Temp3Hour` when those are shown
   in ResSim. Choose **Baseline Configuration** and confirm both names.
3. Verify the browser's target simulation, alternative and directory before Apply.
   The menu passes these explicitly; it does not infer the selected GUI simulation.
   The OSI extraction setting is managed in **Standalone job settings** inside
   Baseline Configuration. Plotting uses archived named results. Menu jobs
   use the selected target and applied settings, not CONFIG.py.
4. For the initial state, the editor reads watershed `_default.txt` plus the target
   alternative's `.txt` file. Use **Import legacy alternative settings** to import
   a preset such as HCR1511 or HCR1531 without changing the target Con_Season.
   Alias files are resolved; cycles/invalid names are rejected.
5. Edit the rule settings/tables, name the set, and **Save Configuration**. Each
   save creates a new library version. **Open Saved Configuration** loads a set
   into the editor; Import/Export JSON exchanges the same format with RTS. Saving
   and opening do not activate settings.
6. Finish all computes, then **Apply to Standalone Alternative**. This snapshots
   the chosen settings for that simulation/alternative. Close the editor when
   finished and compute manually in ResSim. Settings are loaded at initialization
   and do not change an in-progress compute. Do not run other file-writing menu
   jobs concurrently with Apply.
7. Preserve any existing outputs you need before recomputing. Run the baseline
   and then the existing augmentation/trial process as usual. For another baseline,
   load/edit/save/apply a different set and recompute the affected trials using
   the same model alternative. Re-extraction is not needed for rule-setting edits.

The installer preserves the original timestep functions and adds initialization
adapters only. A changed applied set is picked up at the next initialization;
restart once after installation so previously imported Python modules cannot
hide the new adapters. A preset import copies baseline scripted settings only:
it does not reproduce a different alternative's native rule stack, operations,
augmentation method or input mappings.

## What stays separate from baseline settings

The existing default alternative file uses `mainstemFlowAugMethod: AutoDetect`
and `omitTrialsFromFlowAug: "0,2,3"`; other installed files can differ. These and
standalone CONFIG trial settings are not changed by this editor. Verify your own
baseline/augmented trial conventions rather than assuming Apply disables all
augmentation as it does in RTS. The Apply message explicitly states that the
existing standalone augmentation/trial settings remain unchanged.

The menu offers a Simulation type selector, Extract ensemble inputs, Calculate
ensemble augmentation, **Archive / Plot Results**, and **Model Check**. Single POR
mode hides OSI controls and disables ensemble-only jobs; see
[POR / Model Check](STANDALONE_POR_MODEL_CHECK.md). Plot selection uses named archived runs, not CONFIG.py or trial plot
settings. Follow [saved-result SOP and reference](STANDALONE_SAVED_RESULTS.md).
Configuration Overview keeps only the OSI source-member setting for extraction.
Menu jobs use the selected target plus applied settings, with a private temporary
compatibility module for legacy imports. The shared CONFIG.py is not read or
rewritten by the normal menu. Its file remains only for old manual launches.
Standalone augmentation calculation/native activation still use existing model
conventions; archiving does not change those rules or configure native trials.

## Files and isolation

| Artifact | Location relative to standalone watershed |
| --- | --- |
| Menu | `scripts/STANDALONE_WORKFLOW_MENU.py` |
| Standalone job runner | `scripts/ExternalPython/standalone_jobs.py` |
| Standalone editor launcher/backend | `scripts/ExternalPython/standalone_configuration.py` |
| Shared editor/validation | `scripts/ExternalPython/baseline_configuration.py`, `baseline-editor.html`, `baseline-configuration.example.json` |
| Configuration library | `scripts/baseline-configuration-library/<id>.json` |
| Preserved rule sources | `scripts/_standalone_baseline_originals/externalRules/*.py` |
| Initialization runtime | `scripts/standalone_baseline_runtime.py` |
| Applied set | `rss/<simulation>/baseline-configurations/sets/<id>/` |
| Active pointer | `rss/<simulation>/standalone-baseline-config-active.json` |
| Initialization receipts | Applied set's `initialization-receipts/*.json` |
| Editor/job logs | `standalone-workflow-logs/` |
| Installation backup and inventory | `standalone-configuration-backups/<timestamp-token>/`, including `files.json` |

Applied sets contain configuration/resolved JSON, generated CSV tables, linked
source snapshots and rule/runtime snapshots. The active pointer binds settings
to one model alternative. Other alternatives and simulations retain their own
legacy behavior. Within that simulation, all trials of the chosen model
alternative use the applied baseline settings at their initialization. Receipts
record the ensemble member when present, or null plus the output F-part for a
non-ensemble run. Receipts prove initialization, not compute success.

The standalone runtime is generated from the shared RTS initialization adapter,
with its own pointer name, source preservation folder, alternative guard and
non-ensemble receipt support. RTS continues using its separate runtime/pointer.
The saved configuration schema remains identical. Never edit generated applied
CSV tables in place; edit/save/apply a new set instead.

## First validation and rollback

Import/save/apply unchanged Con_Season settings first, compute a small serial
case, and compare with the preserved pre-change results. Then import HCR1511 into
that same target, save/apply, recompute, and inspect the IRRM setting/output.
Switch back to the original saved set and verify restoration. Test two successive
applies in the same application session after the initial restart.

Python tests exercise legacy/alias imports, versioned library saves, applying
and reloading settings, per-simulation/alternative isolation, ordinary non-ensemble
initialization, repeat installation and refusal of an unknown setup script.
The shared RTS editor tests and the Python suite pass. A Jython 2.7.3
smoke check also exercises successive applies, non-ensemble receipts, alternative
isolation and defaults restoration. Cloud tests do not prove native Windows
ResSim initialization order or model output equivalence; those remain local tests.

To revert script installation, close ResSim and restore the changed paths from
the printed backup using files.json (restore existing files; remove only newly
installed ones). Keep library/applied sets if useful. No original alt_config or
CSV schedule needs restoration because the installer and Apply do not rewrite them.
