# Standalone and shared workflow: technical and data reference

Version: 16 October 2026. This documents the packaged implementation and the
reviewed legacy scripts. Actual installed code can differ; use the package's
installation inventory and printed job paths to resolve differences. The kit does
not automatically inspect or certify embedded native scripts/mappings.

## Roots, names and target selection

| Symbol | Location / meaning |
| --- | --- |
| W | Standalone watershed root; last used `C:\Projects\FIRO\watershed\NWP_Willamette_Master_2026_10_05_DamagesPrevented` |
| EP | `W\scripts\ExternalPython` |
| K | `W\scripts\workflow-kit`; embedded source, installers and documentation |
| S | `W\rss\<simulation-folder>`; simulation native files and simulation.dss |
| P | `S\baseline-configurations\sets\<configuration-id>` |
| RTS WS | A separate imported watershed, commonly `C:\CWMS\watershed\ResSimMaster` |
| F | Selected RTS forecast model directory; parent of forecast.dss |

Simulation, native alternative, trial, historical ensemble member and RTS forecast
alternative/run code are different identifiers. In standalone, the browser menu
requires a simulation folder and alternative name explicitly. It does not detect
the active GUI selection. The command-line editor requires --simulation and
--alternative as well. Existing external jobs use CONFIG.py; the baseline selectors
do not update it. A simulation with spaces is normalized to underscores by the
backend. Output DSS is used to locate the active pointer at compute initialization.
The runtime also checks the native alternative name before applying overrides.

## Execution layers and entry points

| Component | Runtime / producer-consumer role |
| --- | --- |
| `scripts/STANDALONE_WORKFLOW_MENU.py` | ResSim Jython/Swing; chooses target, starts external jobs, displays log path |
| `EP/standalone_configuration.py` | External Python; resolves standalone target and starts shared editor |
| `EP/baseline_configuration.py` | External Python HTTP/browser editor; imports, validates, saves and applies settings |
| `EP/baseline-editor.html` | Editor UI served locally; keep backend and UI versions together |
| `scripts/standalone_baseline_runtime.py` | Jython initialization adapter; resolves settings and writes receipts |
| `scripts/externalRules/*.py` | Eleven adapted rule modules; original timestep functions retained |
| `scripts/externalSVs/Alternative_Setup.py` | Loads legacy config plus scoped overrides |
| `scripts/NWDJyLib`, ExternalModules and other existing libraries | Existing model support; retain with watershed |
| `K/Install-StandaloneConfiguration.py` | External Python script installer; --mode standalone or rts |
| `K/Package-Workflow.py` | Embeds kit and records local inventory; defaults to standalone installation |
| ResSim/native model scripts | Compute, output DSS, embedded initialization/cleanup and native bindings |

The external Python interpreter is normally
`%LOCALAPPDATA%\miniconda3\envs\hydro39\python.exe`. Jython inside ResSim is a
separate interpreter; CPython packages are not loaded into the Java application.
Launching PowerShell → Python is simply the command chain used for maintenance;
menu jobs use Java ProcessBuilder → Python. A local HTTP server provides the
browser editor; close the old editor before opening a different target.

## Inputs and configuration precedence

