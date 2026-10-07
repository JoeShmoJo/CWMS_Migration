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
CWMS forecast elevations are requested from six hours before lookback through
six hours after forecast time, to include native UTC-grid samples bracketing
midnight in the forecast timezone. Their timestamps are not shifted to midnight.
Required lookback downloads run first and must cover the actual lookback window.
daily CWMS records retain their Pacific civil clock labels across DST transitions,
whereas six-hour elevations use the fixed forecast timezone. No observations are
interpolated or filled. The daily source zone defaults to America/Los_Angeles and
can be overridden with CONFIG.CWMS_DAILY_TIMEZONE for another source convention.
Observed and plotting rule-curve download groups retain their older windows.
Historical observed elevation/outflow records preserve missing days as DSS UNDEFINED
slots rather than interpolating or shifting later values. Required lookback and
RFC inputs still reject missing values and insufficient coverage. Missing/failed
plotting groups produce warnings and do not prevent the required workflow from
continuing. OSI copying retains CONFIG.ENSEMBLE_YEAR_TO_COPY and 2029.

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
alternative's exact record mappings and ensemble membership. The final loader
now writes the 11 mapped ELEV/1DAY/RULE CURVE records from the user's annual
CON_SEASON_RULE_CURVES.csv table. The CSV preserves all 13 reservoir columns and
366 original generic-year rows; the matching Dec 31 boundary is deduplicated when
building the annual lookup. Dates are expanded through the forecast window with
one daily point of padding at each end. Elevations are treated as feet, consistent
with this model. No interpolation is applied; a forecast spanning Feb 29 fails
until an explicit value/policy is provided. Standalone rule-curve files remain
unchanged. The downloaded CENWP-CALC plotting curves are separate records.
Validate the copied DSS before any live forecast use.
Plotting and augmentation scripts are not yet adapted.

Once local tests pass, install these same Python files into the maintained
standalone watershed, validate its normal launchers, then carry them through
future imports. Script-pane/program-order registration and reimport retention
have not been verified. Do not assume these live processes or registration
survive an import.
