# Optional diversion postprocessing — separate experimental outputs

This tool reads a completed standalone `simulation.dss` or RTS `forecast.dss` and
the generic-year diversion/return CSV. It writes adjusted junction flows and an
adjustment audit into a new directory. It never calls DSS record-writing methods,
changes the network/rule bindings, loads releases or modifies accepted archives.
It is not automatically called by either workflow menu or native cleanup.

## What it calculates

For each member, timestamp and selected junction:

`adjusted = original + already-included scheduled net demand − desired net demand`

Positive CSV values are withdrawals; negative values are returns. Only mapped
upstream elements contribute. Conditions can reduce positive withdrawals when
that member's original reservoir elevation is above/below a threshold. They do
not change original elevations, reservoir releases or minimum-flow requirements.

The network export provided on 16 October contains 32 diversion/return elements,
88 junctions, 74 reaches and 13 reservoirs. All 32 names match DiversionConfig_ALT.csv.
The tool follows exported downstream links, includes the attachment junction,
and **stops at the next reservoir**. Example: Diversion 3 at Detroit_OUT stops at
Big Cliff; its deficit is not subtracted at Salem with Big Cliff outflow held fixed.
Diversion 1 up affects Salem and Wilsonville; Diversion 1 down does not affect Salem.

This first method is explicitly **instantaneous bookkeeping**. It does not use
the export's Muskingum parameters or model travel times. Effects are applied at the
same timestamp to downstream junctions until a reservoir barrier. No routing or
storage-response equivalence is claimed. Evaluate suitability before using it for
rapidly varying or subdaily comparisons. Native regulation and augmentation do
not respond to postprocessed flows. Native DSS/RTS plots keep showing original
results; use the separate adjusted CSVs for this analysis.

## Configure and run

1. Use an existing test simulation; preserve its reference results. If testing
   a no-diversion compute, remove/disable the native diversion rules in the TEST
   alternative and verify the native default operations actually take zero water.
   Removing a scripted rule does not guarantee another operation takes nothing.
   If the coupled demand switch is installed, set `scripts/diversion-demands.json`
   diversion_demands_enabled to false so Combined Min Trib does not add withdrawal
   releases. Without that switch, review the withdrawal CSV/native setup separately.
   This tool does not alter those settings or prove they were disabled.
2. Compute and confirm successful completion/coverage before reading DSS.
3. Copy config.example.json to your own named JSON. Set exact output run suffix
   (for example CON_SEASON0 or C0), explicit members, ISO start/end timestamps,
   timestep_hours and junction names. The example dates/member are illustrative.
4. Set source_diversions **none** only when the compute had no diversions/returns.
   Use **scheduled** only when original output already includes exactly this CSV
   schedule. Scheduled mode changes the existing net demand rather than deducting
   it twice. If actual diversions were capped/limited or schedules differed, neither
   assumption is established: do not use the scheduled mode as an exact correction.
5. Set schedule_day **period_start** for CSV dates based on interval start, or
   **timestamp** for dates based on the DSS timestamp. This is explicit because
   HEC end-of-period 2400 timestamps can represent the next civil midnight. Verify
   against a known daily/subdaily scripted result before a long study. Feb 29 uses
   Feb 28's generic-year entry, matching the schedule's non-leap-year convention.
6. Enable/edit the example condition only after selecting real thresholds and
   withdrawal elements. withdrawal_multiplier=0.5 keeps half the withdrawal;
   zero cancels it. Multiple conditions choose the strongest reduction. Conditions
   cannot target negative return schedules; returns stay fixed unless a future
   independently specified return policy is added. Reducing a withdrawal does not
   implicitly reduce its return.
7. Run the command below. Enter the completed source DSS, schedule CSV and saved
   condition JSON. Source files are read; outputs must be a new directory.

PowerShell, one line (run from any folder; prompts use the standalone root below):

```powershell
$ws = "C:\Projects\FIRO\watershed\NWP_Willamette_Master_2026_10_05_DamagesPrevented"; $src = Read-Host "Completed simulation.dss or forecast.dss full path"; $csv = Read-Host "Diversion CSV full path"; $cfg = Read-Host "Postprocess configuration JSON full path"; & "$env:LOCALAPPDATA\miniconda3\envs\hydro39\python.exe" (Join-Path $ws "scripts\workflow-kit\optional-diversion-postprocess\postprocess.py") --source $src --network (Join-Path $ws "scripts\workflow-kit\optional-diversion-postprocess\network.json") --schedule $csv --config $cfg --output (Join-Path $ws ("diversion-postprocess-results\" + [guid]::NewGuid().ToString("N")))
```

For RTS, change $ws to the imported watershed root. Supply forecast.dss as source.
The network snapshot is from the provided export, not the current live network;
replace it with a new export and review names/connectivity after native changes.
The existing hydro39 environment supplies numpy, pandas and pydsstools.

## Outputs, validation and limitations

| File | Contents |
| --- | --- |
| member-<member>-<junction>.csv.gz | Timestamp, raw CFS, source scheduled net, effective net and adjusted CFS |
| diversion-audit.csv.gz | Every member/time/element: scheduled/effective CFS, included CFS and signed adjustment |
| manifest.json | Complete/incomplete status, condition settings, input hashes, source signature, downstream mapping, reservoir barriers, assumptions and output hashes |

Only period-average CFS junction FLOW and feet reservoir ELEV for the exact selected
members/run are read. The tool checks full uniform timestamp coverage and explicit
endpoints; missing condition elevations fail. It rejects negative adjusted flow
instead of silently clipping. Catalog presence alone is not accepted as coverage.
On error, partial files and an incomplete manifest remain for diagnosis; do not use
them as finished results. Original and adjusted series are always separate.

First validate with no conditions against a simple known no-diversion run, then
one withdrawal reduction over a few days. Compare the same schedules/clock
convention at a local junction before interpreting downstream differences.
This tool does not establish whether diversions caused a parallel-compute failure
or guarantee a speed improvement; benchmark a small serial/parallel test separately.

## Additional reservoir configuration

Baseline configurations include all 13 reservoirs for IRRM and Deep Drawdown.
Existing operating entries are preserved. Additional entries are inactive with
null/blank targets and seasonal fields. Off or incomplete entries impose no additional release requirement, even with
the switch on. The browser shows Off, Not configured or On; malformed nonblank
values still fail validation. Complete enabled entries operate normally. The browser displays numeric nulls as blank number fields.
Off/incomplete Deep Drawdown rows are omitted from runtime CSVs so legacy
readers never try to parse blank numbers. Disabled IRRM skips unused targets.
Opening an older saved set adds missing slots in the editor without rewriting the
old library file or active snapshot. Save/Apply creates a new version as usual.

This adds configuration readiness, not native rule bindings. In the test native
alternative, attach the appropriate rule through ResSim's editor at the intended
operation set and stack position, then apply and validate the settings. The kit's
IRRM_ScriptedRule.txt and DeepDrawdown_ScriptedRule.txt provide import-only dispatch
scripts if needed. They rely on the model's existing module path and initialization
setup and intentionally do not reload shared modules during compute.
Configuration entries cannot detect or automatically add native reservoir rules.
Removing native DiversionFromCSV rule bindings does not create a dependency for
other rule initialization or receipts: acceptance requires member receipts, not
one DiversionFromCSV receipt at each node. Keep the module files for packaging;
removing native bindings and deleting external source files are different changes.
