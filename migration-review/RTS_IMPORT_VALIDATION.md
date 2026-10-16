# Next session: fresh RTS import and workflow validation

Handoff: 16 October 2026. This is the next task, not a completed validation.
The standalone watershed remains the source; use a separate imported RTS copy.
Start with original HEC software and serial compute. No experimental JAR change
is required or installed by this workflow.

## Where we stopped

Standalone configuration, named archives/plots and Model Check have been exercised
by the operator. Recent fixes include explicit POR/ensemble targeting, uppercase
DSS record matching, installed archive dependencies and saved plot references.
Automated checks exercise the Python/package logic; they do not certify a fresh
native RTS import. The latest package must be installed in the source watershed
before importing it. A Git pull alone does not update the watershed.

An open issue remains: some archived `FLOW-MINLIM` reads yielded no finite values.
DSSVue shows these records in the catalog, but their actual tabulated values have
not yet been checked. Do not conclude the native records are empty or that ResSim
failed to write them. The plot index groups optional-reference warnings; detailed
member/location/path errors are in `reference-read-report.csv`. Missing values
are not zero and are never reconstructed from actual outflow.

For the next diagnostic, open BLUE RIVER / FLOW-MINLIM /
C:001985|CON_SEASON0 in the source simulation DSS and tabulate a few values. If
numeric values exist, compare that exact physical/logical path and date window
with the archive read report before changing output settings or recomputing.
Keep the existing DSS, archive and logs so this can be investigated later.

## 1. Preserve the source and prepare the imported copy

1. Finish compute, close DSS views and close both applications before updating
   scripts. Run the package command in [packaging instructions](WORKFLOW_PACKAGE.md).
2. Open source watershed `WORKFLOW_README.html`. Confirm this handoff, the combined
   SOP, both detailed references and the latest saved-results instructions exist.
   Keep `PROJECT_LOCAL_NOTES.md`, saved JSON configurations, native data and results.
3. Import the complete watershed into RTS with the normal native import procedure.
   Confirm the destination root and retain the standalone source unchanged. Check
   scripts, CSV schedules, native alternatives, mappings, external modules and
   `scripts/workflow-kit` survived. A kit alone is not a complete watershed.
4. Close RTS/ResSim and activate RTS script mode only in the imported watershed,
   using the embedded installer command in WORKFLOW_PACKAGE.md. Do not pass the
   standalone source or a forecast directory to that mode-switch command.
5. Reopen RTS and verify model/program linking. Use the RTS menu launcher, not the
   standalone menu. Verify Python/DSS prerequisites and CWMS/network access.

## 2. Validate the baseline path first

1. Create a fresh forecast with valid CWMS lookback and current RFC coverage.
   Confirm the forecast alternative, DSS path, dates and timezone in the RTS menu.
   Current RFC download is not a historical RFC archive extract.
2. Run Initial Extract once. Check inputs and intended historical/synthetic member
   IDs. Current synthetic IDs are 3000–3002 for daily percentile traces and 3003
   for OSI; old outputs/IDs are not automatically renamed.
3. Open a saved baseline configuration, verify the new target, Save as needed,
   then Apply for Baseline Compute. Confirm augmentation is disabled. Standalone
   pointers/receipts do not establish an RTS accepted baseline.
4. Run a small serial case first to check initialization and native data/mappings.
   Verify current completion logs, selected member coverage and initialization
   receipts. Existing catalog records or a 100% display alone are insufficient.
5. Accept/archive the successful baseline. Inspect the created baseline ID and
   compact archive. Confirm accepting results did not initiate another extract.

A short plumbing test may not contain a valid augmentation season. For the full
augmentation test, prepare a baseline covering April 1, travel-time lead-in and
the selected season end, within available inputs. Do not force a season onto a
short October run. Use ALL_ABUNDANT (4), not the zero dummy, when fixed-abundant
water-year mode is selected.

## 3. Validate the complete baseline/augmentation pair

Follow [RTS operator SOP](RTS_OPERATOR_SOP.md) for the exact controls:

1. Name/save an augmentation configuration and select an offered valid season.
2. Process and Load Releases against the accepted baseline. Check successful
   activation and the next-compute label; processing does not run ResSim.
3. Compute augmented in RTS, verify completion and accept/archive the result.
4. Plot the saved baseline/result pair. Check pairing labels, rule curves,
   reservoir minimum requirements and Salem/Albany targets where available.
   Review reference warnings/read reports; never substitute zero for missing data.
5. Close/reopen the menu and plot saved results again to check persistence.
6. Modify a baseline setting through the editor, save it under a new descriptive
   name, Apply, and recompute unaugmented. Accept the new baseline, create/load a
   new scheme, compute and archive its result. Check that old archives/plots still
   identify the earlier baseline and that the new result pairs with the new one.
7. Record outcomes before expanding to a large ensemble or trying parallel compute.
   Standalone Model Check availability does not establish equivalent RTS GUI
   integration; assess that separately if needed after the main workflow passes.

## Evidence to retain

Record actual paths, versions, tested members/date coverage, configuration names
and IDs, baseline/scheme/result IDs and relevant log/report locations in the
imported copy's `PROJECT_LOCAL_NOTES.md`. Retain a successful compute log and
selected configuration with each validation result. Use the detailed references
for artifact producers and locations rather than assuming source/forecast paths
are interchangeable.

| Check | Handoff status |
| --- | --- |
| Fresh native import of the latest packaged watershed | Not yet tested |
| Imported linking, scripts and RTS mode activation | Not yet tested |
| Fresh extract and baseline Save/Apply/compute/accept | Not yet tested |
| Full-season augmentation process/load/compute/accept | Not yet tested |
| Saved pair plots and persistence after reopening | Not yet tested |
| New baseline/new scheme with earlier archives preserved | Not yet tested |
| Native FLOW-MINLIM values versus archive-reader result | Unresolved; inspect actual values |

Do not delete the repository or source study data as part of this validation.
Once the installed portable kit and documentation have been verified locally,
repository retention can be decided independently; the kit does not bundle HEC,
Python, credentials or all study inputs/results.
