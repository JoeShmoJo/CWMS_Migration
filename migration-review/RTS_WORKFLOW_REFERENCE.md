# RTS baseline and augmentation: process and file reference

Current implementation, 16 October 2026. Start with the
[operator SOP](RTS_OPERATOR_SOP.md). This reference describes the current four-button
menu and compact-run backend, rather than the earlier experimental menu layouts.
It documents the repository implementation; an older installed script set may
behave differently. The [data I/O audit](RTS_DATA_IO.md) describes the archive change.

## Locations and terminology

Examples below use these roots; substitute the paths shown by your selected forecast.

| Symbol | Example | Purpose |
| --- | --- | --- |
| `REPO` | `C:\Projects\A_Recent_Projects\CWMS_Migration` | Maintained code and documentation |
| `WS` | `C:\CWMS\watershed\ResSimMaster` | Imported RTS watershed and shared installed scripts |
| `EP` | `WS\scripts\ExternalPython` | Installed external Python backend and maintained data inputs |
| `F` | `C:\CWMS\forecast\Ensemble_Test\ResSimMaster` | One forecast's model directory; parent of its live DSS |
| `A` | `F\augmentation-archives` | Baseline versions, schemes, results, state, history |
| `B` | `A\baseline` or `A\baseline-0002` | One immutable accepted baseline |
| `S` | `A\<configuration>-<baseline-id>-<token>` | A scheme calculated for one baseline |
| `R` | `S\results-<token>` | One accepted augmented result |
| `C` | `F\baseline-configurations\sets\<id>` | Applied baseline configuration snapshot |

The **forecast alternative** (for example ConSeason), ResSim **model alternative**
(for example Con_Season), and output **run code** (for example C0) are related but
not interchangeable names. The menu derives context from the selected RTS run.
Computed ensemble F-parts are normally `C:<six-digit-member>|<run-code>`.
Dates and timezone come from the forecast runtime window, not standalone
`CONFIG.SIM_NAME`. HEC `2400` denotes the following midnight; keep the displayed
HEC date/time convention when checking the window.

A baseline is an accepted unaugmented result, not simply a named configuration.
A reusable baseline configuration is a portable set of scripted-rule settings.
A reusable augmentation configuration is a reservoir table plus calculation
settings. A scheme is that augmentation configuration resolved into releases for
one particular baseline, window and ensemble. An archived result is the completed
simulation after loading a scheme. Saving a configuration does not compute or
accept results. “Commit” here means activating prepared releases, not committing
files to Git.

## Programs and responsibility

Repository sources are under `REPO\migration-review`; the runtime uses installed
copies under `WS`, not files from the repository checkout automatically.

| Entry point or module | Where it runs/lives | Responsibility |
| --- | --- | --- |
| `RTS_WORKFLOW_MENU.py` | `WS\scripts`, RTS Jython/Swing | Four main actions, context display, prompts, background jobs, plot opening |
| `rts_workflow.py` | `EP`, hydro39 Python | Dispatches tasks; holds per-forecast task lock; promotes extracts |
| `workflow_simple.py` | `EP` | Acceptance, configuration processing/loading sequence, run chooser state |
| `run_extraction.py` | `EP` | Runs extraction steps sequentially against a staged DSS; records completion |
| `baseline_configuration.py` | `EP`, local browser editor/backend | Imports/saves/applies baseline settings and checks initialization receipts |
| `rts_baseline_runtime.py` | `WS\scripts` | Forecast-scoped baseline overrides during rule initialization |
| Baseline rule adapters | `WS\scripts\externalRules` | Initialize configured rules; preserve ordinary timestep functions |
| `baseline_versions.py` | `EP` | Baseline registry/fingerprints, version changes, result status/deletion, history |
| `run_archive.py` | `EP` | Captures selected DSS blocks into primary compressed archives; verifies them |
| `run_data_cache.py` | `EP` | Common array reader; also builds/reuses disposable caches for legacy DSS archives |
| `prepare_rts_augmentation.py` | `EP` | Validates baseline/configuration, calculates per-member releases, writes scheme |
| `MainstemAugmentation.py` | `EP`, functions loaded by preparer | Existing augmentation calculation functions |
| `augmentation_mapping.py` | `EP` | Maps reservoir abbreviations to Combined Min Trib release requirements |
| `load_rts_augmentation.py` | `EP` | Verifies scheme/baseline identity, stages live DSS, loads releases, activates marker |
| `MainstemFlowAugSV.py` | `WS\scripts\externalSVs` | Uses forecast-scoped augmentation activation; must already be installed/bound |
| `plot_rts_runs.py` | `EP` | One/two saved-run plots, overlays, source CSVs, selection/read metadata |
| `plot_rts_augmentation.py` | `EP` | Result capture and comparison functions; older comparison CLI remains available |
| ResSim itself | Through normal RTS/ResSim compute controls | Runs the model, initializes rules, writes simulation DSS outputs |

