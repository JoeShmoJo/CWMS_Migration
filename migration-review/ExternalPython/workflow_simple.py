"""Four-action RTS workflow. Configurations are portable; computed results are immutable."""
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import uuid

import pandas as pd

from baseline_versions import (atomic_json, baseline_directory, baseline_identity,
    digest_file, disable, event, registry, save_baseline, write_archive_index)
from extraction_context import Context
from plot_rts_forecast import clean_series, output_groups
from prepare_rts_augmentation import read_config

CONFIG_NAME = 'MinFlowSalemAlbanyConfig.csv'


def read_configuration(path):
    """Read the installed CSV without editing it; retain every variable."""
    read_config(path)  # Use the same validation as the calculator.
    with open(path, encoding='utf-8-sig', newline='') as handle:
        rows = list(csv.reader(handle))
    start = next(i for i, row in enumerate(rows) if row and row[0].strip() == 'Variable')
    header = [cell.strip() for cell in rows[start]]
    while header and not header[-1]:
        header.pop()
    body = [[cell.strip() for cell in (row[:len(header)] + [''] * len(header))[:len(header)]]
            for row in rows[start + 1:] if row and row[0].strip() and not row[0].lstrip().startswith('#')]
    return {'schema': 1, 'name': 'configuration', 'columns': header, 'rows': body,
            'calculation': {'forecast_days': 10, 'wy_type_mode': 'fixed-abundant'}}


def write_configuration_csv(config, destination):
    if config.get('schema') != 1 or not str(config.get('name', '')).strip():
        raise ValueError('A configuration name is required')
    columns, rows = config['columns'], config['rows']
    if not columns or columns[0] != 'Variable' or any(len(row) != len(columns) for row in rows):
        raise ValueError('Configuration table has missing or extra cells')
    numeric = {'MaxConElev', 'MinConElev', 'MinConStor', 'SummerBufferElev', 'MaxRelease', 'TravelTimeDays'}
    for row in rows:
        if row[0] in numeric and any(not math.isfinite(float(value)) for value in row[1:]):
            raise ValueError('Nonfinite numeric configuration value: ' + row[0])
    calculation = config['calculation']
    if int(calculation['forecast_days']) < 1 or calculation['wy_type_mode'] not in ('fixed-abundant', 'storage-maf'):
        raise ValueError('Invalid calculation settings')
    destination = Path(destination)
    with destination.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        writer.writerows(rows)
    read_config(destination)


def save_configuration(config, destination):
    """Portable JSON has no simulation dates, member IDs or baseline reference."""
    with tempfile.TemporaryDirectory(prefix='rts-config-') as directory:
        write_configuration_csv(config, Path(directory) / CONFIG_NAME)
    allowed = {key: config[key] for key in ('schema', 'name', 'columns', 'rows', 'calculation')}
    atomic_json(destination, allowed)
    print('Saved reusable configuration:', destination, flush=True)


def inspect_run(filename, run_code=None):
    """Infer members and coverage from actual finite reservoir/river outputs."""
    from run_data_cache import is_archived, open_cached_run
    if is_archived(filename) and run_code is not None:
        reader = open_cached_run(filename, run_code)
    else:
        from pydsstools.heclib.dss import HecDss
        reader = HecDss.Open(str(filename))
    with reader as dss:
        paths = dss.getPathnameList('/*/*/*/*/*/*/')
        codes = set()
        members = set()
        for path in paths:
            parts = str(path).split('/')
            if len(parts) == 8:
                match = re.fullmatch(r'C:(\d{6})\|([A-Za-z]\d+)', parts[6])
                if match:
                    codes.add(match[2].upper())
                    members.add(int(match[1]))
        if run_code is None:
            if len(codes) != 1:
                raise ValueError('Cannot identify one output run code. Finish the selected RTS compute first.')
            run_code = next(iter(codes))
        groups = output_groups(paths, run_code, members)
        if hasattr(dss, 'metadata'):
            coverage = {int(member): [(pd.Timestamp(first), pd.Timestamp(last)) for first, last in spans]
                        for member, spans in dss.metadata['coverage'].items()}
        else:
            coverage = {}
            for key, member_paths in groups.items():
                for member, path in member_paths.items():
                    series = clean_series(dss.read_ts(path, trim_missing=True)).dropna()
                    if series.empty:
                        continue
                    coverage.setdefault(member, []).append((series.index[0], series.index[-1]))
        if not coverage:
            raise ValueError('No finite computed outputs. Run the model in RTS before continuing.')
    first = max(pair[0] for pairs in coverage.values() for pair in pairs)
    last = min(pair[1] for pairs in coverage.values() for pair in pairs)
    historical = sorted(member for member in coverage if member < 3000)
    synthetic = sorted(member for member in coverage if member >= 3000)
    if not historical:
        raise ValueError('No historical-member outputs were found')
    seasons = []
    for year in range(first.year, last.year + 1):
        april = pd.Timestamp(year=year, month=4, day=1)
        end = min(last.normalize(), pd.Timestamp(year=year, month=10, day=31))
        if first <= april - pd.Timedelta(days=2) and end >= april:
            seasons.append({'year': year, 'end': end.strftime('%Y-%m-%d')})
    return {'run_code': run_code, 'members': historical, 'synthetic_members': synthetic,
            'first': str(first), 'last': str(last), 'seasons': seasons}


