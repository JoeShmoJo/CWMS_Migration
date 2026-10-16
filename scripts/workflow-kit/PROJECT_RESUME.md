# PROJECT RESUME — read this first after re-uploading the watershed

Last handoff: **16 October 2026**. 

## Immediate next task

**Import a fresh copy of this complete standalone watershed into CWMS/HEC-RTS,
activate RTS script mode in the imported copy, and validate the complete workflow.**
Use `scripts/workflow-kit/RTS_IMPORT_VALIDATION.md` for the staged checklist.
This latest native import has **not** been verified. Earlier RTS operation and
Python/package tests do not establish that a new import works.

Keep the working standalone source separate. Begin with original HEC software and
serial compute; do not make parallel-compute changes during the import test.

## Locate the project before editing

The known source watershed was:

```text
C:\Projects\FIRO\watershed\NWP_Willamette_Master_2026_10_05_DamagesPrevented
```

The source contained simulation folders with similar names, including the typo
`Ensebmle_Test`. Another example was `Flood_96_3hour` / `Temp3Hour`, a single POR
simulation. Select the real simulation folder and alternative explicitly; do not
silently correct spelling or assume the selected alternative is Con_Season.
RTS examples used a native output suffix C0; standalone Con_Season used
CON_SEASON0. Read the actual F-parts instead of interchanging these conventions.

## Entry points and documentation

At the watershed root:

- `PROJECT_RESUME.md`: this continuation brief, refreshed by packaging.
- `WORKFLOW_README.html`: double-click for the offline documentation site.
- `PROJECT_LOCAL_NOTES.md`: operator's actual test findings; preserved by packaging.

Inside `scripts/workflow-kit`:

- `PROJECT_START_HERE.md`: project map and operating limits.
- `WORKFLOW_SOP.md`: simple standalone and RTS SOP.
- `STANDALONE_WORKFLOW_REFERENCE.md` and `RTS_WORKFLOW_REFERENCE.md`: detailed
  inputs, outputs, producers, locations, configuration and archive behavior.
- `WORKFLOW_PACKAGE.md`: installation, import, mode switching, backups and rollback.
- `RTS_IMPORT_VALIDATION.md`: next-session checklist and acceptance evidence.
- `STANDALONE_SAVED_RESULTS.md`: saved results, plots and reference warnings.
- `STANDALONE_POR_MODEL_CHECK.md`: POR/ensemble modes and exact-member Model Check.
- `installation-inventory.json`: paths, versions and file hashes at packaging time.
- `manifest.json`: kit payload checksums, not a certificate of successful compute.

Markdown is the source. The matching offline HTML is in
`scripts/workflow-kit/documentation`. The kit supplements the complete model;
it is not a complete watershed, Python environment or HEC application installer.

## What works / intended design

The user has exercised the standalone configuration editor, Model Check and basic
ensemble saved-result plots. Reference plotting was recently added and still has
an open data-read issue below. The newest packaged model has not yet completed a
fresh native RTS import validation.

Use **one native alternative**, changing named baseline settings through the menu
rather than multiplying alternatives/trials. Save stores reusable configuration;
Apply activates a snapshot for the selected target; native compute is manual.
Archive completed baseline/results under descriptive names to compare later.
Do not replace saved history with live DSS records when plotting.

- Standalone menu: `scripts/STANDALONE_WORKFLOW_MENU.py`, launched in ResSim's
  Simulation module. Explicit simulation, alternative and Ensemble/Single POR.
- RTS menu: `scripts/RTS_WORKFLOW_MENU.py`, launched through RTS. Reads forecast
  metadata. Do not use the standalone launcher to operate an RTS forecast.
- Mode is recorded in `scripts/workflow-mode.json`; it is not automatic GUI detection.
- Shared baseline editor uses eleven rule groups and named portable JSON sets.
  Inactive/null IRRM and Deep Drawdown entries are neutral; effects still require
  native rule attachment. Adding a reservoir to JSON does not attach a native rule.
- Normal menus do not depend on a user-edited shared CONFIG.py. Older job scripts
  receive a private temporary compatibility module. Keep legacy files intact.
- POR can use augmentation and saved-result plotting. OSI applies only to ensembles.
  The POR augmentation adapter supplies daily inputs from native blocks; subdaily
  flows use complete-day period averages, storage uses day-end values. Validate
  the calculation and native requirement mapping locally before study use.
- Synthetic ensemble IDs: 3000/3001/3002 daily percentile traces; 3003 OSI. Old
  files may use 2026–2029. Do not relabel those automatically or include synthetic
  traces in historical probability bands.
- Model Check reads the selected POR output or exactly one ensemble member.
  Optional report name; unique report directories. It does not start compute.
- Native uppercase DSS names are supported by case-insensitive extraction/report
  matching. Original DSS paths and values are retained.

## Code and data map for investigation

Operational Python files are in `scripts/ExternalPython`. The kit has maintained
copies under `scripts/workflow-kit/ExternalPython`; install/repackage deliberately
so these do not drift. In a reconstructed full repository, maintained copies were
under `migration-review/ExternalPython` and the original checker under `model_check`.