The menu launches hydro39 using the detected Miniconda/Anaconda installation,
commonly `%LOCALAPPDATA%\miniconda3\envs\hydro39\python.exe`. Its task context
contains forecast name, forecast alternative/run name, live DSS path, lookback,
forecast start/end and timezone. An ephemeral `%TEMP%\rts-menu-*.json` supplies
this context to the backend and is removed after the menu task. The baseline
browser editor uses a separate saved context under `F\workflow-logs`.

## Initial extraction

**Trigger:** Initial Extract. **Input:** selected RTS context, installed downloader
configuration/mappings in `EP\CONFIG.py` and the downloader modules, network data
services, and any existing live inputs used to seed the staged file.

`run_extraction.py` runs these installed scripts in order:

1. `RFC_Downloader_Module.py`: downloads current NWRFC ensembles, processes flows,
   and writes forecast-mode ensemble DSS records.
2. `CWMS_Downloader_Module.py`: obtains required lookback elevations and configured
   observations/other groups from CWMS; writes DSS records.
3. `Dummy_0_and_WY_Abundant_Module.py`: writes the zero dummy and abundant-water-year inputs.
4. `OSI_Ensemble_Year.py`: creates the configured OSI member data.
5. `write_rule_curves.py`: writes configured rule-curve records from the annual CSV.
6. `write_ensemble_shared_inputs.py`: makes required shared inputs available under
   ensemble paths used by ResSim.

| Artifact | Location | Creator / use |
| --- | --- | --- |
| Live input/output DSS | `F\forecast.dss` | Extract promotion initially; then native compute and scheme loading |
| Staged/extracted DSS | `F\extraction-test-<token>\forecast.dss` | Extraction runner; retained input archive |
| Extraction context | Same folder, `context.json` | Runner; explicit dates/timezone/member conventions |
| Extraction log | Same folder, `extraction.log` | Runner; subprocess output and diagnostics |
| Successful completion record | Same folder, `extraction-complete.json` | Runner only after all steps succeed; includes DSS hash and context |
| Raw RFC download copy | `EP\raw_rfc_csv\<date>\...` | RFC downloader; one retained raw set per day, not one per forecast; downloads still occur on later invocations |
| Previous live DSS backup | `F\forecast.before-menu-extract-<token>.dss` | Promotion retains previous live file if one existed |

The menu promotes only the newly completed extraction matching this invocation's
context and verifies its hash. Partial folders remain for diagnosis but are not
substituted for a completed extract. The standalone extraction launcher
`RTS_FORECAST_EXTRACT.py` has separate plan/test behavior; its test-copy-only
messages do not describe the menu's subsequent promotion step.

The RFC downloader supplies the current issue, not arbitrary historical forecasts.
Requested windows must fit actual data availability. Historical RFC archive loading
is not part of this SOP. CWMS lookback timestamps must cover the required window;
missing required data is not filled or extrapolated. Forecast synthetic percentile
members are 3000/3001/3002 and OSI is 3003 in the current extraction conventions;
which members compute depends on the model alternative and available inputs.
Members below 3000 and at/above 3000 are kept separate in plotting. Do not infer
that every downloaded member was computed successfully.

