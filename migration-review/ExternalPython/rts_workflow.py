"""CLI backend for the RTS Swing workflow menu. Never launches model compute."""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

from extraction_context import Context
from prepare_rts_augmentation import sha256
from baseline_versions import (baseline_directory, registry, load_baseline, save_baseline,
                               write_archive_index, delete_result, result_directory, event)


def same_forecast(left, right):
    keys = ('forecast_name', 'run_name', 'timezone', 'lookback', 'start', 'end')
    return all(left.get(key) == right.get(key) for key in keys)


@contextmanager
def workflow_lock(root, action):
    lock = root / '.rts-workflow-task.json'
    try:
        with lock.open('x') as handle:
            json.dump({'pid': os.getpid(), 'action': action}, handle)
    except FileExistsError:
        raise RuntimeError('Another menu task holds {}. If its process was stopped, inspect the recorded PID before removing this stale lock.'.format(lock))
    try:
        yield
    finally:
        lock.unlink()


def promote_extract(context, folder):
    live = Context(context).dss_path
    root = live.parent
    folder = Path(folder).resolve()
    if folder.parent != root.resolve() or not folder.name.startswith('extraction-test-'):
        raise ValueError('Choose an extraction archive inside this forecast directory')
    complete = json.loads((folder / 'extraction-complete.json').read_text())
    if complete['status'] != 'complete' or not same_forecast(complete['context'], context):
        raise ValueError('Extraction does not match the selected forecast/run/time window')
    source = folder / 'forecast.dss'
    if sha256(source) != complete['dss_sha256']:
        raise ValueError('Extract checksum differs from the completed extraction')
    if (root / 'augmentation-archives/baseline').exists():
        raise ValueError('This forecast already has an archived baseline. Use a new forecast for new extracted inputs.')
    token = uuid.uuid4().hex
    candidate = root / ('forecast.extract-pending-' + token + '.dss')
    if live.exists():
        backup = root / ('forecast.before-menu-extract-' + token + '.dss')
        shutil.copy2(live, backup)
        if sha256(live) != sha256(backup):
            raise ValueError('Live DSS changed during backup; finish compute and close DSS views')
        print('Backup:', backup, flush=True)
    shutil.copy2(source, candidate)
    if sha256(candidate) != complete['dss_sha256']:
        raise ValueError('Candidate extraction copy checksum mismatch')
    if live.exists() and sha256(live) != sha256(backup):
        raise ValueError('Live DSS changed during staging; nothing replaced')
    marker = root / 'rts-augmentation-active.json'
    if marker.exists():
        marker.rename(root / ('rts-augmentation-disabled-' + token + '.json'))
    os.replace(candidate, live)
    print('Loaded extract in baseline mode:', live, flush=True)
    print('Next: compute the baseline using the normal RTS Compute action.', flush=True)


def script_arguments(action, root, settings):
    base = ['--forecast-root', str(root)]
    if action == 'reset':
        return 'load_rts_augmentation.py', base + ['--reset']
    scheme = settings['scheme'].strip()
    if action == 'load-scheme':
        return 'load_rts_augmentation.py', base + ['--scheme', scheme]
    if action == 'prepare':
        members = settings['members'].strip()
        if settings['synthetic_members'].strip():
            members += ',' + settings['synthetic_members'].strip()
        return 'prepare_rts_augmentation.py', base + [
            '--scheme', scheme, '--run-code', settings['run_code'].strip(),
            '--members', members, '--season-year', settings['season_year'].strip(),
            '--season-end', settings['season_end'].strip(), '--wy-type-mode', settings['wy_type_mode'],
            '--forecast-days', settings['forecast_days'].strip()]
    if action == 'plots':
        return 'plot_rts_forecast.py', base + ['--run-code', settings['run_code'].strip(),
            '--members', settings['members'].strip(), '--synthetic-members', settings['synthetic_members'].strip()]
    if action in ('compare', 'plot-archive'):
        extra = ['--result-dir', settings['result_dir']] if action == 'plot-archive' else []
        return 'plot_rts_augmentation.py', base + extra + ['--scheme', scheme,
            '--members', settings['members'].strip(), '--synthetic-members', settings['synthetic_members'].strip()]
    raise ValueError('Unknown action: ' + action)


