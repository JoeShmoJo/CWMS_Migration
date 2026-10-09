# RTS ensemble workflow

Install with `Install-ForecastExtraction.ps1`, close the old menu, and reopen
`scripts/RTS_WORKFLOW_MENU.py` from the watershed Script Editor. The main window
has greyed-out forecast metadata and four workflow actions. Manual model compute
stays in RTS. The maintained standalone configuration and trial workflow are not
modified.

## Initial Extract

Downloads inputs to a unique archive, then loads that invocation's verified
completed DSS into the displayed forecast. Failed/partial extractions are never
loaded, and an older extraction is never substituted. Existing live DSS is
backed up. Initial Extract refuses to replace inputs once a baseline is saved;
use a new forecast for different dates/downloads.

After extracting, reopen the forecast, modify the base alternative if needed,
and compute in RTS. Finish compute before continuing.

## Augmentation Configuration

Opening this action asks whether the current manual compute finished
successfully. **Yes** accepts and archives its results. Unaugmented results
establish or update the baseline; augmented results are saved under their
configuration/baseline pairing. **No** opens the editor using the saved baseline
without accepting live outputs. A saved baseline is required. **Cancel** stops.
An identical augmented DSS already archived for that configuration is reused.

The editor initially reads the installed `MinFlowSalemAlbanyConfig.csv`. Its
reservoir table retains every CSV variable. Reservoir names/abbreviations are
read-only; participation uses checkboxes, and numeric settings can be edited.
The current calculation requires identical Salem/Albany participation, Lookout
Point participation, and Hills Creek combined with Lookout Point. The preparer
validates the configuration and required model records before loading anything.
Parameters retained in the table do not imply new calculation logic: existing
algorithm/state-variable limitations still apply.

- **Open Configuration** reads a previously saved reusable JSON configuration.
- **Save Configuration** validates and saves JSON, normally under the watershed's
  `scripts/rts-augmentation-configurations`. The file chooser permits another
  folder, such as a maintained repository. The file contains the name, reservoir
  table, short-forecast length and water-year interpretation. It contains no
  forecast dates, ensemble members or baseline references. Preserve these files
  when reimporting a watershed.
- **Process and Load Releases** optionally accepts a newly completed compute,
  calculates releases against the current saved unaugmented baseline, archives
  the configuration and releases under a unique pairing, backs up live DSS,
  and loads the releases. It then instructs the user to reopen and compute in
  RTS. Do not re-extract.

Actual member IDs and run code come from finite computed outputs, not editable
main-window defaults. Historical members below 3000 and synthetic members at or
above 3000 remain separate in plots. The conservation-season chooser lists
covered years; the target end is the earlier of October 31 and the common saved
output coverage. Preparation separately checks storage, minimum rules, WY type,
and travel-time lead-in. No missing data is extrapolated or silently zero-filled.
If no conservation season is covered, configuration can be saved but processing
is disabled. Short-forecast days and water-year interpretation are configuration
settings; fixed-abundant mode verifies the constant code 4.

The editor uses a temporary CSV snapshot. Processing never overwrites the
working standalone/imported configuration CSV. Each scheme keeps its own CSV,
calculation settings, reusable JSON, required target tables and release records.
Reusable JSON contains the reservoir configuration and calculation settings;
target tables and median-inflow inputs come from the maintained watershed files
and are snapshotted when a scheme is prepared.
Reusing a configuration in another forecast recalculates its releases.

## Plot Results

The same completion question allows a just-computed run to be accepted before
opening the chooser. Choose **No** to browse existing archives without touching
live results. The chooser lists saved unaugmented baseline versions and archived
augmented results, labelled Current baseline or Previous baseline.

Select one run, or Ctrl-click two distinct runs, then **Plot Selected**. Single
run plots show ensemble outputs; two-run comparisons use paired valid historical
members, with synthetic traces separate. Any two saved runs can be compared,
including two augmentation configurations. Comparisons across baseline versions
are labelled explicitly: differences include baseline changes. Augmented plots
include prepared mainstem targets and per-member minimum-release overlays;
different member requirements have a visible minimum/maximum range, with exact
individual traces available in the legend; identical requirements are shown once. Baseline-only plots have no augmentation overlay.

Plotting uses verified caches of archived run data, never live forecast outputs,
and does not require a selected configuration to be active. It creates a fresh `output_plots/saved-runs-*`
folder with offline HTML, source CSVs, paired differences, requirement CSVs,
selection metadata, and a read report. Earlier plots remain archived. Their labels reflect when they were generated;
the chooser and newly generated plots use current baseline-version status. The index
opens automatically; Open Last Plots reopens the most recent menu-generated plots.

**Delete Selected Augmented Result** confirms the specific result before deleting
its DSS, embedded older plots, and saved-runs plot archives that include that
result (including comparisons). Other runs, baseline versions, configuration
inputs, and action history remain. Baselines cannot be deleted from this window.
The list refreshes after deletion.