| Area | Main files / locations |
| --- | --- |
| Package and mode transition | workflow-kit/Package-Workflow.py, Install-StandaloneConfiguration.py |
| Baseline editor/runtime | ExternalPython/baseline_configuration.py, standalone_configuration.py; scripts/*_baseline_runtime.py; preserved original rule implementations |
| Standalone jobs | ExternalPython/standalone_jobs.py; native model-specific download/augmentation scripts |
| POR augmentation reader | ExternalPython/standalone_por_augmentation.py |
| Named archives and plots | ExternalPython/standalone_results.py, run_archive.py, run_data_cache.py, plot_rts_forecast.py |
| Model Check adapter | ExternalPython/standalone_model_check.py; scripts/model_check/extract_dss.py and check_model.py |
| Source standalone results | rss/<actual simulation>/simulation.dss |
| Accepted standalone archives | rss/<simulation>/standalone-results/run-<id>/capture.json, run-archive.json, series.npz, optional configuration-provenance/ |
| Standalone plots | rss/<simulation>/output_plots/archived-<id>/index.html, plot HTML/CSVs, reference CSVs, selection.json |
| Reference failures | Same plot folder/reference-read-report.csv |
| Model check output | rss/<simulation>/model-check-runs/check-<name>-<id>/; check-context.json and extracted report directory |
| Browser/job logs | standalone-workflow-logs/results-*.log, job-*.log, configuration-*.log under the watershed |
| Saved/applied settings | scripts/baseline-configuration-library/; simulation baseline-configurations/ and standalone-baseline-config-active.json; RTS uses its forecast root |

Compact archives store selected arrays, not copies of the whole DSS file.
PostProcess peak/max CSV cleanup is not a replacement for full-series archives.

## Open issue: minimum-limit reference reads

Recent plots reported many optional `FLOW-MINLIM` records as “Empty or wholly
missing time series.” The native DSSVue catalog shows BLUE RIVER/FLOW-MINLIM for
member 1985 and others. **Catalog presence is confirmed; actual native tabulated
values have not yet been checked.** It is not established whether the data are
missing or our archive reader is failing. Do not declare this resolved merely
because warnings were grouped or the other plots work.

Next diagnostic: tabulate BLUE RIVER / FLOW-MINLIM / C:001985|CON_SEASON0 in the
existing source simulation.dss. Compare a few real values, dates and the exact
physical pathname with reference-read-report.csv and archived metadata. If values
exist, debug run_archive.capture_run and baseline_versions.read_fingerprint_series
with that record. Preserve the DSS and original archive; do not recompute, invent
zeros, fill missing limits from outflow or silently replace archive provenance.

Rule curves, combined-minimum/withdrawal demands, prepared augmentation minimums,
mainstem targets and applied minimum limits are distinct references. Prepared
requirements are shown for result archives, not baseline archives, so stale
prepared inputs are not represented as baseline requirements. Older archives may
lack newly added references. Empty optional references do not by themselves mean
pool elevation/outflow results failed. Keep detailed failures even when summarizing
warnings. No claim is made that every native output is fresh after a failed run.


## Rules for resuming safely and efficiently

1. Read this file, PROJECT_LOCAL_NOTES.md, the applicable SOP and the import
   checklist. Inventory actual files/mode before changing them. Do not assume
   another machine can access the Windows watershed directly.
2. Reuse the existing test watershed for successive tests; it is large. Make a
   separate imported RTS copy for the transition, but avoid repeated whole-model
   copies for small script experiments. Preserve working source/configuration/data.
3. Do not modify, decompile or recreate modifications to vendor JARs. Experimental
   compiler isolation was retired after review of HEC terms. The workflow uses
   original supported HEC applications and user scripts; Java experiments are not
   prerequisites. Do not infer thread safety from a successful serial run.
4. Test installed modules in a fresh process, without repository imports masking
   missing dependencies. An earlier archive failure was exactly that omission.
5. The old repository tests were in tests/. They may not be present if only the
   watershed/kit is re-uploaded; do not claim to have run them. When available,
   run relevant Python unittest tests; native Windows/DSS validation is separate.
6. Python jobs use hydro39 at
   `%LOCALAPPDATA%\miniconda3\envs\hydro39\python.exe`; the GUI-side scripts are
   Jython. The kit does not provide Python packages, native DSS bindings, HEC,
   CWMS credentials/certificates or network access. Inspect existing prerequisites.
7. Keep PowerShell commands on one line for the operator. A repository edit/pull
   alone never installs into the watershed. Repackage and reopen the menu to test
   delivered behavior; use the embedded mode installer for RTS transitions.
8. Native output presence or 100% progress does not prove successful fresh compute.
   Verify selected member/time coverage and current logs. Record observed outcomes
   separately from automated tests and assumptions.

Historical RFC archive loading remains paused pending missing station data. The
optional diversion postprocessor is a separate opt-in experiment with routing and
reservoir-barrier limitations; it is not a substitute for native operating feedback.

## Updating this handoff after the next session

Record the actual imported root, application versions, selected forecast/run,
member/date coverage, baseline/scheme/result IDs and evidence locations. Mark each
RTS_IMPORT_VALIDATION check passed/failed/unrun. Resolve or retain the minimum-limit
question explicitly. Update this file and the operator's PROJECT_LOCAL_NOTES.md,
then refresh the portable kit/HTML before removing any temporary checkout.
