"""Plan by default; --execute prepares a separate DSS copy, never the live forecast."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from extraction_context import Context


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--context', required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    with open(args.context, encoding='utf-8-sig') as handle:
        data = json.load(handle)
    context = Context(data)
    print('Forecast:', data['forecast_name'], 'Run:', data['run_name'], flush=True)
    print('Live DSS (unchanged):', context.dss_path, flush=True)
    print('Existing DSS:', context.dss_path.is_file(), flush=True)
    print('Local window:', context.lookback, context.start, context.end, data['timezone'], flush=True)
    print('UTC window:', context.utc(context.lookback), context.utc(context.start), context.utc(context.end), flush=True)
    print('RFC uses the currently published ensemble; requested dates cannot extend its coverage.', flush=True)
    print('RFC daily aggregation retains the legacy six-hour shift after conversion to forecast local time.', flush=True)
    if not args.execute:
        print('PLAN ONLY: no downloads or DSS opens. Use --execute for a separate test copy.', flush=True)
        return

    from windows_ca import configure_ca_bundle
    configure_ca_bundle()

    # Close RTS/CWMSVue DSS views and ensure no compute is running before execution.
    if not context.dss_path.parent.is_dir():
        raise FileNotFoundError('Forecast directory does not exist: {}'.format(context.dss_path.parent))
    stage = Path(tempfile.mkdtemp(prefix='extraction-test-', dir=str(context.dss_path.parent)))
    target = stage / 'forecast.dss'
    if context.dss_path.is_file():
        shutil.copy2(context.dss_path, target)
    else:
        print('No existing forecast DSS. Downloaders will create a new DSS in the test directory.', flush=True)
    data['dss_path'] = str(target)
    data['percentile_members'] = {'3000': 0.25, '3001': 0.50, '3002': 0.75}
    data['osi_member'] = 3003
    context_file = stage / 'context.json'
    context_file.write_text(json.dumps(data, indent=2), encoding='utf-8')
    print('Test DSS:', target, flush=True)
    env = os.environ.copy()
    env['RESSIM_EXTRACTION_CONTEXT'] = str(context_file)
    env['PYTHONUNBUFFERED'] = '1'
    directory = Path(__file__).resolve().parent
    scripts = ['RFC_Downloader_Module.py', 'CWMS_Downloader_Module.py',
               'Dummy_0_and_WY_Abundant_Module.py', 'OSI_Ensemble_Year.py', 'write_rule_curves.py',
               'write_ensemble_shared_inputs.py']
    log = stage / 'extraction.log'
    with log.open('w', encoding='utf-8') as handle:
        for script in scripts:
            print('Running:', script, flush=True)
            proc = subprocess.Popen([sys.executable, '-u', str(directory / script)],
                                    cwd=str(directory), env=env, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, errors='replace')
            with proc.stdout:
                for line in proc.stdout:
                    print(line, end='', flush=True)
                    handle.write(line)
                    handle.flush()
            status = proc.wait()
            if status:
                raise RuntimeError('{} failed ({}). Partial test copy retained at {}; log: {}'.format(script, status, target, log))
    print('Extraction steps completed on TEST COPY ONLY:', target, flush=True)
    import hashlib
    digest = hashlib.sha256()
    with target.open('rb') as dss_handle:
        for block in iter(lambda: dss_handle.read(1024 * 1024), b''):
            digest.update(block)
    (stage / 'extraction-complete.json').write_text(json.dumps({
        'status': 'complete', 'context': data, 'dss_sha256': digest.hexdigest()}, indent=2), encoding='utf-8')
    print('MENU_EXTRACT:', stage, flush=True)
    print('Not compute-ready yet: verify rule-curve inputs, ensemble membership, and RTS mapping behavior.', flush=True)


if __name__ == '__main__':
    main()
