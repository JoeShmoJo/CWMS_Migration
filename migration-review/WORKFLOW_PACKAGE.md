# Standalone and RTS workflow package

This kit travels with the watershed at `scripts/workflow-kit`. It contains both
menus, the baseline editor/runtime, RTS extraction/augmentation/archive/plot helpers,
script installers, and the operator/file reference documents. `manifest.json`
contains SHA-256 checksums of the kit payload. No application JAR, Java runtime,
Python environment, DSS output or model network is bundled by this kit.

Keep the existing watershed scripts, CSVs, alt_config, external modules, native
alternatives and DSS mappings when transferring the watershed. The kit supplements
those model-specific files; it is not a replacement watershed or a universal model
installer. Keep the standalone watershed and imported RTS copy separate.

For repository-free reopening, begin with [project handoff](PROJECT_START_HERE.md),
the [combined operator SOP](WORKFLOW_SOP.md), and the
[standalone technical reference](STANDALONE_WORKFLOW_REFERENCE.md). Packaging adds
a root WORKFLOW_README.md, preserves PROJECT_LOCAL_NOTES.md, and records actual
local script paths/checksums and Python versions in installation-inventory.json.

## Read in a browser

Double-click `WORKFLOW_README.html` at the watershed root. The linked HTML guides
under `scripts/workflow-kit/documentation` work offline with navigation, formatted
tables and code, and browser printing/PDF export. No server, Markdown viewer or
additional Python package is needed to read or generate them. Markdown remains
the editable source; rerunning the embedded packager regenerates HTML.

The standalone menu also supports [Single POR / Model Check](STANDALONE_POR_MODEL_CHECK.md).
The embedded model_check directory contains code/limits only; native results and
old report output folders are not copied into the kit.

## Standalone SOP

1. Finish compute and close ResSim before installing/updating scripts. Package the
   existing watershed using the repository command below. This activates standalone
   mode and embeds the kit; it does not copy the large watershed.
2. Reopen the watershed in standalone ResSim. In the Simulation module Script Editor,
   run the launcher below. Select the actual simulation folder and alternative.
3. Open Baseline Configuration, verify the target banner, load/import/edit settings,
   save a named configuration, then Apply. Compute manually in ResSim.
4. Use existing native standalone augmentation conventions, then archive/plot
   named results using [saved-run instructions](STANDALONE_SAVED_RESULTS.md). The other
   menu jobs use the selected target and applied **Standalone job settings** in the
   baseline editor. Apply before extraction/calculation jobs. Plotting existing archives needs no
   new Apply. Verify additional
   downloader/date constants and native mappings separately. Apply does not turn
   off standalone augmentation automatically.
5. See [standalone instructions](STANDALONE_CONFIGURATION.md) for validation,
   trial conventions, receipts and rollback. The user has verified standalone
   configuration in ResSim; new environment transitions still need local testing.

Standalone Script Editor launcher:

```python
from hec.script import ClientAppWrapper; import os; execfile(os.path.join(str(ClientAppWrapper.getWatershed().getWkspDir()), 'scripts', 'STANDALONE_WORKFLOW_MENU.py'))
```

Build/update the package from the repository (PowerShell, one line):

```powershell
Set-Location "C:\Projects\A_Recent_Projects\CWMS_Migration"; git pull --ff-only; if ($LASTEXITCODE -ne 0) { throw "Git pull failed" }; & "$env:LOCALAPPDATA\miniconda3\envs\hydro39\python.exe" ".\migration-review\Package-Workflow.py" --watershed "C:\Projects\FIRO\watershed\NWP_Willamette_Master_2026_10_05_DamagesPrevented"
```

## Import into RTS

1. Import/copy the complete watershed using your normal RTS import procedure.
   Confirm scripts, workflow-kit, native alternatives and DSS mappings survived.
2. Close RTS and ResSim. Activate RTS mode **in the imported watershed copy**,
   before creating a new forecast. Run the following line and enter that copy's
   watershed root, not a forecast root or your standalone source.

```powershell
$ws = Read-Host "Imported RTS watershed root"; & "$env:LOCALAPPDATA\miniconda3\envs\hydro39\python.exe" (Join-Path $ws "scripts\workflow-kit\Install-StandaloneConfiguration.py") --watershed $ws --mode rts
```

