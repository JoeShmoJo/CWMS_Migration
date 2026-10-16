# Standalone ensemble / single POR mode and Model Check

Select the simulation and alternative in the standalone menu, then choose
**Simulation type → Ensemble** or **Single POR**. This is an explicit workflow
selection; it does not modify ResSim's native run type or infer the GUI state.
Verify the native simulation is configured the same way.

## Single period-of-record run

1. Select **Single POR** and open Baseline Configuration. OSI settings are hidden
   and not required. Save/Apply operating settings as needed.
2. Supply the model's existing POR inputs and compute normally in ResSim. The RFC
   ensemble extraction and ensemble augmentation calculator are unavailable in
   this mode; no OSI copy runs. This change does not implement a POR extractor or
   rewrite the ensemble augmentation calculation for POR.
3. Open **Archive / Plot Results**. Pick the completed ordinary F-part output,
   such as CON_SEASON0, give it a name, and archive it as a baseline or a result
   paired with an existing POR baseline. Confirmation still requires actual
   successful compute and full required date coverage.
4. Select one or two archived POR runs and plot. These are single time-series
   lines, not ensemble probability bands. Archives remain usable after live DSS
   changes/deletion. POR/ensemble data are distinguished in capture.json; results
   cannot be paired with a baseline of a different run type.

The POR archiver selects ordinary F-parts, not C:<member>|<suffix>. The ensemble
archiver continues selecting member-prefixed paths. Existing archives without
run_type metadata are interpreted as ensemble archives. A plot can contain
multiple physical date blocks; there is no hardcoded calendar year window.

## Check a POR run or one ensemble member

1. Finish native compute and close DSS views. In the standalone menu select the
   actual simulation, alternative and type, then click **Model Check**. This opens
   the same result browser, which now contains a Model check section.
2. Choose the completed output suffix above the Model check section.
3. **Ensemble:** enter exactly one member ID, for example 2000 or 3003. The wrapper
   selects exactly C:002000|<suffix>, not whichever member has the most records.
   **Single POR:** the member input is hidden; the ordinary suffix is used directly.
4. Click **Run Model Check**, confirm the source run/configuration are the ones
   intended, and wait. The report opens in a browser, or an error appears in the
   result browser. The source simulation.dss is read, not rewritten; no new compute
   starts and no shared model_check_config.txt is changed.
5. Review report warnings and individual checks. A completed report is not an
   assertion that every check passed or that all selected records are fresh.

## Files, producing programs and preservation

| Artifact | Location relative to standalone watershed | Producer / use |
| --- | --- | --- |
| Existing checker source | scripts/model_check/{extract_dss.py,check_model.py,catalog_dss.py,run_model_check.py} | Existing user-supplied checker; installed with file backups |
| Control point limits | scripts/model_check/control_point_limits.csv | Checker input; preserved/updated with the supplied source |
| GUI adapter | scripts/ExternalPython/standalone_model_check.py | Exact output/member selection, active-table overrides, new report folder |
| Source results | rss/<simulation>/simulation.dss | Native compute → exact F-part extraction |
| Per-job root | rss/<simulation>/model-check-runs/check-<uuid>/ | Adapter; new directory each invocation |
| Job context | Per-job root/check-context.json | Source signature, selected F-part/member/mode/config ID and complete/incomplete status |
| Extracted run | Per-job root/<simulation>_<alternative>_<date>/ | Existing extractor → checker |
| Result CSVs | Extracted run/{reservoirs,limits,junctions,diversions,rules}.csv and *_series.csv | Selected member/POR results plus units/path references |
| Extract metadata | Extracted run/run_info.json | Extractor; original alternative and source watershed |
| Model operation report | Extracted run/modelReport.json, when available | Exact matching modelReport_<alternative>.json copied from rss or the simulation |
| Report and figures | Extracted run/report.html, plots/, release_decisions/ and summary CSVs | Existing checker; offline Plotly files included |
| Disabled-demand expectations | Extracted run/*ConfigCSV-disabled.csv, if the coupled switch is off | Adapter; report-local zero schedules, original CSVs unchanged |
| Portable checker code | scripts/workflow-kit/model_check/ | Kit; only code, README and control-point limits, not old output folders/caches |

The wrapper uses the currently applied baseline's generated CSV tables when the
active pointer matches this alternative and passes its resolved checksum. With no
active baseline it uses the checker's legacy configuration resolution. If the
coupled scripts/diversion-demands.json switch is explicitly false, withdrawal and
diversion expected schedules are zeroed in report-local copies. Other switches
or manual native operation changes are not automatically interpreted.

Only the exact alternative's operation report is copied; an unrelated report is
not substituted. A missing report limits rule-stack checks. Report freshness and
whether the active configuration actually produced all selected outputs still
require operator verification. In particular, do not apply a new configuration
and then check old live results as if they were produced with it.

The adapter runs the checker against live full outputs because compact archives
omit many rule/control series the checker needs. It does not currently check an
archived compact run. Past check folders stay intact. The original manual checker
and its config file remain available; the GUI uses no shared config file.

Start with one short known POR or one ensemble member, inspect its selected F-part
in check-context.json/run_info.json and compare with a known report before using
this for a large study. Local Windows/DSS execution remains necessary validation.