def accept_completed(root, context):
    """Only called after the operator confirms a completed manual compute."""
    from plot_rts_augmentation import capture
    from load_rts_augmentation import validate_manifest
    root = Path(root)
    if (root / 'baseline-execution-test.json').exists():
        raise ValueError('Diagnostic execution mode is active; do not accept timing-test results as baseline.')
    data = registry(root)
    if data['current']:
        saved_context = data['versions'][data['current']].get('context')
        keys = ('forecast_name', 'run_name', 'timezone', 'lookback', 'start', 'end')
        if saved_context and any(saved_context.get(key) != context.get(key) for key in keys):
            raise ValueError('Forecast dates differ from the saved baseline. Use a new forecast for new dates or extracted inputs.')
    marker = root / 'rts-augmentation-active.json'
    baseline_configuration_pointer = None
    if marker.exists():
        active = json.loads(marker.read_text())
        scheme = root / 'augmentation-archives' / active['scheme']
        manifest = json.loads((scheme / 'manifest.json').read_text())
        validate_manifest(root, scheme, manifest)
        if active['augmentation_sha256'] != manifest['augmentation_sha256'] or active['baseline_sha256'] != manifest['baseline_sha256']:
            raise ValueError('Active scheme provenance differs from its archived configuration')
        live_hash = digest_file(root / 'forecast.dss')
        for path in scheme.glob('results-*/capture.json'):
            saved = json.loads(path.read_text())
            if not (path.parent / 'FAILED.txt').exists() and saved['sha256'] == live_hash:
                if saved['scheme'] != manifest['scheme'] or saved['baseline_sha256'] != manifest['baseline_sha256']:
                    raise ValueError('Archived result provenance mismatch')
                if digest_file(path.parent / 'forecast.dss') != live_hash:
                    raise ValueError('Previously archived result checksum mismatch')
                event(root, 'completed-result-reused', directory=str(path.parent))
                print('Results already archived:', path.parent, flush=True)
                return
        directory = capture(root, scheme, manifest)
        metadata = json.loads((directory / 'capture.json').read_text())
        metadata['compute_status'] = 'user-confirmed-success-not-verified'
        atomic_json(directory / 'capture.json', metadata)
        print('Accepted completed augmentation:', directory, flush=True)
    else:
        data = registry(root)
        code = data['versions'][data['current']]['run_code'] if data['current'] else None
        details = inspect_run(root / 'forecast.dss', code)
        from baseline_configuration import check_initialization
        baseline_configuration_pointer = check_initialization(root, details)
        if data['current']:
            # The explicit completed-compute confirmation is the acceptance
            # action; no old DSS is loaded over the just-computed results.
            atomic_json(root / 'augmentation-archives/baseline-edit-session.json',
                        {'baseline_id': data['current'], 'context': context, 'run_code': details['run_code']})
        save_baseline(root, context, details['run_code'])
    if baseline_configuration_pointer is not None:
        from baseline_configuration import archive_configuration
        directory = root / 'baseline-configurations' / 'accepted-computes' / uuid.uuid4().hex
        directory.mkdir(parents=True)
        archive_configuration(root, directory, baseline_configuration_pointer)
        atomic_json(directory / 'acceptance.json', {'baseline_id': registry(root)['current'],
                    'forecast_dss_sha256': digest_file(root / 'forecast.dss'),
                    'compute_status': 'user-confirmed-success-not-verified'})
        event(root, 'baseline-configuration-compute-accepted', directory=str(directory),
              configuration_id=baseline_configuration_pointer['id'], baseline_id=registry(root)['current'])
    # Warm the immutable archive once; future configuration/plots reuse arrays.
    from run_data_cache import open_cached_run
    if marker.exists():
        source, code = directory / 'forecast.dss', manifest['run_code']
    else:
        source = baseline_directory(root) / 'forecast.dss'
        code = registry(root)['versions'][registry(root)['current']]['run_code']
    with open_cached_run(source, code):
        pass
    pending = root / 'augmentation-archives/workflow-pending.json'
    if pending.exists():
        pending.unlink()


