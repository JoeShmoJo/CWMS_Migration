# RTS baseline configuration editor — review design

Open `editor-mockup.html` in a browser without RTS, Python or internet access.
It contains an example populated from the current standalone script/configuration
snapshot. Open/save JSON, edit settings and tables, preview imported CSV files,
and export a readable HTML summary. It is a design prototype: it does not apply
files, change the watershed, compute ResSim or provide production validation.

## Proposed configuration contract

One reusable JSON file contains all baseline scripted-rule settings. Its header
has a format identifier, schema version, name and description. `rules` has stable
rule identifiers, descriptive labels, scalar/per-reservoir settings, and tables.
Dates, forecast paths, members, baseline IDs and augmentation settings are absent.
The included example is a proposal, not a format accepted by existing scripts.

Each table has `mode` (`inline` or `csv`), ordered `columns` and `rows`, and an
optional `csv_path`. JSON `null` preserves a blank cell; zero remains zero.
Original CSV names and headings are retained for lossless adapter export. The
prototype keeps CSV cell values as text; the production validator must enforce
numeric, Boolean, date and reservoir requirements for each specific rule.

Inline mode uses the saved table. CSV mode uses the linked file resolved by the
production adapter. Relative links resolve from the imported RTS watershed;
absolute paths may be supported but reduce portability. The saved rows serve as
an editor preview in linked mode and are never an automatic fallback if the link
is missing. The prototype cannot read an arbitrary local path: Browse CSV loads
a file selected by the user into the preview. Applying must reread and validate
the actual linked file, independently of that preview.

The first version supports daily tables, reservoir/date event tables, parameter
matrices, scalar values and per-reservoir settings. Date-range editing,
interpolation controls and graphical daily-schedule tools are later improvements.
In particular, FIRO blanks mean no target: do not interpolate or zero-fill them
unless the rule's explicit configuration calls for it.

## Rule coverage

| Rule | Existing settings |
| --- | --- |
| Deep Drawdown | Reservoir/event CSV; buffer and glide settings in Python |
| Spring Spill | Reservoir/event CSV; buffer and glide settings in Python |
| No Draft | Reservoir/date/elevation CSV |
| Secondary Flood Draft Limit | Parameter-by-reservoir CSV |
| FIRO Space | Daily elevations CSV; mode, per-reservoir mode and tuning settings |
| Combined Min Trib | Daily minimum-flow and withdrawal CSVs; downstream refill setting |
| Diversions and Returns | Daily diversion/return CSV |
| IRRM | Activation and target elevations from alt_config; glide setting |
| Draft to Rule Curve | Activation from alt_config; lookahead and buffer settings |
| Fill LOP First | Date window, elevations and release settings in Python |
| HCR / LOP Balance | Date window, conservation elevations and release settings in Python |

The snapshot's `Con_Season.txt` contains no overrides. Its effective alternative
settings come from `_default.txt`. Alternative setup and the external state-variable
controller are runtime infrastructure; their compute order, debug flags and file
routing are retained separately, not exposed as operational rule edits.
Augmentation configuration and Salem/Albany target tables remain a separate set.
`Combined_Min_Trib.csv` is not read by the supplied MinFlowPlusWithdrawal module;
that module uses MinFlowConfig.csv plus WithdrawalConfig.csv. Preserve the older
file in the source snapshot, but do not present it as an active third input.

## Proposed apply and archive behavior

1. Open/edit/save a reusable set in the independent editor. Saving changes no
   active model files. Export Summary makes inspection possible without RTS.
2. In RTS, Apply for Baseline Compute resolves linked CSVs, validates all rule
   settings, and stages a fully resolved snapshot under the selected forecast.
3. Publish the complete staged set, disable augmentation and record that an
   unaugmented compute is pending. Tell the user to compute manually in RTS.
4. During compute initialization, an RTS-only adapter supplies the staged
   settings. Rules continue to obtain their data once per compute. Embedded
   rule wrappers and initialization order must be verified before deployment.
5. Accept completed results and archive the resolved settings, original linked
   file bytes, checksums and adapter/script version with the results. Existing
   baseline-result comparisons determine baseline identity: identical outputs
   retain the version; changed outputs create a new version. Configuration-only
   changes still get an action-history entry and their compute snapshot retained.

A changed configuration requires a new unaugmented compute before preparing
augmentation. Previously archived augmentation pairs remain readable with their
original baselines; loading stale releases into a changed baseline is blocked.
All augmentation-affecting baseline inputs remain in the baseline comparison.

## Isolation and implementation sequence

Keep standalone source files and config readers unchanged. Install adapted rule
modules only in the imported RTS watershed and make configuration selection depend
on the actual forecast output directory. Do not use a single watershed-wide active
configuration: two forecasts must be able to retain different settings. Rules
that initialize before Alternative_Setup need a forecast-aware resolver as well;
changing only Alternative_Setup's config pointers would not cover those cases.

The adapter can initially export existing CSV/Hjson representations from the
resolved JSON, avoiding simultaneous rewrites of every rule parser. Python-defined
operational constants require explicit per-compute overrides in RTS copies;
module-global mutation is unsuitable across forecasts/ensemble members. Retain
existing defaults and test old behavior against an unchanged imported set.

Next implementation steps: finalize field definitions and validations; implement
portable JSON/CSV resolution and snapshotting; build the independent editor;
install/test the RTS adapter; connect Apply and baseline acceptance to the menu.
The mockup deliberately disables Apply until those pieces are implemented.
