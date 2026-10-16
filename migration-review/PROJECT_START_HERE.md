# Start here: Willamette ResSim / RTS project handoff

Documentation date: 16 October 2026. Keep this file with the watershed.
The repository is not needed to operate the installed workflow or use the embedded
mode installer. The scripts, model, data and Python environment are still needed.

Double-click **WORKFLOW_README.html** at the watershed root for the offline browser
version of these guides. Use the navigation bar to move between standalone and RTS
instructions. Browser Print can save a PDF. Markdown sources remain available.

For a new coding session or re-upload, read [PROJECT_RESUME.md](PROJECT_RESUME.md)
first. Packaging also places that continuation brief at the watershed root.

## Next task

[Fresh RTS import and validation checklist](RTS_IMPORT_VALIDATION.md) is the next
session's work. The latest native import has not yet been tested. The open
FLOW-MINLIM issue is recorded there; catalog presence has been confirmed, actual
values have not. Preserve the current simulation DSS, archives and read reports.

## Read in this order

1. [Operator SOP: standalone and RTS](WORKFLOW_SOP.md).
2. [Detailed standalone/shared reference](STANDALONE_WORKFLOW_REFERENCE.md).
3. [Detailed RTS process and file reference](RTS_WORKFLOW_REFERENCE.md).
4. [Packaging, importing and switching modes](WORKFLOW_PACKAGE.md).
5. [RTS data I/O and archive design](RTS_DATA_IO.md).

`installation-inventory.json`, generated beside this file when packaged, records
actual watershed paths, simulation folders, script/data checksums and the Python
interpreter/package versions used for packaging. `manifest.json` fingerprints the
kit payload. Neither certifies compute success. Read installed source and logs if
a local edit makes behavior differ from these documents.

## What was completed / where work stopped

- Standalone menu jobs use the browser’s applied job settings and selected target;
  The shared CONFIG.py is not needed by the normal menu. Plot trials are retired.
  Use [named saved results](STANDALONE_SAVED_RESULTS.md) to retain changing baselines
  and plot one or two archived runs later. Standalone synthetic IDs now match RTS:
  3000/3001/3002 percentiles and 3003 OSI. Re-extraction and native member/mapping
  review are required; old DSS/archives are not renamed.
- A shared browser baseline editor supports eleven scripted-rule groups and
  reusable named JSON sets, with separate Save and Apply actions.
- Standalone targeting now explicitly asks for simulation and alternative. The
  user verified the revised configuration workflow in standalone ResSim.
- RTS supports extraction, baseline configuration/acceptance, augmentation
  preparation/loading, accepted results and plotting. The user exercised RTS;
  compact archives and later packaging changes require local verification.
- A portable kit and script-mode installer are provided. Automated tests cover
  packaging, checksums and standalone → RTS → standalone transitions. Native
  import/transition validation remains an operator task.
- Experimental vendor JAR/compiler isolation work is retired from this workflow.
  Do not install/recreate that modification. Use original HEC software and a
  supported compute mode, initially serial. Prior restoration of every local
  experimental installation has not been independently verified by these scripts.
- Historical RFC archive loading is paused pending missing station records.
  Current extraction downloads the current RFC issue, not a historical issue.

Known examples, not hardcoded operating targets:

| Item | Last known location/name |
| --- | --- |
| Standalone watershed | `C:\Projects\FIRO\watershed\NWP_Willamette_Master_2026_10_05_DamagesPrevented` |
| Confirmed target mismatch corrected | Editor had Ensemble_Test / Con_Season; intended Flood_96_3hour / Temp3Hour |
| RTS installation | `C:\Mobile_Programs\rts-install-package-3.6.0\HEC-RTS-3.6.0` |
| RTS imported watershed | `C:\CWMS\watershed\ResSimMaster` |
| Example forecasts | `C:\CWMS\forecast\Ensemble_Test\ResSimMaster`, `C:\CWMS\forecast\15Oct2026\ResSimMaster` |
| Historical RFC archive, incomplete | `C:\Projects\RFC_ARCHIVE\output` |
| Former working repository | `C:\Projects\A_Recent_Projects\CWMS_Migration` |

Do not reuse those simulation/date choices blindly. Confirm the open model and
active forecast. Names `Ensemble_Test` and `Ensebmle_Test` both appeared in earlier
work; use the actual filesystem path, not a corrected spelling guessed from notes.

## Reopen months later, without Git

1. Back up the complete existing watershed and any study forecasts/results you
   intend to retain. Preserve this embedded kit and original-source folders.
2. Read `scripts/workflow-mode.json`; compare it with the environment you intend
   to use. It records installation mode, not automatic GUI detection.
3. Verify the original HEC application and the `hydro39` Python environment.
   Use the inventory to identify dependencies and versions. Recreate/install them
   through approved channels if the old machine/environment is gone. The kit does
   not bundle Conda, Python packages, HEC applications or authentication.
4. If changing mode, close both applications and use the embedded installer as
   described in WORKFLOW_PACKAGE.md. Activate RTS mode only in the imported copy.
5. Open the environment's launcher. Verify target, dates, paths, trial convention,
   inputs and native rule bindings before changing or computing anything.
6. Preserve existing results. Run a small serial baseline, verify initialization
   receipts and native completion, then validate outputs before a large study.
7. Record local test findings and changes in `PROJECT_LOCAL_NOTES.md`. Keep an
   example successful log and the exact configuration used with study results.

## Before deleting the repository

Run the final package command supplied with this handoff and verify these exist
in the actual standalone watershed: root `WORKFLOW_README.md`, `PROJECT_RESUME.md`,
`scripts/workflow-kit/PROJECT_START_HERE.md`, SOP, both detailed references,
`installation-inventory.json`, `manifest.json`, installer and runtime payload.
Open the documents from that location. Test the standalone launcher there.
A Git pull alone does not put documentation or scripts into the watershed.

Retain the complete model and required forecasts/data separately; the kit is
scripts/documentation, not a complete model or reproducibility archive. Removing
an unneeded checkout is different from deleting the only copy of study inputs,
results, saved configuration libraries or the Python environment.

## POR and model checks

[Single POR / Model Check](STANDALONE_POR_MODEL_CHECK.md) documents the mode toggle,
OSI-free single-run plotting and launching the existing model checker for one
POR output or one exact ensemble member. Native mode/input settings are not
changed by the toggle.

## Optional follow-up experiment

[Conditional diversion postprocessing](DIVERSION_POSTPROCESS.md) reads completed
results and writes separate adjusted flows. It is opt-in, not part of the accepted
baseline/augmentation workflow. Review its routing/barrier assumptions and test
locally before use. The editor can also add inactive IRRM/Deep Drawdown reservoir
settings; native rule attachment still requires the ResSim editor.

## Known issues to carry forward

- Some optional FLOW-MINLIM archive reads contain no usable values. Actual native
  values versus reader behavior remain unresolved; see the next-session checklist.

- RTS baseline identity compares pool elevation/outflow, not every input. An
  input-only edit can retain an old archive when compared outputs are unchanged.
  Use a fresh forecast for a clean input-change experiment until this is resolved.
- Old output records can look successful after a failed compute. Check current
  logs, selected members and full time coverage; 100% alone is insufficient.
- Standalone Apply does not turn off augmentation or change native trial settings.
- Peak CSV cleanup is not a full-series archive suitable for augmentation.
- No season offered in RTS means required baseline coverage is unavailable.
- Parallel scripted ensemble support depends on the original application; the
  package neither repairs nor enables it through vendor software modifications.