def execute(args, context):
    root = Context(context).dss_path.parent
    settings = context['menu_settings']
    scripts = Path(__file__).resolve().parent
    print('Forecast:', context['forecast_name'], 'Run:', context['run_name'], flush=True)
    if args.action in ('initial-extract', 'begin-config', 'results', 'save-config', 'process-config', 'reset-baseline', 'plot-selected'):
        from workflow_simple import execute_simple
        execute_simple(args.action, args, context, scripts)
        return
    clean_context = {key: value for key, value in context.items() if key != 'menu_settings'}
    if args.action == 'load-baseline':
        load_baseline(root, clean_context, settings['run_code'].strip())
        return
    if args.action == 'save-baseline':
        save_baseline(root, clean_context, settings['run_code'].strip())
        return
    if args.action == 'list-results':
        rows = write_archive_index(root)
        print('Current baseline:', registry(root)['current'], flush=True)
        for row in rows:
            print(row['baseline_status'], row['baseline_id'], row['scheme'], row['captured_utc'], row['directory'], flush=True)
        if not rows:
            print('No archived augmented results yet.', flush=True)
        return
    if args.action == 'delete-result':
        delete_result(root, settings['result_dir'], include_plots=settings.get('include_plots', False))
        return
    if args.action == 'link-baseline':
        archive = root / 'augmentation-archives'
        baseline = baseline_directory(root)
        manifest = json.loads((baseline / 'manifest.json').read_text())
        if manifest['run_code'] != settings['run_code'].strip() or Path(manifest['forecast_root']).resolve() != root.resolve():
            raise ValueError('Existing baseline belongs to a different forecast/run code')
        if sha256(baseline / 'forecast.dss') != manifest['sha256']:
            raise ValueError('Existing baseline checksum mismatch')
        destination = archive / 'baseline-context.json'
        if destination.exists():
            raise ValueError('Baseline context is already linked; do not overwrite it')
        destination.write_text(json.dumps(clean_context, indent=2))
        data = registry(root)
        data['versions'][data['current']]['context'] = clean_context
        from baseline_versions import atomic_json
        atomic_json(archive / 'baseline-versions.json', data)
        event(root, 'baseline-context-linked', baseline_id=data['current'])
        print('Existing baseline linked to selected context. Baseline DSS unchanged.', flush=True)
        return
    if args.action == 'load-extract':
        promote_extract(context, settings['extraction_dir'])
        return
    if args.action == 'extract':
        subprocess.run([sys.executable, '-u', str(scripts / 'run_extraction.py'), '--context', args.context, '--execute'], check=True)
        return
    script, arguments = script_arguments(args.action, root, settings)
    if args.action in ('prepare', 'load-scheme'):
        archive = root / 'augmentation-archives'
        baseline_context = archive / 'baseline-context.json'
        if registry(root)['current']:
            saved = registry(root)['versions'][registry(root)['current']].get('context')
            if saved is not None:
                if not same_forecast(saved, context):
                    raise ValueError('Forecast window differs from the current baseline. Use a new forecast for changed dates or extracted inputs.')
            elif not baseline_context.exists():
                raise ValueError('Use Link existing baseline once after checking the original forecast dates.')
            else:
                saved = json.loads(baseline_context.read_text())
                if not same_forecast(saved, context):
                    raise ValueError('Forecast time window differs from its archived baseline. Create a new forecast.')
    if args.action == 'prepare':
        baseline_context = root / 'augmentation-archives/baseline-context.json'
        if not (baseline_context.parent / 'baseline').exists():
            baseline_context.parent.mkdir(exist_ok=True)
            baseline_context.write_text(json.dumps(clean_context, indent=2))
    subprocess.run([sys.executable, '-u', str(scripts / script)] + arguments, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--context', required=True)
    parser.add_argument('--action', required=True, choices=('extract', 'load-extract', 'prepare', 'load-scheme', 'reset', 'plots', 'compare', 'link-baseline', 'load-baseline', 'save-baseline', 'list-results', 'plot-archive', 'delete-result', 'initial-extract', 'begin-config', 'results', 'save-config', 'process-config', 'reset-baseline', 'plot-selected'))
    args = parser.parse_args()
    context = json.loads(Path(args.context).read_text(encoding='utf-8-sig'))
    root = Context(context).dss_path.parent
    with workflow_lock(root, args.action):
        execute(args, context)


if __name__ == '__main__':
    main()
