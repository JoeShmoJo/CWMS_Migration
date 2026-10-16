# Operator SOP: standalone ResSim and RTS

Start with [project handoff](PROJECT_START_HERE.md). For exact files and producers,
use the [standalone/shared reference](STANDALONE_WORKFLOW_REFERENCE.md) and
[RTS reference](RTS_WORKFLOW_REFERENCE.md). All compute is manual in ResSim/RTS.

## Common rules

- Saving a configuration stores settings. Applying activates settings for the
  target's next initialization. Computing produces results. RTS acceptance archives
  completed results. These are four separate actions.
- Finish computes and close DSS views before file-writing jobs. Restart once after
  script installation/mode changes. Verify every target banner before Apply.
- Keep one native model alternative and change named settings within it. The editor
  does not change native operation sets, rule bindings, input mappings or dates.
- Preserve outputs needed for comparison before recomputing. Do not accept a failed
  or partial run. Check current native logs and all intended members/window.

## A. Standalone ResSim

1. Open the watershed and desired simulation in the Simulation module. Note the
   simulation directory and alternative shown in Simulation Control.
2. Open the Script Editor in that module and run this single line:

```python
from hec.script import ClientAppWrapper; import os; execfile(os.path.join(str(ClientAppWrapper.getWatershed().getWkspDir()), 'scripts', 'STANDALONE_WORKFLOW_MENU.py'))
```

3. **For extraction, augmentation and plotting:** Open CONFIG.py in the menu and
   check SIM_NAME, ALTERNATIVE_NAME_STEP1, TRIAL, TRIAL_SUFFIXES and OSI member
   selection. Save it. These jobs use CONFIG.py independently of baseline selectors.
   Check downloader dates/mappings and rule-curve coverage in installed scripts/model.
4. If inputs are needed, run **Extract inputs (all four steps)**. Wait for successful
   completion and inspect the job log and actual simulation.dss input coverage.
   Do not extract again merely to change baseline operating settings.
5. **For baseline settings:** Select the explicit simulation folder and enter the
   native alternative name. Open **Baseline Configuration**; verify the browser's
   target matches Simulation Control. Import legacy settings or open a saved set.
6. Edit/name **Save Configuration**, then **Apply to Standalone Alternative**.
   Save alone does not activate settings. Verify your model's baseline trial has
   augmentation disabled through its existing conventions; Apply does not do this.
7. Compute the baseline trial manually. Verify current log completion, ensemble
   coverage and initialization receipts. Preserve the baseline results if needed.
8. Configure the existing standalone augmentation reservoir/target CSVs and trials.
   **Calculate augmentation** reads the CONFIG-selected baseline outputs and writes
   release requirements into that simulation DSS. Verify the log and paths.
9. Compute the augmented trial manually. Use **Plot ensemble** for CONFIG.TRIAL or
   **Plot alternative/trial comparison** for CONFIG.TRIAL_SUFFIXES. These plot live
   standalone DSS outputs; they do not select RTS accepted archives.
10. For a new baseline, open/load/edit/save/apply another set to the same target,
    recompute baseline, recalculate augmentation and recompute augmented trials.
    Changing baseline settings does not make old augmentation requirements current.

Existing default legacy settings use AutoDetect with omitted augmentation trials
`0,2,3`; do not assume a locally edited alternative retains those defaults.
Native rules/trial bindings must agree with the intended comparison.

## B. RTS / CWMS

First import the complete watershed and activate RTS script mode in that copy,
using [package/import instructions](WORKFLOW_PACKAGE.md). Then:

1. Select the intended forecast/run. Run `scripts/RTS_WORKFLOW_MENU.py` in the RTS
   Script Editor. Verify forecast, run, DSS path, lookback, start/end and timezone.
   Refresh metadata if selection changed.
2. **Initial Extract** once. Wait for successful promotion and refresh/reopen the
   forecast as instructed. It loads inputs; it does not run ResSim.
3. **Baseline Configuration** → open/import/edit → **Save Configuration** →
   **Apply for Baseline Compute**. Apply disables RTS augmentation. Finish computes
   and release the forecast as instructed for file changes. Reopen/refresh afterward.
4. Confirm next compute has no augmentation; compute manually. Verify successful
   member completion and required coverage in current logs/results.
5. Open **Augmentation Configuration**. Answer **Yes** to accept the just-completed
   baseline. Yes is your confirmation of successful compute; No uses saved results;
   Cancel stops. Check the accepted baseline ID.
6. Name/configure/save the augmentation settings. Select an available season and
   **Process and Load Releases**. Answer Yes to an acceptance prompt only for new
   completed output; otherwise No. Wait for successful loading and check activation.
7. Reopen/refresh as instructed; compute manually with loaded augmentation. Do not
   run Initial Extract again. Confirm completion for all requested members.
8. **Plot Results** → Yes to accept the completed augmented run → select the baseline
   and its augmented result → plot. Check pairing labels and plot read reports.
9. For a new baseline: load/edit/save/apply baseline settings, compute unaugmented,
   accept, create/process/load a new scheme, compute augmented, accept and compare.
   Old result pairings remain attached to their original baselines.

Use the [full RTS SOP](RTS_OPERATOR_SOP.md) for coverage requirements, result
selection/deletion and detailed checks. Fixed-abundant water-year data must be
ALL_ABUNDANT **4**, not the zero dummy. A short October test may not support an
April–October augmentation calculation.

## Stop and diagnose

| Situation | Action |
| --- | --- |
| Wrong target | Close editor; choose correct simulation/alternative or forecast; reopen and Apply there |
| Missing input dates/members | Fix extraction or mapping before computing; do not infer coverage from catalog presence |
| Compute fails/hangs | Preserve log; inspect worker logs/current process; do not archive as successful |
| No initialized receipt | Check installed adapter/mode, exact output DSS and alternative; restart and retest |
| Archive/loader fails | Read printed job log; preserve candidate and recovery backup; do not repeatedly overwrite live data |
| No augmentation season | Use a baseline with necessary seasonal coverage |
| Reopening after a long break | Follow PROJECT_START_HERE.md and inventory before launching a large compute |