| Input | Location | Created/maintained by | Used by / effect |
| --- | --- | --- | --- |
| Native simulation/alternative/trials | S and native watershed model files | ResSim editor/operator | Compute dates, operation sets, rule bindings and DSS mappings |
| External job settings | EP/CONFIG.py | Operator | Extraction/augmentation/plot target and trial selection |
| Default legacy settings | scripts/alt_config/_default.txt | Existing model/operator | Base scripted settings |
| Alternative legacy settings | scripts/alt_config/<alternative>.txt | Existing model/operator | Override defaults; @alias can refer to another preset |
| Rule CSV schedules | Usually scripts/externalRules/*.csv | Existing model/operator | Initial imported settings; actual paths come from alt_config |
| Mainstem augmentation reservoir settings | scripts/externalSVs/MinFlowSalemAlbanyConfig.csv | Operator/model | Participation, aliases, storage floors, travel time, limits |
| Mainstem flow target tables | scripts/externalSVs/MinFlowSalem_2008BiOp.csv and MinFlowAlbany_2008BiOp.csv | Existing model/operator | Water-year/seasonal target flows |
| Remaining-inflow statistics | EP/median_remaining_by_day.pkl | Maintained study input | Augmentation calculation; retain trusted version |
| Rule-curve plotting schedule | EP/CON_SEASON_RULE_CURVES.csv in reviewed scripts | Existing model/operator | Plot curves; not proof native DSS rule curves have adequate coverage |
| Current RFC forecasts | Network; mappings in downloader | RFC service/download script | Ensemble hydrologic inputs |
| CWMS observations/lookback | Network; mappings in downloader | CWMS service/download script | Initial reservoir elevations and configured observations |

Legacy alternative defaults are read first, then the alternative's settings. The
editor imports those and the preserved rule constants/tables into a reusable set.
Once applied, scoped snapshot overrides are used for the matching simulation and
alternative; other alternatives retain legacy behavior. Within that simulation,
all trials of the selected alternative receive the applied baseline settings.
Only one selected alternative is bound by the active pointer in a simulation;
the editor refuses opening that pointer as a different alternative.

CONFIG.py fields reviewed: SIM_NAME, ALTERNATIVE_NAME_STEP1, TRIAL,
TRIAL_SUFFIXES, H_LINE_DICT and ENSEMBLE_YEAR_TO_COPY. Additional dates, member
ranges, mappings and plot constants may remain in individual legacy scripts.
Do not assume the menu consolidates every script parameter into CONFIG.py.
Do not assume standalone download windows are the RTS forecast window: legacy
CWMS scripts use current-date-based logic unless locally adapted. Review them for
historical simulations. The existing menu does not supply historical RFC archives.

## Inactive reservoir slots

IRRM and Deep Drawdown configurations include all 13 reservoirs. Existing values
and activation flags are preserved; missing entries have false activation and
null targets/seasonal fields. They display as blanks and do not add native rules.
An off switch or missing required setting makes that reservoir's rule neutral,
even if its switch is on. The browser shows Off, Not configured, or On and the
resolved snapshot records operating_status. Complete enabled entries operate
normally. Off/incomplete Deep Drawdown rows are excluded from runtime CSVs;
IRRM masks an incomplete target inactive before interpolation. Invalid nonblank
numbers/dates still fail validation. Opening older sets expands only the editable view; Save/Apply makes a new
version without rewriting historical library/applied files. Linked CSV bytes stay
unchanged; missing editable slots appear after resolving/saving them inline.

## Baseline settings: outputs and consumers

The shared editor covers DeepDrawdown, SpringSpill, NoDraft,
SecondaryFloodDraftLimit, FIRO_SPACE, MinFlowPlusWithdrawal, DiversionFromCSV,
IRRM, DraftToRC, FillLOPfirst and HCR_LOP_Balance. Diversions can be negative
returns; the diversion/withdrawal enable settings must agree with the intended
Combined Min Trib behavior. The editor controls scripted settings, not whether
native rule objects exist or are bound in every operation set.

| Artifact | Location | Producer → consumer / retention |
| --- | --- | --- |
| Reusable versioned JSON | scripts/baseline-configuration-library/<id>.json | Save → editor Open; each save gets a new version; retain |
| Export JSON/summary | Browser-selected destination | Export → sharing/review; not activation |
| User configuration snapshot | P/configuration.json | Apply → provenance; retain with applied run |
| Resolved snapshot | P/resolved.json | Apply → runtime resolved paths/settings |
| Generated tables | P/tables/*.csv | Apply → initialization loaders; do not edit in place |
| Linked CSV bytes | P/linked-sources/ | Apply → reproducibility of linked schedules |
| Rule/runtime snapshots | P/scripts/ | Apply → scoped execution/provenance |
| Manifest | P/manifest.json | Apply → identity/context/hash validation |
| Active pointer | S/standalone-baseline-config-active.json | Apply → runtime; binds configuration and model alternative |
| Initialization receipts | P/initialization-receipts/*.json | Runtime → diagnosis of loaded module/member/settings |
| Original source implementations | scripts/_standalone_baseline_originals/externalRules/*.py | Installer → wrapper generation and snapshots |

Receipts record ensemble member when recognized, otherwise null plus output F-part
for a non-ensemble run. They prove initialization, not success or freshness of all
computed data. Settings are picked up on the next initialization; changing Apply
during compute is invalid. Source alt_config and CSVs are not rewritten by Apply.
An unsaved browser edit can be applied, but Save first if it needs to be reusable.
Standalone Apply leaves augmentation method and omitted trials unchanged.

## Standalone extraction, augmentation and plots

The menu's four extraction scripts run sequentially: CWMS_Downloader_Module.py,
RFC_Downloader_Module.py, Dummy_0_and_WY_Abundant_Module.py, OSI_Ensemble_Year.py.
This differs from the staged RTS extraction runner. Existing standalone jobs read
and write the selected simulation.dss directly. No compact RTS acceptance archive
or atomic RTS extract-promotion behavior is implied by their menu buttons.

| Output | Location in reviewed standalone scripts | Producer / consumer |
| --- | --- | --- |
| Live inputs and simulation results | S/simulation.dss | Downloaders and ResSim → compute, augmentation, plots |
| Raw current RFC CSVs | EP/raw_rfc_csv/<date>/... | RFC downloader → diagnostic/source archive; once-per-day save marker |
| Zero / water-year dummy series | S/simulation.dss | Dummy writer → mapped model inputs; verify values and paths |
| Editable OSI copied member | S/simulation.dss | OSI writer → model/OSI workflow; member convention is script-version-specific |
| Augmentation requirement series | S/simulation.dss | MainstemAugmentation.py → augmentation state variable/rules |
| Augmentation profile | EP/MainstemAugmentation.pstats | Reviewed calculator → performance diagnosis |
| Ensemble HTML plots | W/output_plots/plotly_html/<timestamp>/ | Ensemble_Plots.py → browser/operator |
| Trial comparison HTML plots | W/output_plots/plotly_html_trials/<timestamp>/ | ALT_COMPARISON_PLOTS.py → browser/operator |
| External job/editor logs | W/standalone-workflow-logs/*.log | Menu → diagnosis; Open last job log |
| Native compute logs | Usually S, application logs may differ | ResSim → per-worker/member completion diagnosis |

Reviewed augmentation code uses CONFIG.SIM_NAME and ALTERNATIVE_NAME_STEP1,
reads/writes the same simulation.dss, has a 10-day short horizon, and uses
April 1–October 31 season constants. It derives full-series inputs including
storage/flows/requirements and writes FLOW-MIN-EXTERNALFLOWAUG and diagnostic
Salem/Albany requirement/deficit variants. Inspect actual printed paths and DSS
F-parts: the exact trial/member suffix selection remains model-specific.
Recalculate after changing baseline results or augmentation parameters. The
standalone button does not create RTS scheme manifests or immutable result pairs.

Reviewed standalone plot F-parts normalize spaces to hyphens, pad short
alternative names to ten characters, then append the trial suffix. A native
output may use a different spelling/case; inspect real paths when no plots appear.
Reviewed HTML uses Plotly CDN assets, so do not assume these standalone plots work
offline. RTS saved-run plots embed/copy their offline library separately.

Native PostProcess_CSV cleanup is a different path: ensemble cleanup can append
PeakExtract_<alternative>.csv beside the output DSS; non-ensemble cleanup can
write <alternative>.csv.gz. The embedded cleanup script determines actual fields
and behavior. Peaks cannot substitute for daily ensemble series in augmentation.
The kit does not modify cleanup bindings or reduce native DSS output volume.

## Mode conversion and installed-source provenance

RTS mode installs the maintained RTS backend/extraction helpers, RTS launchers,
rts_baseline_runtime and RTS MainstemFlowAugSV. It unwraps recognized standalone
rule adapters and preserves neutral original sources before adding RTS wrappers.
Standalone mode performs the reverse adapter change and restores previously
preserved standalone helpers/state variable. Newly added RTS-only helper files
can remain dormant; use the correct launcher for the installed mode.

| Retained item | Location / significance |
| --- | --- |
| Mode marker | scripts/workflow-mode.json; last installer mode only |
| RTS original rule sources | scripts/_rts_baseline_originals/externalRules/ |
| Standalone helpers retained for return | scripts/_workflow_originals/ExternalPython/ |
| Standalone mainstem state variable retained | scripts/_workflow_originals/MainstemFlowAugSV.py |
| Script backup and inventory | W/standalone-configuration-backups/<timestamp-token>/files.json and corresponding paths |
| Previous embedded kit | scripts/workflow-kit-previous-<id>/ |
| Kit checksums | K/manifest.json |
| Actual installation/environment inventory | K/installation-inventory.json |

Backups preserve existing affected files; entries marked absent were newly
installed. Restore existing entries and remove only newly created entries to undo
an installation. Installation failure rolls back its script writes. Keep backups
until both workflows are locally validated. The first preserved standalone helper
copies are not a live synchronization mechanism: later custom helper edits need
explicit review when updating or switching modes. Do not edit kit sources and
installed sources independently without recording which is authoritative.

RTS acceptance/schemes/compact arrays are documented in RTS_WORKFLOW_REFERENCE.md.
Key distinction: reusable JSON can cross environments; result identities and
active pointers do not. Apply JSON to the new target, compute and accept anew.

## Preservation and recovery

Retain the full model, embedded scripts, original-source folders, CSVs, saved
libraries, needed simulation DSS files, forecast inputs, applied snapshots and
RTS archives. Keep native model alternative/operation bindings and application
version information. Compact primary series.npz files are study data, not caches.
Do not delete the only primary arrays or source data when cleaning up.

The inventory records the packaging interpreter and installed distribution
versions without exporting credentials. It is a dependency record, not a Conda
lockfile or environment installer. DLL/native DSS compatibility and CWMS access
must be validated separately. Credentials and machine trust settings are outside
the watershed. Use approved storage/access procedures for those.

A clean restart test uses preserved inputs and a small serial case, known saved
settings, current log completion and verified member/date coverage. Compare actual
reservoir outflows and Salem flows (and elevations as relevant) against a preserved
reference. Exact matches support that case; they do not prove every future member,
time window or native script path behaves identically.
