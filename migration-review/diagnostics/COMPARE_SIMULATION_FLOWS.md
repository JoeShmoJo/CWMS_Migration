# Serial versus parallel flow comparison

ExternalPython/compare_simulation_flows.py performs no DSS writes. Close ResSim
and DSS views before running so input data do not change during comparison. Both
input files must already exist; the report goes into a new directory. The
script uses the existing hydro39 Python/pydsstools environment on Windows.

Scope is exactly 13 named reservoir pool FLOW-OUT series and Willamette_at Salem
FLOW, for each requested ensemble member and one exact F-part run/trial suffix.
It excludes other trials, inputs, elevations, powerplants and diversions. Default
members are 1982-2024 (43); 14 locations yield 602 logical comparisons. The
--run-code argument is the suffix after |, for example Con_Season1. If omitted,
the script lists available suffixes without reading time-series data. If an
explicit suffix is unavailable in either file it lists common suffixes and exits
2; do not guess another trial merely to obtain matching results.

Reads cataloged calendar blocks, rather than probing blank D parts. Blocks are
merged by timestamp, with inconsistent overlaps rejected. Units/type/interval
and A parts must match. Exact numerical comparison is the default (--atol 0).
An explicitly chosen absolute tolerance is available; there is no relative
 tolerance, rounding, interpolation or filling. Missing/undefined values fail,
even if missing in both files. Different coverage among selected series also
fails; daily coverage is checked for holes. --start and --end can restrict an
inclusive ISO timestamp window. Without them, all selected cataloged output
coverage is compared. Identical stale outputs, or a complete period absent from
both files, cannot be detected without external run provenance/window evidence.

Reports:
- result.txt: PASS/FAIL, selected files/trial/members, compared range, counts.
- summary.csv: every location/member, status, sample counts, gaps, differences,
  maximum absolute difference and date bounds.
- differences.csv: first 2000 missing/different samples with both values.
  Summary counts cover all compared samples even after the detail cap.

Exit status 0 means every expected series matches within the selected tolerance
and coverage checks; 1 means differences/missing records/read errors; 2 means an
argument or trial-selection problem. No full-model equivalence is established:
only requested flows are compared. Reports can be inspected without ResSim.

Five local tests passed, including complete matching and missing-Salem CLI cases
with stub DSS readers, member/trial/parameter selection, missing timestamps,
exact/toleranced value differences, and calendar-block merge/conflicts. Real DSS
I/O must run on the user's Windows machine; pydsstools is not installed here.