## Baseline configuration inputs and applied files

The browser editor combines these eleven scripted rule groups into one baseline
configuration. It does not edit native operation-set selection, stack order,
DSS mappings, or arbitrary embedded model scripts.

| Editor group | External module | Main source of initial settings |
| --- | --- | --- |
| Deep Drawdown | `DeepDrawdown.py` | Config table selected through `DeepDrawdownConfigCSV` |
| Spring Spill | `SpringSpill.py` | `SpringSpillConfigCSV` |
| No Draft | `NoDraft.py` | `NoDraftConfigCSV` |
| Secondary Flood Draft Limit | `SecondaryFloodDraftLimit.py` | `secondaryDraftConfigCSV` |
| FIRO Space | `FIRO_SPACE.py` | Daily schedule through `firoSpaceConfigCSV` |
| Combined Min Trib | `MinFlowPlusWithdrawal.py` | `minFlowConfigCSV`, `withdrawalConfigCSV` |
| Diversions and Returns | `DiversionFromCSV.py` | `diversionConfigCSV`; negative values represent returns |
| IRRM | `IRRM.py` | Active/target settings and preserved module constants |
| Draft to Rule Curve | `DraftToRC.py` | Active setting and preserved module constants |
| Fill LOP First | `FillLOPfirst.py` | Existing module settings/constants |
| HCR / LOP Balance | `HCR_LOP_Balance.py` | Existing module settings/constants |

Initial CSV paths/settings are resolved from installed `scripts\alt_config` and
preserved rule implementations. Actual filenames can vary by imported alternative;
use the editor and resolved snapshot rather than assuming a particular filename.
Daily tables may be embedded or linked to CSV. Linked bytes are validated and
snapshotted when applied; a saved library set embeds the schedule values.

| Artifact | Location | Creator / effect |
| --- | --- | --- |
| Reusable baseline library version | `WS\scripts\baseline-configuration-library\<id>.json` | Editor Save Configuration; each save gets a new ID, even with the same name |
| Portable JSON/readable summary | User/browser-selected export destination | Editor export; inspection/sharing, not activation |
| Preserved imported rule source | `WS\scripts\_rts_baseline_originals\externalRules\*.py` | Baseline adapter installer; source for applied script snapshots |
| Applied configuration | `C\configuration.json` | Apply; user settings for this forecast |
| Resolved configuration | `C\resolved.json` | Apply; generated table references and provenance hashes |
| Generated rule tables | `C\tables\*.csv` | Apply; actual tables used by forecast overrides |
| Linked source snapshots | `C\linked-sources\...` | Apply; linked input bytes retained |
| Applied script snapshots | `C\scripts\...` | Apply; preserved external rules and runtime source |
| Applied manifest | `C\manifest.json` | Apply; configuration ID/name/context and resolved hash |
| Active baseline pointer | `F\rts-baseline-config-active.json` | Apply; selects forecast-scoped configuration |
| Initialization receipts | `C\initialization-receipts\*.json` | Runtime during compute; identify member/module/configuration loaded |
| Accepted configuration provenance | `F\baseline-configurations\accepted-computes\<id>\...` | Acceptance; copied configuration/script/table provenance plus `acceptance.json` |

Unused IRRM and Deep Drawdown reservoirs have inactive null configuration slots.
No native rule binding is added. Complete required fields before enabling; the
backend excludes incomplete inactive Deep Drawdown rows from runtime CSVs and
skips disabled IRRM targets. Existing values and older snapshots are preserved.

Save does not apply. Apply disables augmentation and records a pending unaugmented
compute; settings take effect at the next initialization, not halfway through a
running simulation. Acceptance checks initialization receipts for the configured
members, but receipts do not prove successful simulation completion. Applying
creates new forecast-scoped files; it does not overwrite the standalone source
CSV configurations. Shared reusable libraries live under `WS`, so preserve them
across watershed reimports. Directly editing source CSVs is outside this editor's
isolation behavior.

