# Paste into the RTS watershed Script Editor. Jython 2.7 compatible.
# PLAN ONLY by default. No forecast data is changed.
import json
import os
import tempfile
from java.lang import ProcessBuilder
from java.io import BufferedReader, InputStreamReader, File
from usace.cavi.client import CAVI

# Set once per imported watershed if the editor does not supply __file__.
# Prefer saving this launcher in the watershed's scripts folder.
EXTERNAL_PYTHON_DIR = r'C:\CWMS\watershed\ResSimMaster\scripts\ExternalPython'
EXECUTE_TEST_COPY = False

script_file = globals().get('__file__')
if script_file and os.path.isfile(script_file):
    sibling = os.path.join(os.path.dirname(os.path.abspath(script_file)), 'ExternalPython')
    if os.path.isfile(os.path.join(sibling, 'run_extraction.py')):
        EXTERNAL_PYTHON_DIR = sibling

tab = CAVI.getCaviFrame().getForecastTab()
if tab is None:
    raise RuntimeError('No forecast tab available')
forecast = tab.getForecast()
run = tab.getSelectedForecastRun()
if forecast is None or run is None:
    raise RuntimeError('Open a forecast and select its run first')
window = run.getRunTimeWindow()
zone = tab.getTimeZone()
if window is None or zone is None:
    raise RuntimeError('Forecast time window or timezone unavailable')
context = {
    'forecast_name': str(forecast.getName()),
    'run_name': str(run.getName()),
    'dss_path': str(run.getForecastDssFilename()),
    'timezone': str(zone.getID()),
    'lookback': [str(window.getLookbackDateString()), str(window.getLookbackHrMinString())],
    'start': [str(window.getStartDateString()), str(window.getStartHrMinString())],
    'end': [str(window.getEndDateString()), str(window.getEndHrMinString())]
}
roots = [os.path.join(os.environ.get(base, ''), name)
         for base in ('LOCALAPPDATA', 'USERPROFILE')
         for name in ('miniconda3', 'anaconda3')]
roots += [r'C:\ProgramData\miniconda3', r'C:\ProgramData\anaconda3',
          r'C:\Miniconda3', r'C:\Anaconda3', r'C:\Programs\Miniconda3', r'C:\Programs\Anaconda3']
python_exe = None
for root in roots:
    candidate = os.path.join(root, 'envs', 'hydro39', 'python.exe')
    if os.path.isfile(candidate):
        python_exe = candidate
        break
if python_exe is None:
    raise IOError('hydro39 Python was not found')
runner = os.path.join(EXTERNAL_PYTHON_DIR, 'run_extraction.py')
if not os.path.isfile(runner):
    raise IOError('Install the updated ExternalPython files first: ' + runner)
descriptor, context_path = tempfile.mkstemp(prefix='ressim-context-', suffix='.json')
os.close(descriptor)
try:
    with open(context_path, 'w') as handle:
        json.dump(context, handle)
    command = [python_exe, '-u', runner, '--context', context_path]
    if EXECUTE_TEST_COPY:
        command.append('--execute')
    builder = ProcessBuilder(command)
    builder.directory(File(EXTERNAL_PYTHON_DIR))
    builder.redirectErrorStream(True)
    process = builder.start()
    reader = BufferedReader(InputStreamReader(process.getInputStream()))
    try:
        while True:
            line = reader.readLine()
            if line is None:
                break
            print line
    finally:
        reader.close()
    status = process.waitFor()
    print 'Exit code:', status
    if status:
        raise RuntimeError('Forecast extraction failed; see output above')
finally:
    os.remove(context_path)
