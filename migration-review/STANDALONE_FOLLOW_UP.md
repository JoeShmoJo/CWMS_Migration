# Standalone ResSim follow-up

This log tracks changes to consider in the maintained standalone watershed after
RTS testing. None of the pending items below has been applied to the standalone
model. Keep one maintained operation set; do not duplicate it to distinguish
augmentation schemes.

## Confirmed calculation issue

- **April 1 usable storage is reduced twice.** In
  `ExternalPython/MainstemAugmentation.py`, `calculate_storage_on_date()` already
  subtracts `MinConStor`. The subsequent `April01_conStorage` loop subtracts it
  again. Subtract once in the future standalone correction and test the result.
  Lookout Point combines Hills Creek storage and its storage floor: usable
  storage = LOP storage + HCR storage - 118800 - 155400 acre-feet for the supplied
  configuration. Both floors must be counted once, not twice.

## Changes to evaluate after RTS validation

- **Water-year-type metadata:** the current RTS ALL_ABUNDANT input is constant
  4, but WaterYearTypeVariable exports it under STOR-MAF with AC-FT units.
  The RTS preparer requires explicit fixed-abundant mode and verifies all values
  are 4. Review the standalone state-variable units and distinguish categorical
  codes from physical storage; never divide this code by a million. The existing
  legacy target selection uses the abundant 1.48 table row for values above 1.2.

- **Local minimum-release inputs:** the imported model saves `Combined Min Trib`
  under `FLOW-SPEC`, replacing the older named `FLOW-MIN` records expected by
  the external calculator. Verify the maintained standalone model uses the
  same current rule before adopting these path mappings there.
- **Green Peter/Foster:** `MinFlowPlusWithdrawal.py` computes a Green Peter
  minimum release as Foster target + Foster rule-curve fill rate - Foster local
  inflow, clamped at zero. The RTS calculator mapping uses that saved Green
  Peter release, not an assumed Foster `Combined Min Trib` record. Validate the
  appropriate replacement for the legacy standalone GPR input.
- **Baseline and scheme archives:** preserve one unaugmented baseline; calculate
  every scheme from it. Save configuration, calculated minimum releases,
  Salem/Albany targets, and resulting simulation outputs with each scheme.
  Do not mistake prepared releases for successfully computed model results.
- **Input validation:** reject missing values, wrong units, incomplete seasonal
  coverage, or missing required rule records before calculating releases.
  Do not replace missing inputs with zero silently.
- **Configurable member IDs:** avoid synthetic percentile member IDs overlapping
  real RFC ensemble years. RTS uses 3000/3001/3002 for 25/50/75% daily inflow
  traces and 3003 for the OSI copy. Standalone currently retains legacy IDs;
  coordinate any future change with its alternatives, scripts, and plotting.
- **Plotting:** include Salem/Albany targets and the augmentation minimum-release
  series used by each scheme. Distinguish model results from daily percentile
  inflow traces and from quantiles across historical-member model outputs.

## Requirements to retain

- Preserve standalone trial behavior, including `omitTrialsFromFlowAug` and
  baseline-trial lookup. An RTS adaptation must be explicitly scoped to RTS.
- Preserve the April-through-October target season; a shorter test window is
  not a reason to alter the seasonal definition.
- Supplied configuration selects Lookout Point, Fall Creek, Cottage Grove,
  Dorena, Cougar, and Blue River for both Salem and Albany. Hills Creek does
  not augment independently; the calculator combines it with Lookout Point.
- Retain release limits and travel-time handling. Review any changes to those
  assumptions separately from file-path and run-ID changes.

## Current validation limits

ForecastTest_1055 records for members 1981-1991 and 3000-3002 passed checks of
33 core input series and 10 Combined Min Trib series through September 30,
2027. This validates the checked daily records, not the future augmentation
calculation or every model output. RTS reported a Java null-pointer error for
1981 despite readable checked outputs; its cause remains unresolved.

The RTS preparation and loading scripts and the explicit RTS activation switch
are implemented on the review branch. They have cloud unit tests but have not
yet been validated against actual Windows DSS/RTS. The maintained standalone
calculator remains unchanged. Augmented compute and scheme-result archiving
remain unvalidated/unimplemented, respectively.

The RTS travel shift limits reservoir release dates to the declared target
window shifted earlier by each reservoir's travel time; it does not leave NaNs
at the tail and then silently turn them into zero on write. Consider adopting
this explicit boundary handling in standalone after validation. A September 30
test end does not change the full model's April-October seasonal requirement.