def catalog(root):
    data = registry(root)
    runs = []
    for identity, version in data['versions'].items():
        runs.append({'id': identity, 'kind': 'baseline', 'baseline_id': identity,
                     'label': identity + ' (unaugmented)', 'directory': str(Path(root) / 'augmentation-archives' / version['directory']),
                     'status': 'Current baseline' if identity == data['current'] else 'Previous baseline'})
    for row in write_archive_index(root):
        directory = Path(row['directory'])
        manifest = json.loads((directory.parent / 'manifest.json').read_text())
        runs.append({'id': str(directory.relative_to(Path(root) / 'augmentation-archives')),
                     'kind': 'augmented', 'baseline_id': row['baseline_id'], 'directory': str(directory),
                     'label': '{} — {}'.format(manifest.get('configuration_name', row['scheme']), row.get('captured_utc') or directory.name),
                     'status': row['baseline_status']})
    return runs


def state(root, context, scripts, include_config=False):
    data = registry(root)
    result = {'context': context, 'current_baseline': data['current'], 'runs': catalog(root)}
    if include_config:
        if not data['current']:
            raise ValueError('Compute the initial unaugmented model and confirm completion before opening augmentation configuration.')
        source = baseline_directory(root) / 'forecast.dss'
        result['outputs'] = inspect_run(source, data['versions'][data['current']]['run_code'])
        default = Path(scripts).parent / 'externalSVs' / CONFIG_NAME
        result['configuration'] = read_configuration(default)
        if not result['outputs']['seasons']:
            print('No conservation season is covered by this baseline. Configuration can be saved, but releases cannot be processed.', flush=True)
    filename = Path(root) / 'augmentation-archives/workflow-state.json'
    atomic_json(filename, result)
    print('MENU_STATE:', filename, flush=True)
    return result


def process_configuration(root, context, settings, scripts):
    if settings.get('confirm_completed'):
        accept_completed(root, context)
    data = registry(root)
    if not data['current']:
        raise ValueError('Compute and accept the initial unaugmented baseline first')
    pending = Path(root) / 'augmentation-archives/workflow-pending.json'
    if pending.exists() and json.loads(pending.read_text())['mode'] == 'baseline':
        raise ValueError('A new baseline compute is pending. Compute it in RTS and confirm completion before processing augmentation.')
    expected = settings.get('expected_baseline_id')
    if expected and expected != data['current'] and not settings.get('confirm_completed'):
        raise ValueError('The current baseline changed after opening the editor. Reopen Augmentation Configuration.')
    version = data['versions'][data['current']]
    if version.get('context'):
        keys = ('forecast_name', 'run_name', 'timezone', 'lookback', 'start', 'end')
        if any(version['context'].get(key) != context.get(key) for key in keys):
            raise ValueError('Forecast dates differ from this baseline. Create a new forecast for changed dates.')
    details = inspect_run(baseline_directory(root) / 'forecast.dss', version['run_code'])
    season = next((item for item in details['seasons'] if item['year'] == int(settings['season_year'])), None)
    if not season:
        raise ValueError('Selected conservation season is not covered by the baseline')
    config = settings['configuration']
    slug = re.sub('[^A-Za-z0-9_-]+', '_', str(config['name'])).strip('_') or 'configuration'
    scheme_name = slug[:60] + '-' + data['current'] + '-' + uuid.uuid4().hex[:8]
    with tempfile.TemporaryDirectory(prefix='rts-config-') as directory:
        config_csv = Path(directory) / CONFIG_NAME
        write_configuration_csv(config, config_csv)
        arguments = ['--forecast-root', str(root), '--scheme', scheme_name,
            '--config-csv', str(config_csv), '--run-code', details['run_code'],
            '--members', ','.join(str(member) for member in details['members'] + details['synthetic_members']),
            '--season-year', str(season['year']), '--season-end', season['end'],
            '--forecast-days', str(config['calculation']['forecast_days']),
            '--wy-type-mode', config['calculation']['wy_type_mode']]
        subprocess.run([sys.executable, '-u', str(Path(scripts) / 'prepare_rts_augmentation.py')] + arguments, check=True)
    scheme = Path(root) / 'augmentation-archives' / scheme_name
    atomic_json(scheme / 'configuration.json', config)
    manifest = json.loads((scheme / 'manifest.json').read_text())
    manifest['configuration_name'] = config['name']
    manifest['configuration_sha256']['configuration.json'] = digest_file(scheme / 'configuration.json')
    atomic_json(scheme / 'manifest.json', manifest)
    subprocess.run([sys.executable, '-u', str(Path(scripts) / 'load_rts_augmentation.py'),
                    '--forecast-root', str(root), '--scheme', scheme_name], check=True)
    atomic_json(pending, {'mode': 'augmentation', 'scheme': scheme_name, 'baseline_id': data['current']})
    print('Releases processed and loaded. Reopen this forecast and run the model in RTS. Do not re-extract.', flush=True)


