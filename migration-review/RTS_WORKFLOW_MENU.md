# RTS ensemble workflow menu

Install using `Install-ForecastExtraction.ps1`. Open a forecast, select its run,
and run `scripts/RTS_WORKFLOW_MENU.py` in the RTS watershed Script Editor.
The window stays open between steps. It follows the supplied DP menu pattern,
but invokes hydro39 Python in background workers rather than loading the DP
calculation modules.

Verify the displayed forecast, time window, run code, and member ranges. The
initial historical range is 1981-1991 and synthetic range 3000-3002; change them
to match the forecast you actually created. The initial scheme name is
scheme_03 to avoid replacing the existing scheme_02. Season end is explicit
and defaults to September 30 of the forecast end year; it must fit available
baseline coverage. Fixed-abundant mode requires constant water-year code 4.

For ForecastTest_1055, click **Link existing baseline** once. Confirm that the
displayed forecast dates/model/inputs still match the baseline already created.
The backend validates the archived DSS checksum and forecast/run-code scope;
the old archive did not record a full RTS time window, so operator confirmation
is required to establish that association. The action does not change the
baseline DSS. Then use **Choose saved scheme** to select scheme_02, or prepare
a new unique scheme name.

## New forecast sequence

1. Extract to archive. Successful extraction produces a completion record and
   checksum; the new folder is filled into the menu automatically.
2. Load extract / baseline. Validates the selected forecast/run/dates, backs up
   the live DSS, and copies the completed extract in baseline mode.
3. Compute the baseline with the normal RTS Compute action.
4. Save as baseline after compute, then prepare augmentation under a new scheme
   name. The first preparation can still capture the baseline for compatibility.
5. Load the selected scheme, then compute manually in RTS.
6. Archive + compare plots, then Open last plots.

Current forecast plots are also available without a scheme comparison. Reset
augmentation disables the active scheme for the next compute but retains its
records and archives. It does not recompute the baseline automatically.

## Selection, locks, and logs

After selecting another forecast/run or editing dates, click **Refresh selected
forecast**. Actions reject a selected context that differs from the displayed
one. Do not start RTS compute while a menu task is running. Action buttons and
settings are disabled during each task, with an indeterminate progress bar,
streamed output, and separate UTF-8 logs under the forecast's workflow-logs.
Backend task locks prevent overlapping menu jobs on the same forecast.

Finish compute and close DSSVue before file operations. If Windows still holds
the DSS, close the forecast in RTS while leaving this menu open, then check
**Use the displayed forecast after closing it in RTS**. Refresh before closing
if dates changed. A different actively selected forecast is never silently
substituted. Reopen the same forecast for manual compute after loading.

The normal menu close button is disabled while a task runs. If RTS is forcibly
closed, a leftover `.rts-workflow-task.json` may remain. Inspect its recorded
PID and ensure the task has stopped before removing the stale lock.

Load extract refuses to change inputs in a forecast that already has an
archived comparison baseline. Create a new forecast when downloaded inputs or dates change. Model/operation
set changes can use the explicit baseline edit workflow below. Older extraction archives without completion metadata cannot be loaded
through the menu; new extractions create it automatically.

The menu does not start a model compute or certify its success. Check RTS logs
before treating captured outputs as a successfully computed scheme. Standalone
operation sets, scripts, and trial behavior remain unchanged.

The backend has cloud tests; the Swing UI and Windows DSS operations require
testing in actual RTS. To use a different imported watershed when the Script
Editor omits `__file__`, set EXTERNAL_PYTHON_DIR once in the menu script.

## Explicit baseline edits and versions

1. **Load baseline (augmentation off)** restores the current saved unaugmented
   DSS, backs up the live DSS, disables augmentation, and records an edit session.
2. Reopen the forecast, edit the model/operation set, and compute normally in RTS.
3. Finish compute and close DSS views. **Save as baseline after compute** asks
   you to confirm the unaugmented compute finished; it cannot verify RTS status.
4. If the logical time series match, the console says **Baseline results
   unchanged** and keeps the version. If values differ, it saves an immutable
   new version and marks older augmented result pairs **Previous baseline**.
5. Prepare a new uniquely named scheme from the current baseline. An older
   scheme can still be plotted with its original baseline, but cannot be loaded
   for a new compute after the baseline changes. Loading a scheme invalidates
   the baseline edit session to prevent accidentally saving augmented output.

Comparison includes the timestamp/value sequences, units, and series types of
reservoir elevations, flows and storage; river flows; local minimum rules;
water-year type; rule curves; and hydrologic inputs present in the DSS. It ignores
DSS byte layout, calendar-block names, pathname case, and missing-value payloads.
Finite values are compared exactly. Missing previously archived logical series
cause a refusal to save rather than silently accepting an incomplete compute.
Prepared augmentation records and outputs from other run codes are excluded.
Operation-set files are not used to decide whether baseline results changed.
This retains computed data and configurations, not a recoverable copy of every
model edit. Dates/extracted-input changes still use a new forecast.

Existing `baseline` and `scheme_02` archives are adopted as baseline-0001 without
rewriting their DSS or manifests. New versions use baseline-0002, etc. under
augmentation-archives. Schemes resolve their own baseline by ID/checksum; they
do not follow the current-baseline pointer when plotting older results.

## Archived results and deletion

**List archived results** refreshes the result catalog. **Choose archived result**
shows scheme, capture date, and Current/Previous baseline status. **Plot selected
archived pair** reads that capture with its original baseline without using the
live forecast or requiring its scheme to be active. Each plotting invocation
creates a new plots folder, preserving earlier plots.

**Delete selected archived result** asks for confirmation naming the folder.
It removes that result's DSS and plots while retaining scheme inputs and every
baseline version, including baselines referenced by other results. Baselines and
whole schemes cannot be selected for deletion. Failed captures are not listed.

The append-only `augmentation-archives/action-history.jsonl` records baseline
loads/saves (including unchanged saves), scheme preparation/loading, captures,
and requested/completed deletions. `baseline-versions.json` holds the current
baseline pointer and version provenance; `archive-index.json` holds the current
result labels. Do not manually edit these files or the immutable DSS copies.
Old plot pages retain the status displayed when generated; regenerate an
archived pair to show its current Current/Previous baseline label.