## Reset Baseline

Warns that the baseline may change and offers to archive completed current
results first. It disables augmentation and records that an unaugmented compute
is pending. It does not load an earlier run's DSS over the forecast or change
any baseline version/result label immediately.

Modify the base alternative if needed and compute manually in RTS. After it
finishes, open Augmentation Configuration or Plot Results and choose **Yes** to
accept the completed results. Matching logical series keep the baseline version
and print **Baseline results unchanged**. Changed series produce a new immutable
baseline and label older augmented results **Previous baseline**. Processing
augmentation while a reset baseline is still awaiting acceptance is refused.

Comparison uses timestamps, values, units and types of elevations, flows,
storage, local minimum rules, WY type, rule curves and hydrologic inputs. It
ignores DSS layout/calendar-block names, pathname case and missing-value payloads.
Finite values are compared exactly. Missing previously archived logical series
cause refusal to accept an incomplete baseline. Operation-set files are not used
to decide whether computed results changed, and operation sets are not restored
from result archives. A configuration always calculates against the current
baseline; previous results remain available only for plotting/deletion in the UI.

## Metadata, locks and history

Refresh forecast metadata after switching the selected run or changing dates.
Tasks refuse a changed selected context. Finish compute and close DSSVue before
file operations. If Windows holds a DSS lock, close the forecast while keeping
the menu open and select **Use this displayed forecast after closing it in RTS**.
Refresh metadata before closing if anything changed; reopen for manual compute.

Background hydro39 jobs stream output and write UTF-8 logs under `workflow-logs`.
Controls are disabled during jobs; backend task locks prevent overlapping menu
jobs. Do not start RTS compute concurrently. If RTS is forcibly closed, inspect
the PID in `.rts-workflow-task.json` before removing a stale lock.

Existing `baseline`/`scheme_02` archives are adopted as baseline-0001 without
rewriting their DSS. New versions are immutable. `baseline-versions.json` records
provenance; `archive-index.json` labels result pairs; `workflow-pending.json`
records whether a manual compute is awaiting acceptance. The append-only
`action-history.jsonl` records acceptance, reset, preparation/loading, capture,
plotting and deletion. Do not edit these metadata files or archived DSS copies.

The completion question is operator confirmation, not an RTS success detector.
Check compute status/logs before answering Yes; old outputs can survive a failed
compute. Cloud tests use mocked DSS I/O. The table/configuration round-trip was
also checked with real Swing classes under Jython 2.7.3 and Java 21; the full
window and Windows DSS operations still require testing in RTS.


Optional developer smoke check (Jython jar installed separately):

```sh
java -Djava.awt.headless=true -jar /path/to/jython-standalone-2.7.3.jar tests/check_swing_configuration.py
```

This compiles the menu and exercises actual Swing table checkboxes, identifier
column protection, cell edits and portable configuration round-tripping without
starting an RTS window or opening DSS files.


## Archived data caches

Accepting a completed run creates `run-data-cache-C0` beside its archived
`forecast.dss`. Older archives build this cache on their first plot or
augmentation preparation. A single catalog pass identifies actual computed
series, combines calendar blocks, and caches reservoir elevations, storage,
inflows/outflows, river flows, Combined Min Trib requirements and water-year
inputs. Coverage and ensemble membership are stored with the arrays, so opening
configuration does not reread every series just to infer the time window.

`series.npz` contains compressed NumPy arrays, loaded without pickle. The JSON
manifest retains original logical DSS pathnames, units, data types, coverage,
timezone, source-file checksum and cache checksum. Timestamps and values are
stored together in the array file. Missing values and gaps are
preserved. Cache-backed augmentation uses the same unit, daily coverage,
water-year and finite-value checks as DSS-backed calculation. Its computed
release records are still written to `augmentation.dss` and loaded into the live
forecast for manual RTS compute.

Subsequent saved-run comparisons and configuration preparations reuse the
cache. Source and cache byte checksums are still verified; this does read file
bytes, but avoids repeated DSS catalogs and time-series retrieval. Cache build,
validation and total plot times are printed in the console. The original DSS
remains the complete archive, and accepting a newly computed baseline still
compares its hydrologic series to identify baseline changes.

Saved-run plots use `CON_SEASON_RULE_CURVES.csv` directly, expanded over the
plotted dates. They do not search the ResSim output or CWMS DSS for rule curves
with potentially different coverage. Big Cliff and Dexter receive no curve from
this CSV. Each plot archive contains the actual CSV schedule, its checksum, and
the expanded per-plot curve data. Prepared release/target CSVs are loaded once
per scheme per plotting invocation, rather than once per plot.

Caches are disposable derived files. Missing, incompatible or checksum-damaged
caches rebuild automatically from their archived DSS. To retry a record read
that failed during cache creation, close the menu and remove only that run's
`run-data-cache-C0` folder; its next use rebuilds it. Deleting an augmented result
also removes its cache. No standalone modules or configuration CSVs are changed
by caching.