3. Reopen RTS, verify imported model/program linking, create/select the forecast,
   and run `scripts/RTS_WORKFLOW_MENU.py` in the RTS Script Editor. Check forecast,
   run, DSS file, dates and timezone. Do not use the standalone menu in RTS.
4. Initial Extract → configure/apply baseline → compute unaugmented → accept
   results → configure/process/load augmentation → compute augmented → accept/plot.
   Follow [RTS operator SOP](RTS_OPERATOR_SOP.md) for the full sequence and
   [file reference](RTS_WORKFLOW_REFERENCE.md) for inputs, outputs and provenance.
5. Saved baseline JSON uses the same format in both environments. Open the saved
   set and Apply again in the new forecast. Standalone active pointers, simulation
   outputs and initialization receipts are not RTS baseline acceptance or archives.
   Native operation sets, mappings and standalone augmentation trials are not
   converted by loading configuration JSON. Validate these in the imported model.
6. First run a small serial case and verify initialization and expected output.
   This package does not install the experimental Java/compiler modification or
   promise native multithreaded scripted ensemble support.

RTS Script Editor launcher:

```python
from hec.script import ClientAppWrapper; import os; execfile(os.path.join(str(ClientAppWrapper.getWatershed().getWkspDir()), 'scripts', 'RTS_WORKFLOW_MENU.py'))
```

The existing `hydro39` Python environment must be installed on the destination
machine. The launchers expect `%LOCALAPPDATA%\miniconda3\envs\hydro39\python.exe`.
Python needs the existing project dependencies including numpy, pandas, plotting
packages and the working DSS binding. CWMS/RFC extraction also requires network
access and CWMS access/certificates. These prerequisites are not installed by the
kit. RTS metadata, program linking, valid forecast dates and model mappings still
require normal RTS setup. Archived RFC loading remains outside this workflow.

## Switching, backups and files

The mode installer unwraps recognized adapters using preserved original sources,
then installs the selected adapter once. It refuses missing originals/unknown
setup code before writing. It backs up every affected existing file and rolls
back script writes if installation fails. Restart after switching to clear cached
Jython modules. Never switch during compute or run both environments against the
same writable watershed.

| Artifact | Location relative to watershed | Producer/purpose |
| --- | --- | --- |
| Portable kit and docs | `scripts/workflow-kit/` | Package builder; offline installer payload |
| Active script mode | `scripts/workflow-mode.json` | Installer; records last mode, not automatic environment detection |
| Menus | `scripts/STANDALONE_WORKFLOW_MENU.py`, RTS mode also `scripts/RTS_WORKFLOW_MENU.py` | Installer; use the environment's menu |
| Backend scripts | `scripts/ExternalPython/` | Installer updates selected helpers; preserves existing CONFIG.py |
| Original rule implementations | `scripts/_standalone_baseline_originals/`, `scripts/_rts_baseline_originals/` | Installer; sources for adapters and subsequent transitions |
| Preserved standalone downloader/helpers | `scripts/_workflow_originals/ExternalPython/` | Preserved before first RTS transition; restored for standalone; RTS-only new helpers may remain dormant |
| Original standalone augmentation state variable | `scripts/_workflow_originals/MainstemFlowAugSV.py` | Preserved before first RTS transition; restored for standalone |
| Versioned baseline library | `scripts/baseline-configuration-library/` | Editor Save; portable JSON |
| Standalone applied settings | `rss/<simulation>/baseline-configurations/`, `standalone-baseline-config-active.json` | Apply; scoped to selected simulation/alternative |
| RTS applied settings/results | Forecast root; see RTS file reference | Apply, accept, process/load; not shared with standalone results |
| Script backups | `standalone-configuration-backups/<timestamp-token>/files.json` | Both installer modes; inventory and original file contents |
| Previous kit | `scripts/workflow-kit-previous-<id>/` | Builder; only kit copied, no DSS/model duplication |

To switch a copy back to standalone, close applications and run the embedded
installer with `--mode standalone` instead of `--mode rts`. CONFIG.py and all native
model settings remain as they were; verify them before computing. To roll back a
particular installation, use its printed backup and files.json: restore entries
that existed and remove only newly installed entries. Mode switching retains
both environments' saved/applied configurations; it does not migrate result data.

No CONFIG.py, alt_config file, user CSV schedule, native network, simulation DSS,
forecast DSS or application JAR is rewritten by packaging/mode installation.
RTS mode deliberately installs the maintained MainstemFlowAugSV implementation;
standalone mode restores the preserved standalone implementation.
