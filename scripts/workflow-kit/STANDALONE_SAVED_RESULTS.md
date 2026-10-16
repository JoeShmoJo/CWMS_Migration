# Standalone: changing baselines, archiving results and plotting later

This replaces the normal standalone trial-plot workflow. The menu now has
**Archive / Plot Results** instead of Plot ensemble / Plot trial comparison.
Plot-trial settings and reference-line controls are retired from Baseline
Configuration. You select named saved runs for plotting, independently of live DSS.
RTS keeps its existing acceptance/scheme workflow; this standalone feature does
not change its archives or operators' steps.

Select Ensemble or Single POR in the menu. Single POR archives ordinary F-parts
and plots single traces without OSI or ensemble bands. The **Model Check** button
checks one POR output or one selected ensemble member. See the
[POR and Model Check reference](STANDALONE_POR_MODEL_CHECK.md).

## Short SOP

1. Select the simulation and native alternative in the standalone menu. Open
   Baseline Configuration, edit/save/apply operating settings. The only standalone
   extraction option remaining there is the OSI source member. The selected target
   supplies the simulation/alternative for jobs. CONFIG.py is not read or edited.
2. Extract if inputs are needed; verify native mappings, dates/member coverage and
   the alternative's baseline/augmentation conventions. The menu does not configure
   native trial augmentation behavior or change existing script date constants.
3. Compute the unaugmented baseline manually and check native success for every
   intended member and date. Before recomputing over those outputs, open
   **Archive / Plot Results** and refresh.
4. Choose the completed output suffix shown by the catalog, enter a useful name,
   select **New baseline**, and **Archive completed results**. Confirm only after
   checking actual compute completion. An output suffix such as CON_SEASON0 is an
   input selector at capture time, not a persistent plot-trial setting.
5. Calculate augmentation and compute using the existing model's augmentation
   setup. In the result browser choose the completed output, give it a name, select
   **Result paired with baseline**, select the correct archived baseline and archive.
   This pairing is operator-specified; the tool does not infer scheme activation
   or certify that the selected native trial was unaugmented/augmented.
6. Select one or two named archived runs (Ctrl-click for two) and **Plot selected
   saved runs**. Offline HTML plots and the plotted CSVs are generated from the
   archives, even if simulation.dss later changes or is removed.
7. To change baseline: edit/save/apply configuration, compute a fresh unaugmented
   baseline, archive it under a new name, recalculate/recompute augmentation and
   archive its results paired with the new baseline. Old data and pairings stay
   available. Unlike RTS fingerprint reuse, each explicit standalone capture is
   a separate immutable named result, even if its values match an older capture.

Native trials may still be used by the model to distinguish baseline/augmentation.
They are not the way you choose plotted results anymore. Archiving an existing
trial is supported through its exact output suffix; changing a source trial does
not change already archived data.

## Inputs, outputs and implementation

| Item | Location relative to standalone watershed | Producer / consumer |
| --- | --- | --- |
| Capture source | rss/<simulation>/simulation.dss | Native compute → archiver; never overwritten by archiver |
| Named run archive | rss/<simulation>/standalone-results/run-<id>/ | Explicit operator capture; retain |
| Primary arrays | Same directory, series.npz | Shared compact archiver → saved-run plotter |
| Data manifest | Same directory, run-archive.json | Array hashes, logical DSS paths, units/type/timezone/member series |
| Capture identity/pairing | Same directory, capture.json | Name, kind, baseline ID, suffix, members, UTC time, configuration ID, archive checksum |
| Applied configuration snapshot | Same directory, configuration-provenance/ when available | Copy of the active baseline set at capture; includes scripts/tables/receipts |
| Plot output | rss/<simulation>/output_plots/archived-<id>/ | Saved-run plotter; separate from older legacy plot folders |
| Browser entry/library | Same plot folder, index.html and plotly.min.js | Offline viewing; no CDN required |
| Individual plots | Same plot folder, plot-<n>.html | Elevations, outflows and selected control-point flows |
| Plotted source data | Same plot folder, plot-<n>-run-<id>.csv | Exact archived member values used in each plot |
| Plot selection | Same plot folder, selection.json | Selected capture metadata and baseline pairing flag |
| Browser/backend | scripts/ExternalPython/standalone_results.py | Local token-protected editor; no live compute initiation |
| Job runner | scripts/ExternalPython/standalone_jobs.py | Extraction/calculation from selected target and applied OSI setting |

The archiver reuses the RTS compact storage format and selected-series filtering.
It retains pool elevation/outflow, control-point flows and the shared supported
augmentation input series. It does not copy the whole DSS. There is no physical
forecast.dss inside a new archive; that name is an internal logical locator used
by the shared reader. Primary arrays cannot be regenerated from an unrelated
later live simulation. Corruption fails verification instead of substituting live
data. Pending failed captures remain under pending-<id> and are not published.

Config provenance is the active snapshot **at capture time**. It is not independent
proof that every record was produced using it. Capture before applying the next
configuration, confirm native logs and check required member/time coverage.
Source catalog presence and a 100% progress bar do not prove freshness. The tool
selects all cataloged members for that suffix, including potentially stale members
from older computes; use a clean test output when establishing reference results.