## Compute, acceptance and baseline identity

Live simulation outputs are written by ResSim into its configured DSS, normally
`F\forecast.dss`. Compute logs are native application artifacts, not produced by
the workflow's Python tasks. Native ensemble-through-ResSim examples write
`F\rss\C0.log`, worker `C0*.log`/`.log.tmp` and `C0.rssrun`; CWMS-orchestrated ensemble
examples can write `F\EnsembleRuns\<member>\C0.log`. Locations depend on the compute
path. The RTS-launched ResSim server log has appeared at
`%LOCALAPPDATA%\Temp\1\logs\ResSimServer.log`; check its timestamp before relying on
that session-specific example. A new log ending in successful completion matters
more than an old DSS record's presence or a progress bar showing 100%.

**Trigger:** Yes in the completion question opened by Augmentation Configuration,
Plot Results, or Process and Load Releases. With augmentation inactive, acceptance
saves/compares an unaugmented baseline. With augmentation active, it captures a
result under that scheme. A loaded scheme is not a completed result.

| Artifact | Location | Creator / role |
| --- | --- | --- |
| Baseline registry | `A\baseline-versions.json` | `baseline_versions.py`; current ID and all versions, hashes, contexts, fingerprints |
| First baseline | `A\baseline\...` | Acceptance (or legacy preparation path); normally baseline-0001 |
| Later baseline | `A\baseline-0002\...`, etc. | Acceptance only when compared outputs differ |
| Baseline manifest | `B\manifest.json` | Baseline save; ID, run code, forecast root, archive hash |
| Baseline context | `A\baseline-context.json` | Baseline save/link; forecast context |
| Edit-session metadata | `A\baseline-edit-session.json` | Acceptance/reset/legacy load coordination; not a copy of operation sets |

Baseline equality compares **computed reservoir pool elevation and outflow only**,
for the run code and archived members: timestamps, values, units and type, with
no numerical tolerance. It ignores DSS layout/block naming. It does not compare
operation-set files, configuration names, river flows, water-year inputs or every
other variable. Missing previously archived pool series causes rejection rather
than silently accepting an incomplete baseline.

Changed compared results create a new immutable baseline ID; old augmented
results retain their original data and pairing, labelled Previous baseline.
Identical compared results keep the existing baseline and its archive. A newly
applied configuration can therefore be accepted with separate provenance while
the baseline ID stays unchanged. Configuration/script changes alone do not
necessarily create a new result baseline.

## Compact versus legacy result storage

| Artifact | New compact archive | Legacy archive |
| --- | --- | --- |
| Primary time series | `B\series.npz` or `R\series.npz` | Archived `forecast.dss` |
| Primary data manifest | `run-archive.json` in same folder | Baseline/result metadata points at DSS checksum |
| Optional derived cache | Not required | `run-data-cache-C0\series.npz` and `manifest.json` |
| Rebuild after array damage | No: primary data must be recovered from a backup | Disposable cache can rebuild from intact archived DSS |

New acceptance captures selected full time series, not peak summaries. It scans
the catalog and reads selected physical date blocks once, retaining pool outputs,
plot control-point flows, reservoir storage/inflows needed by augmentation,
Combined Min Trib requirements and water-year values for the run. It excludes
unrelated runs, powerhouse/tailwater/diversion/return outputs, unrelated reaches,
and DSS rule-curve searches. The scope includes all cataloged members for the
accepted run code, not a certified list of only the latest successful members.

`series.npz` is compressed NumPy data loaded without pickle. `run-archive.json`
records logical DSS paths, timestamps' array references, units/types/timezones,
array checksum, content hash and source-file signature. Existing APIs may still
refer internally to `B\forecast.dss` as a logical source locator; a new compact
archive does not physically contain that DSS file. Plots and preparation use the
array reader instead. Corrupt primary data fails verification; current live
outputs are never silently substituted for archived results.

Capture checks live file size and timestamps around the read. This detects normal
concurrent writes, not adversarial changes with preserved metadata. Finish compute
before acceptance. Unchanged legacy baselines may remain DSS-backed; existing
archives are neither converted nor deleted automatically.

