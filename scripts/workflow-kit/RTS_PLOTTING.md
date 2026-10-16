# Plot the completed RTS forecast

Install with Install-ForecastExtraction.ps1. Run plot_rts_forecast.py with hydro39
Python while the compute is finished. No DSS records are written. Plotly is already
listed in the original hydro39 environment specification; install it into that
environment if it is missing.

The actual ForecastTest2 catalog showed combined outputs in the main forecast.dss,
with F-parts C:<member>|C0, daily intervals, reservoir -Pool locations and river
location names. The new plotter selects these records from the catalog and reads
whole logical series without assuming D-part years or padded standalone names.
It ignores input copies such as RULE CURVE-C0, DUMMY-C0, and C0-INPUT. It does not
interpret the existence of an EnsembleRuns directory as proof of a successful compute.

Example first test:

```powershell
& "$env:LOCALAPPDATA\miniconda3\envs\hydro39\python.exe" -u "C:\CWMS\watershed\ResSimMaster\scripts\ExternalPython\plot_rts_forecast.py" --forecast-root "C:\CWMS\forecast\ForecastTest2\ResSimMaster" --run-code C0 --members 1981-2025 --location Detroit-Pool --start 2026-10-08 --end 2026-12-08
```

Remove --location Detroit-Pool to plot all matching reservoirs and control points.
For this previously prepared forecast, 2026/2027/2028 are legacy synthetic
percentile input traces and 2029 is the OSI copy; exclude them from historical
output bands. Future extractions reserve 3000/3001/3002 and 3003, and historical
member selection must match the actual returned RFC members and computed results.
Do not include synthetic members in the --members option used for output bands.
Members 3000/3001/3002 are now read by default as separately labeled, bold
daily 25/50/75% inflow-result overlays. They never enter the historical bands.
Missing synthetic outputs are reported; the plotter cannot compute an unrun trace.
--synthetic-members overrides that selection, and overlap with --members is rejected.

Each run writes a unique directory under <forecast>/output_plots, prints its
index.html path, and includes a local Plotly JavaScript bundle for offline use.
Plots contain individual historical member results, 5–95% and 25–75% pointwise
output bands, median, and a mapped rule-curve overlay for reservoir elevations
when available. By default rule curves come from the supplied annual CSV schedule,
and only the 11 mapped reservoirs get an overlay (no Big Cliff or Dexter lookup).
--rule-curve-source dss prefers the mapped DSS record with CSV fallback. Each
overlay is labeled by source and exported in a rule_curve CSV for date/value review.
The index now groups elevation and outflow links by reservoir and flow links
by river location. Routing reaches are omitted from the control-point selection.
Legends allow traces to be toggled. The median hover and bands
CSV report time-varying sample counts. Missing members/read failures are reported;
a chart with some readable results is not evidence every requested member completed.
read-report.csv records paths and valid coverage; series and bands are also exported.
Missing-value slots are retained and are not interpolated across in the traces.

These output bands differ from reservoir results obtained by computing daily
non-exceedance inflow traces. Plotting does not compute unrun synthetic members.
Observed overlays, Salem volume-ranked legend labels, alternative comparisons,
and augmentation are not yet ported. Original standalone plotting files are unchanged.

Cloud tests exercised path selection, member filtering, missing values, quantile
counts, and offline HTML/CSV generation against fixture records. Reading actual
Windows DSS results still requires the local test above.
