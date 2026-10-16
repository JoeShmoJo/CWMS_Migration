# Standalone ensemble / single POR mode and Model Check

Select the simulation and alternative in the standalone menu, then choose
**Simulation type → Ensemble** or **Single POR**. This is an explicit workflow
selection; it does not modify ResSim's native run type or infer the GUI state.
Verify the native simulation is configured the same way.

## Single period-of-record run

1. Select **Single POR** and open Baseline Configuration. OSI settings are hidden
   and not required. Save/Apply operating settings as needed.
2. Supply the model's existing POR inputs and compute normally in ResSim. RFC
   ensemble extraction remains unavailable; no OSI copy runs. Augmentation is
   available for both run types through **Calculate augmentation** after baseline
   compute. The POR adapter reads the selected alternative's actual native blocks,
   not the ensemble calculator's fixed calendar-year list. Its daily calculation
   uses complete-day averages of period-average flows and end-of-day storage/WY
   values for subdaily sources. Incomplete boundary days are omitted; gaps,
   conflicting records, ambiguous intervals and mismatched coverage stop the job.
   Daily sources retain their native timestamps. It writes daily augmentation
   requirement records under the same POR F-part; confirm the existing native
   augmentation mapping reads those daily requirements, then recompute. Compare
   a short known case before relying on a longer study. Seasonal allocation logic,
   configured minimum storage, forecast horizon and input mappings are unchanged.
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
   actual simulation, alternative and simulation type, then click **Model Check**.
2. The dedicated Model Check page uses that target directly. An optional report
   name identifies this check; repeated checks always create unique folders.
3. **Single POR:** no member, completed-output, archive-purpose or baseline
   selection is shown. **Ensemble:** enter exactly one member ID.
4. Click **Run Model Check** and confirm. The normal native alternative suffix
   (formatted alternative plus trial 0) is selected when present. If it is absent,
   a sole matching trial is accepted; ambiguity stops the check rather than
   selecting another output arbitrarily. Exact member selection is retained.
   The report opens in a browser. Errors appear on the page. The source DSS is
   read only, no compute starts and no shared model_check_config.txt is changed.
5. Review report warnings and individual checks. A completed report is not an
   assertion that every check passed or that all selected records are fresh.

## Files, producing programs and preservation

| Artifact | Location relative to standalone watershed | Producer / use |
| --- | --- | --- |
| Existing checker source | scripts/model_check/{extract_dss.py,check_model.py,catalog_dss.py,run_model_check.py} | Existing user-supplied checker; installed with file backups |
| Control point limits | scripts/model_check/control_point_limits.csv | Checker input; preserved/updated with the supplied source |
| GUI adapter | scripts/ExternalPython/standalone_model_check.py | Exact output/member selection, active-table overrides, new report folder |
| POR augmentation adapter | scripts/ExternalPython/standalone_por_augmentation.py | Catalog-based POR selection and validated daily input conversion for MainstemAugmentation.py |
| Source results | rss/<simulation>/simulation.dss | Native compute → exact F-part extraction |
| Per-job root | rss/<simulation>/model-check-runs/check-<report-name>-<uuid>/ | Adapter; new directory each invocation |
| Job context | Per-job root/check-context.json | Report name, source signature, selected F-part/member/mode/config ID and complete/incomplete status |
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