## Augmentation inputs, preparation, activation and results

The augmentation editor starts from
`WS\scripts\externalSVs\MinFlowSalemAlbanyConfig.csv`. This reservoir table includes
aliases, participation, conservation elevations/storage, summer buffer elevations,
maximum release and travel time. The current calculation uses participation,
storage floors, release limits and travel times; retained elevation/buffer fields
do not imply additional implemented logic. Current participation restrictions
require Lookout Point and combine Hills Creek with it, with identical Salem/Albany
support flags.

Additional maintained inputs are
`WS\scripts\externalSVs\MinFlowSalem_2008BiOp.csv` and
`MinFlowAlbany_2008BiOp.csv`, plus `EP\median_remaining_by_day.pkl` and
`EP\MainstemAugmentation.py`. The target tables provide mainstem requirements;
the pickle provides median remaining-inflow data. Do not replace the latter with
an untrusted pickle. Their exact copies/hashes are saved with each scheme.

Baseline arrays supply storage, inflow/outflow, Combined Min Trib release
requirements, Salem/Albany flows, and water-year values. The Green Peter minimum
uses the saved Green Peter Combined Min Trib output, which already accounts for
the downstream Foster target/mass balance, rather than substituting Foster's
minimum directly.

**Short forecast days** is the calculation's short-horizon setting (default 10),
not the total forecast length or ensemble count. The **season year** identifies
the covered April–October augmentation season, not the historical member year.
The menu offers seasons based on saved output coverage and caps the end at the
earlier of October 31 and common coverage. Preparation also requires the travel-
time lead-in and complete required daily inputs. It does not invent missing dates.

Water-year modes differ: `storage-maf` expects physical MAF-labelled values;
`fixed-abundant` explicitly treats the input as the constant category 4, even if
ResSim exports a storage unit label. The latter rejects 0, other values and missing
samples. It must not silently reinterpret or replace an arbitrary input with 4.

| Artifact | Location | Creator / use |
| --- | --- | --- |
| Reusable augmentation JSON | Default `WS\scripts\rts-augmentation-configurations\<chosen-name>.json`; chooser can select elsewhere | Save Configuration; reservoir table/calculation settings, no forecast dates/members/baseline identity |
| Generated scheme directory | `S` | `workflow_simple.process_configuration`; name combines config slug, baseline ID and unique token |
| Resolved reservoir CSV | `S\MinFlowSalemAlbanyConfig.csv` | Preparer, from editor's temporary CSV snapshot |
| Target/calculator/input snapshots | `S\MinFlowSalem_2008BiOp.csv`, `MinFlowAlbany_2008BiOp.csv`, `median_remaining_by_day.pkl`, `MainstemAugmentation.py` | Preparer copies maintained inputs |
| Reusable settings used for this scheme | `S\configuration.json` | Process Configuration after preparation |
| Per-member calculation table | `S\member-<member>.csv` | Preparer; baseline-derived calculations, targets, prepared releases |
| Prepared release DSS | `S\augmentation.dss` | Preparer; daily `FLOW-MIN-EXTERNALFLOWAUG` records for supporting reservoirs and mainstem locations |
| Scheme manifest | `S\manifest.json` | Preparer/process step; baseline ID/hash, forecast root, run code, members, season, settings, paths and input/output hashes |
| Failed preparation marker | `S\FAILED.txt` | Preparer on failure; do not load partial scheme |
| Active scheme pointer | `F\rts-augmentation-active.json` | Loader after successful staging; tells RTS augmentation runtime which scheme is active |
| Previous activation records | `F\rts-augmentation-disabled-<token>.json` | Disable/apply/load operations retain prior marker metadata |
| Previous live DSS backup | `F\forecast.before-augmentation-<token>.dss` | Loader retains old live DSS by rename before promoting staged file |
| Accepted augmented result | `R\series.npz`, `run-archive.json`, `capture.json` | Capture after operator confirms successful augmented compute |