def reset_baseline(root, context, confirm_completed=False):
    if confirm_completed:
        accept_completed(root, context)
    data = registry(root)
    disable(root, uuid.uuid4().hex)
    if data['current']:
        version = data['versions'][data['current']]
        atomic_json(Path(root) / 'augmentation-archives/baseline-edit-session.json',
                    {'baseline_id': data['current'], 'context': context, 'run_code': version['run_code']})
    atomic_json(Path(root) / 'augmentation-archives/workflow-pending.json', {'mode': 'baseline'})
    event(root, 'baseline-reset-requested', baseline_id=data['current'])
    print('Augmentation disabled. Modify the base alternative if needed, then run it in RTS.', flush=True)
    print('The baseline version and older result labels will change only when different completed unaugmented results are accepted.', flush=True)


def execute_simple(action, args, context, scripts):
    settings = context.get('menu_settings', {})
    clean = {key: value for key, value in context.items() if key != 'menu_settings'}
    root = Context(clean).dss_path.parent
    if action == 'initial-extract':
        if registry(root)['current']:
            raise ValueError('Initial extract is already complete for this forecast. Use Reset Baseline for model changes, or create a new forecast for new dates/downloads.')
        existing = set(root.glob('extraction-test-*/extraction-complete.json'))
        subprocess.run([sys.executable, '-u', str(Path(scripts) / 'run_extraction.py'), '--context', args.context, '--execute'], check=True)
        # Load only the verified completed archive from this invocation/context.
        from rts_workflow import promote_extract, same_forecast
        candidates = []
        for path in set(root.glob('extraction-test-*/extraction-complete.json')) - existing:
            metadata = json.loads(path.read_text())
            if same_forecast(metadata['context'], clean):
                candidates.append(path)
        if len(candidates) != 1:
            raise ValueError('Expected one newly completed extraction for this invocation; nothing loaded')
        promote_extract(clean, candidates[0].parent)
        atomic_json(root / 'augmentation-archives/workflow-pending.json', {'mode': 'baseline'})
    elif action in ('begin-config', 'results'):
        if settings.get('confirm_completed'):
            accept_completed(root, clean)
        state(root, clean, scripts, include_config=action == 'begin-config')
    elif action == 'save-config':
        save_configuration(settings['configuration'], settings['configuration_file'])
    elif action == 'process-config':
        process_configuration(root, clean, settings, scripts)
    elif action == 'reset-baseline':
        reset_baseline(root, clean, settings.get('confirm_completed', False))
    elif action == 'plot-selected':
        available = {row['id']: row for row in catalog(root)}
        ids = settings['selected_runs']
        if len(ids) not in (1, 2) or len(set(ids)) != len(ids) or any(identity not in available for identity in ids):
            raise ValueError('Choose one or two distinct saved runs')
        with tempfile.TemporaryDirectory(prefix='rts-plots-') as directory:
            selected = Path(directory) / 'runs.json'
            atomic_json(selected, [available[identity] for identity in ids])
            subprocess.run([sys.executable, '-u', str(Path(scripts) / 'plot_rts_runs.py'),
                            '--forecast-root', str(root), '--runs-json', str(selected)], check=True)
    else:
        raise ValueError('Unknown simplified workflow action: ' + action)
