# Forecast extraction: first local test

The standalone watershed is the maintained source. Carry its scripts with each
RTS import. The four existing Python entry points still default to CONFIG.SIM_NAME
and rss/<simulation>/simulation.dss when no RESSIM_EXTRACTION_CONTEXT is supplied.
The new runner supplies an explicit context without editing CONFIG.py.

## Install into the imported watershed for testing

Fetch and check out the `forecast-extraction-context` branch in the repository.
Run `Install-ForecastExtraction.ps1` from migration-review. It backs up existing
files outside the watershed, then copies only the six changed/new Python files
and the RTS launcher. It does not alter CONFIG.py, alt_config, or model files.
The installer prints the backup location. An explicit -WatershedRoot supports
other paths; -BackupRoot supports another backup location.

Open the installed scripts/RTS_FORECAST_EXTRACT.py in the RTS Script Editor, or
paste its contents into your test script. It defaults to PLAN ONLY. If the editor
does not supply __file__, set EXTERNAL_PYTHON_DIR once for the imported watershed.
Select the intended forecast run. Verify the printed forecast name, DSS path,
local/UTC dates, and exit code. Nothing is downloaded in this mode.

## Separate test DSS

After the plan is correct, close DSS views and ensure no compute or other writer
is running. Set EXECUTE_TEST_COPY=True in the launcher. The runner copies the
forecast DSS into a unique extraction-test-* directory beside the original and
runs the four steps synchronously, stopping on the first nonzero exit code.
If the forecast directory exists but its DSS has not been created, the downloaders
create a fresh DSS in the test directory instead. Plan mode needs neither file nor directory.
Partial test copies and extraction.log remain for diagnosis. It never promotes
the test copy or changes the original forecast DSS.

The RFC endpoint supplies its current ensemble, not arbitrary requested dates.
Coverage checks reject missing intervals and insufficient endpoints. The legacy
six-hour daily aggregation shift and synthetic members 2026/2027/2028 are retained;
forecast mode converts incoming timestamps to the fixed forecast timezone first.
That alignment still needs validation against the working standalone dataset.
CWMS forecast elevations are requested from lookback through forecast time;
daily CWMS records retain their Pacific civil clock labels across DST transitions,
whereas six-hour elevations use the fixed forecast timezone. No observations are
interpolated or filled. The daily source zone defaults to America/Los_Angeles and
can be overridden with CONFIG.CWMS_DAILY_TIMEZONE for another source convention.
observed and rule-curve download groups retain their older windows. All requested
CWMS series must return data, so an ancillary missing series may stop this first
test; the error names it. OSI copying retains CONFIG.ENSEMBLE_YEAR_TO_COPY and 2029.

TLS verification stays enabled, including standalone CWMS downloads. The legacy
certificate-verification bypass is removed. By default on Windows, the runner
combines certifi's public roots with Windows ROOT certificates trusted for TLS
server authentication. It validates the PEM, passes REQUESTS_CA_BUNDLE to child
processes, and removes its unique temporary bundle at exit. Explicit user bundles
in REQUESTS_CA_BUNDLE or CURL_CA_BUNDLE are preserved. If verification still fails,
inspect the exact error and the installed organization roots; do not disable it.

## What this test does not establish

No real network, Windows Java/Jython, or DSS extraction was executed in the cloud.
Automated tests cover context parsing, midnight/UTC conversion, coverage/gap
checks, runner ordering, failure propagation, and isolation of the live DSS using
stub processes. Local testing remains required.

Successful extraction does not yet prove Con_Season compute readiness. Check the
alternative's exact record mappings and ensemble membership, and supply its
shared/Willamette_Rule_Curves.dss records if RTS redirects those to forecast.dss.
The downloaded CENWP-CALC rule curves use different pathnames and are not a
replacement for that file. Validate the copied DSS before any live forecast use.
Plotting and augmentation scripts are not yet adapted.

Once local tests pass, install these same Python files into the maintained
standalone watershed, validate its normal launchers, then carry them through
future imports. Script-pane/program-order registration and reimport retention
have not been verified. Do not assume these live processes or registration
survive an import.