Processing validates the saved baseline and snapshots configuration, writes only
prepared releases into `augmentation.dss`, then verifies and loads manifest-listed
records into a staged live DSS. Whole-file staging is retained to avoid partially
changing the live input file. The old live DSS is retained by rename; a caught
promotion failure restores it. An interruption between renames may require manual
restoration from that backup. Loading writes the active marker; it never computes.

A scheme manifest's `prepared-not-computed` status describes preparation and is
not rewritten to certify model success. `capture.json` records the separately
accepted result, time, archive identity and baseline pairing. Operator-confirmed
compute status is not independent log verification. Reaccepting unchanged compact
result content under the same scheme/baseline reuses the saved result. An earlier
baseline's scheme cannot be activated as a current-baseline scheme; its archived
results remain available for plotting.

## Plotting and archive management

**Trigger:** Plot Results, optionally accepting current completed results, then
Plot Selected. One run or any two distinct archived runs may be selected. Matching
historical members are paired for comparisons; synthetic traces stay separate.
Matching baseline IDs make a baseline/augmentation comparison interpretable.
Cross-baseline comparisons are explicitly labelled as containing baseline changes.

| Artifact | Location | Creator / use |
| --- | --- | --- |
| Plot archive | `F\output_plots\saved-runs-<token>\` | `plot_rts_runs.py`; a new folder per invocation |
| Browser entry | `index.html` | Plotter; links to offline plot pages and baseline-status notes |
| Plot pages/library | `plot-<n>.html`, `plotly.min.js` | Plotter; offline interactive figures |
| Actual plotted data | `plot-<n>-run-<n>.csv` | Plotter; source series for each figure |
| Paired differences | `plot-<n>-paired-difference.csv` | Plotter for two-run comparisons |
| Requirements used | `plot-<n>-run-<n>-requirements.csv` | Plotter; prepared scheme targets/minimum-release overlays |
| Rule-curve provenance | `CON_SEASON_RULE_CURVES.csv`, `plot-<n>-rule-curve.csv` | Plotter copies `EP\CON_SEASON_RULE_CURVES.csv` and expands annual schedule over plot dates |
| Plot selection/provenance | `selection.json` | Plotter; selected archive descriptors and rule-curve checksum |
| Read audit | `read-report.csv` | Plotter; records read/missing/error and rule-curve notes |

Plotting uses saved arrays or legacy caches, not current live simulation results.
Baseline-only plots have no augmentation overlay. Requirement traces can vary
by ensemble member; identical traces are displayed once, differing requirements
have a range and individually selectable traces. The annual CSV supplies available
rule curves without searching ResSim/CWMS DSS records for longer coverage. Dexter
and Big Cliff have no curve from this CSV.

Older comparison CLI plots can also live under `R\plots-<token>`; the current
chooser creates `output_plots\saved-runs-*`. Earlier plot files remain. Their
labels reflect the status when generated; the chooser and new plots use current
baseline status.

Delete Selected Augmented Result confirms deletion of that result and plots that
include it. It retains its scheme's configuration/prepared releases, baselines,
other results, and action history. Old/failed extraction folders and full live-
DSS recovery backups are not automatically purged. Baselines have no delete
button. Do not remove primary compact arrays under the assumption they are caches.

## State, logs and maintenance boundaries

| Artifact | Location | Creator / use |
| --- | --- | --- |
| Workflow task logs | `F\workflow-logs\<action>-<uuid>.log` | Menu background task; streamed backend stdout/stderr |
| Baseline editor context/log | Same folder, `baseline-editor-*.json` / `.log` | Baseline Configuration launch; context and editor process output |
| Per-forecast task lock | `F\.rts-workflow-task.json` | `rts_workflow.py`; PID/action, removed after normal task exit |
| Pending compute | `A\workflow-pending.json` | Extract/apply/process/reset paths; baseline or augmentation awaiting compute/acceptance |
| Menu display state | `A\workflow-state.json` | Backend; context, baseline ID, run list, optional configuration/coverage |
| Result index | `A\archive-index.json` | Registry/index functions; current/previous baseline labels |
| Action trail | `A\action-history.jsonl` | Append-only workflow events; configuration apply, acceptance, loading, plotting, deletion |

A workflow task lock prevents overlapping backend menu tasks; it does not stop
someone starting a native compute independently. Never delete a lock until its
recorded process has stopped and the partial task has been inspected.

The main menu currently has four actions, not Reset Baseline. Older CLI/backend
reset/load commands remain for compatibility and are not required for the normal
configuration-driven SOP. No archived operation-set file is restored by applying
a baseline configuration. The imported alternative and rule bindings still need
to be correct.

For this portable watershed use the embedded
`WS\scripts\workflow-kit\Install-StandaloneConfiguration.py --mode rts` as
explained in [package/import instructions](WORKFLOW_PACKAGE.md). It installs the
required workflow helpers and converts recognized standalone adapters in the
imported copy. Script backups are printed under that watershed's
`standalone-configuration-backups`; preserve the inventory for rollback.
Older separate repository PowerShell installers remain historical maintenance
entry points; they are not the recommended conversion procedure for this package.
A Git pull alone does not update installed watershed scripts. No repository is
needed for the embedded installer. Application JAR modification is not required;
use the original HEC application. No experimental compiler patch is installed by
the package or this SOP.

## Known limitations and troubleshooting

| Symptom or situation | Meaning / action |
| --- | --- |
| Fixed-abundant error | Archived water-year values are not uniformly 4; inspect model mapping and saved values. Zero dummy is not ALL_ABUNDANT. |
| Water-year/input-only edit but unchanged pool outputs | Existing baseline identity/archive may be retained. Current equality does not compare every preparation input. Do not assume an input-only change was captured; a fresh forecast is the clean workaround pending a dedicated fix. Do not force a result change by altering unrelated operating settings. |
| Process disabled / no season | Baseline lacks April-season coverage; save configuration if useful, but use a suitably covered forecast for augmentation. |
| Missing daily input / unit error | Required baseline or mapped data are incomplete/inconsistent. Do not zero-fill or extrapolate to bypass validation. |
| Applied configuration missing receipts | Settings were not confirmed initialized for all selected members; check adapter installation/session and recompute. |
| Changed forecast context | Refresh the menu for a selection change; use a new forecast for new dates/extracted data after baseline acceptance. |
| DSS lock / replacement failure | Finish compute, close DSS views and release the forecast if needed; inspect the retained backup/candidate and log before retrying. |
| Archive checksum error | Primary compact data require recovery, not regeneration from live DSS. Legacy disposable cache alone may rebuild from its intact source DSS. |
| Error or only partial compute | Do not answer Yes to archive success. Native logs and exact member/window coverage must be checked by the operator. |

The separate PostProcess_CSV cleanup script is not the workflow archive producer.
Its code is the model's existing cleanup script, rather than one of the menu's
ExternalPython tasks. Outputs are placed beside the model's configured DSS output:

| PostProcess output | Creator / contents | Workflow consumer |
| --- | --- | --- |
| `PeakExtract_<alternative>.csv` | Ensemble cleanup branch; appended member IDs, timestamps and peak flows/elevations | Not used as full-series baseline or augmentation input |
| `<alternative>.csv.gz` | Non-ensemble cleanup branch; selected full time series | Not automatically imported by this RTS archive reader |

This workflow needs full daily member series for augmentation
and plots, so peak CSVs cannot replace its compact archives. Direct per-member
memory export and reduced native DSS output remain separate future work.

Archive directories preserve results/configuration provenance, not an entire
executable, environment, all native operation sets or a fully portable watershed.
For a study handoff, retain the needed forecast/inputs/model, applied settings,
schemes with their referenced baselines, result and plot archives, plus installed
code/environment information. Reusable configuration libraries and raw RFC copies
live under the shared watershed rather than under each forecast; include them
separately when needed. Do not claim a result can be recomputed from `series.npz`
and a configuration JSON alone.
