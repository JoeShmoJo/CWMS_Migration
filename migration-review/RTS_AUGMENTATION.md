# RTS two-step augmentation

The standalone `ExternalPython/MainstemAugmentation.py` is unchanged. The RTS
preparer loads only its function definitions, avoiding its top-level standalone
compute, and supplies RTS records and configuration explicitly.

## Prepare

Finish the baseline compute and close the forecast and DSSVue before taking a
snapshot. Run `prepare_rts_augmentation.py` with `--forecast-root`, a unique
`--scheme` name, `--members`, `--run-code`, `--season-year`, and an explicit
`--season-end` ISO date. The first preparation preserves a whole DSS baseline
under `augmentation-archives/baseline`; later schemes reuse that baseline, never
the latest live augmented outputs. Do not edit the archived baseline.

Each scheme contains configuration snapshots, a source calculation snapshot,
CSV calculation data for every member, targets and releases in
`augmentation.dss`, and a checksummed `manifest.json`. Failures leave a marked
partial scheme without a loadable manifest. Use a new name on retry.

For ForecastTest_1055 use 2027-09-30 as the explicit test season end: that is the
coverage validated in the current baseline. This is a partial-season test,
not the full April-October operation. The preparer does not invent October
inflows. Travel times shift releases earlier than the target dates, including
the last declared target date. Releases are zero outside that shifted window.

The RTS calculation subtracts the minimum storage floor once, combines Hills
Creek with Lookout Point, and uses saved Combined Min Trib release requirements.
Green Peter's rule value already converts the Foster target into a Green Peter
release. Release caps are enforced. The legacy signed-deficit and May 16
water-year classification behavior are retained; they are not a new optimization
method. SummerBufferElev is used by the legacy one-step method, not added as a
new constraint to this two-step external calculation.

The current forecast uses the extraction's ALL_ABUNDANT constant 4 input.
Its WaterYearTypeVariable output is labeled AC-FT despite being that constant.
Use `--wy-type-mode fixed-abundant` for this explicit setup. Every loaded value
must equal 4; it is not divided by a million. The legacy target selection treats
4 as abundant and selects the 1.48 target-table row. The default storage-maf
mode continues to require MAF units and rejects the misleading AC-FT label.

## Load and compute

After reviewing preparation, run `load_rts_augmentation.py --forecast-root ...
--scheme ...`. Close the forecast and DSSVue first. This backs up the live DSS,
writes the complete scheme records into a candidate copy, and replaces the
live DSS only after candidate writes finish. Activation is explicit through
`rts-augmentation-active.json` beside the forecast DSS. No compute is launched.

Reopen the forecast and compute manually. The installed MainstemFlowAugSV
module uses that marker only for RTS. Without a marker it returns zero for the
augmentation rule, irrespective of retained scheme records. With a marker it
requires matching run/member and supporting reservoirs and reads the exact
current RTS F-part without standalone trial substitution. Standalone retains
its existing configured method, omitted trials, and baseline-trial lookup.
The activated scheme supplies its archived reservoir augmentation configuration
and mainstem target tables, allowing an earlier scheme to be reloaded after
editing the working augmentation CSVs without rewriting those working files.

The installer backs up and updates the imported watershed's external SV module,
not the maintained standalone watershed. Restart RTS after installing this
module so the old loaded module/cache does not remain in use. The existing
rule/state-variable pass-through scripts need no edits.

Use `--reset` instead of `--scheme` on the loader to disable augmentation for
the next compute. It does not erase any DSS records or archives. Avoid
re-extracting or editing the model, dates, downloaded inputs, ensemble range,
or operation set between comparison schemes. If those change, create a new
forecast/baseline; do not reuse the old baseline merely because the directory
name still matches. Hashes verify archived files, not equivalence of an edited
RTS model.

After the augmented compute finishes, close the forecast and DSSVue and run
`plot_rts_augmentation.py --forecast-root ... --scheme ... --members 1981-1991`.
Synthetic members default to 3000-3002 and are excluded from historical bands.
The command checks that the selected scheme is active, preserves a whole live
DSS snapshot under a unique `results-*` directory inside the scheme archive,
then creates offline comparison plots, CSV differences, and a read report.
Each invocation captures a new snapshot; it does not overwrite prior results.

Historical baseline/augmented bands compare paired valid member values. Click
a historical member in the legend to show both individual traces. Mainstem
flow plots show prepared targets; participating reservoir outflow plots expose
the prepared minimum-release traces by member. Identical requirements are shown
once, differing requirements as exact individual traces initially hidden in
the legend. A median is not labeled as an applied requirement.

Captured records do not certify compute success: old output can survive a
failed recompute. Capture metadata explicitly records unverified compute
status. Check the RTS status/logs and read report before using the comparison
as evidence of successful augmented results. The preparation manifest remains
prepared-not-computed because plotting cannot certify that status.

## Current verification

Cloud unit tests exercise the actual legacy calculation functions, single
storage-floor subtraction, travel-time boundaries, missing-input rejection,
archive checksum validation, and baseline initializer behavior. Actual HEC-DSS
writes and the active RTS compute path require the user's Windows validation.