Historical member bands and individual traces are separate from common standalone/
RTS synthetic IDs: 3000 (daily 25%), 3001 (daily 50%), 3002 (daily 75%) and 3003
(OSI). New captures record synthetic member identity explicitly. Old archives
without that field retain the legacy 2026–2029 interpretation; they are not
rewritten. Two-run
plots are labelled when pairings differ, since differences may include baseline
changes. These are overlays, not a full causal attribution or validation report.
New captures and plots include available native rule curves, minimum limits and
prepared augmentation requirements, as described below. Older archives can lack
these reference records.

## CONFIG.py and older settings

The installed CONFIG.py file is retained so older manually launched scripts are
not destroyed. The normal menu no longer depends on it. Extraction/calculation
children receive a temporary private compatibility module containing only the
selected target and OSI source member. No shared CONFIG.py is opened, edited or
executed by those jobs. Default OSI member is 2011 until changed in Baseline
Configuration; review it before extraction. Older saved baseline sets can contain
retired trial plot fields; opening/applying migrates them without rewriting the
historical file. Old HTML plots and native trial results remain untouched.

Use the installed original HEC application and a supported compute mode. This
feature does not enable multithreading, modify native rule bindings or replace
the standalone augmentation calculator with RTS's scheme system. Test a small
serial case, archive/plot it, change/recompute/archive and verify the first archive
still plots the original values before a large study.


## OSI source member and migration to RTS IDs

The browser's osi_source_member selects the downloaded historical/percentile trace
to copy; destination is always 3003. For example, 2011 copies member 2011 inputs
into member 3003, retaining simulation timestamps and the original member. 3001
can be chosen to seed OSI from the daily median trace. 3003 itself is rejected as
a source. The source setting takes effect when extraction/copy runs, not on Apply.

Updated standalone extraction writes percentile IDs 3000–3002 and OSI ID 3003,
matching RTS. Re-extract into a clean test simulation/output after updating, then
select the new IDs in the native ensemble configuration. Change any explicit
standard/OSI input mapping from C:002029| to C:003003|. Generic member-substitution
paths need no per-record remapping. The installer changes scripts only; it does
not change native member selections, DSS mappings, existing DSS or archives.
Do not assume old 2026–2029 records were deleted, renamed or refreshed.

Standalone augmentation now discovers actual baseline pool-outflow members for
its native alternative's trial-0 suffix rather than a hardcoded 1981–2028 loop,
so computed 3000–3003 members can be processed. This does not certify freshness;
verify the native compute selection and remove stale records only through your
normal deliberate test-data preparation. Dates/constants outside member selection
are preserved from the actual installed scripts.

## Archive purpose versus simulation type

**Archive purpose** labels saved results as a new baseline or a result paired
with a saved baseline. It does not change POR/ensemble mode or native operations.
Those archive controls are not required for Model Check, which has a separate
page bound to the simulation and alternative selected in the main menu.

### Installed archive dependencies

The installer includes `scripts/ExternalPython/extraction_context.py`, required
by `write_rule_curves.py` when saved-result selection imports the shared reservoir
list. This helper must be installed alongside the archive modules, even for
standalone results with no forecast extraction. A browser message “No module
named 'extraction_context'” indicates an incomplete script installation, not
missing simulation records. Repackage/update the watershed and reopen its menu;
existing native results need not be recomputed. Installed archive selection and
capture are tested in a fresh isolated Python process without repository imports.

## Plot references, consistent with RTS

New standalone captures include selected computed rule-curve and minimum-release
records alongside plot outputs. Elevation plots show the saved native
`<reservoir>-Rule Curve / ELEV-ZONE` line. Outflow plots show available combined
minimum tributary/withdrawal demands, the prepared augmentation minimum release
(`FLOW-MIN-EXTERNALFLOWAUG`), and the actual applied minimum limit (`FLOW-MINLIM`)
with separate labels. Prepared requirements are shown for result archives, not
baseline archives, so leftover prepared inputs do not appear as baseline
requirements. Salem/Albany flow plots show available prepared/native
mainstem targets. Prepared inputs are included only for members with computed
pool results, so preparing more members than were computed does not enlarge the
archive's output-member selection.

A shared reference appears as one dashed line. If historical members differ,
their minimum, maximum and median are shown; synthetic members do not change
these summaries. POR references are single traces. Comparison plots label each
run's references separately. Missing points stay missing. Reference member data
are exported as `reference-*.csv` beside the offline HTML plots.

These are native records captured with that run, not current configuration values
silently substituted later. Plotting uses compact archived arrays and works after
live DSS deletion. Existing archives are unchanged and can lack these records;
the plot index and `selection.json` report missing references. To add references,
archive the still-available completed native results again under a new name.
No new compute is needed if the required native records are already present.
If the model did not save a required reference, its plot cannot show it; do not
infer a rule curve or requirement from actual elevations/outflows.

Empty cataloged optional reference records do not invalidate otherwise usable
pool/outflow archives. The plot index lists plots first, then groups availability
notices by run/reference in a collapsible section. Every failed reference read,
including location, member, original pathname and error, is retained in
`reference-read-report.csv`. A missing minimum-limit record does not imply a zero
minimum. It is not replaced with observed outflow; available prepared demand and
combined-minimum traces remain separately labeled.

Open diagnostic at the 16 October 2026 handoff: FLOW-MINLIM catalog records exist,
but it is not yet established whether their native values are missing or the
archive reader failed to retrieve them. See [next-session validation](RTS_IMPORT_VALIDATION.md).
Warning grouping improves reporting; it does not resolve that data-read question.
