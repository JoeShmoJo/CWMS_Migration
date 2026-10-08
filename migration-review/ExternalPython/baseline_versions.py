"""Immutable RTS baseline versions, result provenance, and an append-only action trail."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import uuid

import numpy as np
import pandas as pd


def digest_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.pending')
    temporary.write_text(json.dumps(data, indent=2, allow_nan=False), encoding='utf-8')
    os.replace(temporary, path)


def event(root, action, **details):
    archive = Path(root) / 'augmentation-archives'
    archive.mkdir(exist_ok=True)
    record = dict(utc=datetime.now(timezone.utc).isoformat(), action=action, **details)
    with (archive / 'action-history.jsonl').open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(record, allow_nan=False) + '\n')
        handle.flush()
        os.fsync(handle.fileno())


def registry(root):
    archive = Path(root) / 'augmentation-archives'
    filename = archive / 'baseline-versions.json'
    if filename.exists():
        return json.loads(filename.read_text(encoding='utf-8'))
    legacy = archive / 'baseline'
    if not legacy.exists():
        return {'current': None, 'versions': {}}
    manifest = json.loads((legacy / 'manifest.json').read_text())
    if digest_file(legacy / 'forecast.dss') != manifest['sha256']:
        raise ValueError('Existing baseline checksum mismatch')
    context_path = archive / 'baseline-context.json'
    version = {'directory': 'baseline', 'sha256': manifest['sha256'],
               'run_code': manifest['run_code'], 'fingerprint': None,
               'context': json.loads(context_path.read_text()) if context_path.exists() else None}
    data = {'current': 'baseline-0001', 'versions': {'baseline-0001': version}}
    atomic_json(filename, data)
    event(root, 'baseline-registered', baseline_id='baseline-0001', legacy=True)
    return data


def baseline_directory(root, manifest=None):
    root = Path(root)
    data = registry(root)
    if not data['current']:
        # Legacy callers can still check the missing physical path themselves.
        return root / 'augmentation-archives/baseline'
    identity = data['current']
    if manifest is not None:
        identity = manifest.get('baseline_id')
        if identity is None:
            identity = next((key for key, value in data['versions'].items()
                             if value['sha256'] == manifest['baseline_sha256']), None)
        if identity not in data['versions']:
            raise ValueError('Scheme references an unknown baseline version')
        if data['versions'][identity]['sha256'] != manifest['baseline_sha256']:
            raise ValueError('Scheme baseline checksum differs from its version')
    directory = (root / 'augmentation-archives' / data['versions'][identity]['directory']).resolve()
    if root.resolve() / 'augmentation-archives' not in directory.parents:
        raise ValueError('Baseline directory is outside the forecast archive')
    return directory


def baseline_identity(root, manifest=None):
    data = registry(root)
    if manifest is None:
        return data['current']
    identity = manifest.get('baseline_id')
    if identity is None:
        identity = next((key for key, item in data['versions'].items()
                         if item['sha256'] == manifest['baseline_sha256']), None)
    if identity not in data['versions'] or data['versions'][identity]['sha256'] != manifest['baseline_sha256']:
        raise ValueError('Unknown or inconsistent baseline provenance')
    return identity


def semantic_fingerprint(filename, run_code):
    """Hash logical series, ignoring DSS layout/calendar blocks and missing sentinels.

    Includes reservoir/river outputs, local minimum rules, WY type and all
    hydrologic input series. Excludes prepared augmentation and other run codes.
    No numerical tolerance: any finite value, timestamp, unit, or type change
    counts. Existing gaps are represented, never filled or interpolated.
    """
    from pydsstools.heclib.dss import HecDss
    from plot_rts_forecast import unit_key
    keys = {}
    output_f = re.compile(r'^C:\d+\|' + re.escape(run_code) + '$', re.I)
    parameters = {'FLOW', 'FLOW-IN', 'FLOW-OUT', 'FLOW-UNREG', 'FLOW-SPEC',
                  'STOR', 'STOR-MAF', 'ELEV', 'ELEVATION', 'ELEV-FOREBAY',
                  'PRECIP', 'PRECIP-INC', 'TEMP', 'TEMPERATURE', 'SWE'}
    with HecDss.Open(str(filename)) as dss:
        for path in dss.getPathnameList('/*/*/*/*/*/*/'):
            # Preserve blank pathname parts, including the usually blank A part.
            parts = str(path).split('/')[1:-1]
            if len(parts) != 6:
                raise ValueError('Malformed DSS pathname: ' + str(path))
            a, b, c, _, e, f = parts
            if c.upper() not in parameters and not f.upper().endswith('|RULE CURVE') and f.upper() != 'RULE CURVE':
                continue
            if 'EXTERNALFLOWAUG' in c.upper():
                continue
            # Input ensemble F parts may be blank or end in | / |RULE CURVE.
            # Only exact run-code matches are accepted as simulation outputs.
            if re.search(r'\|[A-Z]\d+$', f, re.I) and not output_f.fullmatch(f):
                continue
            logical = '/{}/{}/{}//{}/{}/'.format(a, b, c, e, f)
            key = logical.upper()
            keys.setdefault(key, logical)
        if not keys:
            raise ValueError('No hydrologic time series found for baseline comparison')
        records = {}
        has_elevation = has_outflow = False
        print('Comparing hydrologic series:', len(keys), str(filename), flush=True)
        for number, (key, logical) in enumerate(sorted(keys.items()), 1):
            if number % 100 == 0:
                print('Compared series:', number, '/', len(keys), flush=True)
            record = dss.read_ts(logical, trim_missing=True)
            times = pd.DatetimeIndex(record.pytimes)
            values = np.ma.asarray(record.values, dtype=float).filled(np.nan)
            if len(times) != len(values) or not len(values) or times.has_duplicates or times.hasnans:
                raise ValueError('Empty or ambiguous baseline time series: ' + logical)
            order = np.argsort(times.asi8)
            values = values[order].copy()
            values[~np.isfinite(values) | (np.abs(values) > 1e30)] = np.nan
            values[values == 0] = 0.0
            metadata = [key, unit_key(record.units), str(getattr(record, 'type', '')).strip().upper(),
                        [time.isoformat() for time in times[order]]]
            digest = hashlib.sha256(json.dumps(metadata, separators=(',', ':')).encode('utf-8'))
            # Explicit marker for missing values makes NaN payloads irrelevant.
            digest.update(np.isnan(values).astype('u1').tobytes())
            digest.update(np.nan_to_num(values, nan=0).astype('<f8').tobytes())
            records[key] = digest.hexdigest()
            parts = logical.split('/')[1:-1]
            if output_f.fullmatch(parts[5]):
                has_elevation |= parts[2].upper() in ('ELEV', 'ELEVATION') and np.isfinite(values).any()
                has_outflow |= parts[2].upper() == 'FLOW-OUT' and np.isfinite(values).any()
        if not has_elevation or not has_outflow:
            raise ValueError('Computed baseline elevation and outflow records are required')
    digest = hashlib.sha256(json.dumps(records, sort_keys=True).encode('utf-8')).hexdigest()
    return {'sha256': digest, 'records': records}


def disable(root, token):
    marker = Path(root) / 'rts-augmentation-active.json'
    if marker.exists():
        marker.rename(Path(root) / ('rts-augmentation-disabled-' + token + '.json'))


def replace_live(root, source, reason):
    root = Path(root)
    live = root / 'forecast.dss'
    token = uuid.uuid4().hex
    backup = root / ('forecast.before-' + reason + '-' + token + '.dss')
    original = digest_file(live) if live.exists() else None
    if original is not None:
        shutil.copy2(live, backup)
        if digest_file(backup) != original or digest_file(live) != original:
            raise ValueError('Live forecast changed during backup')
    candidate = root / ('forecast.' + reason + '-pending-' + token + '.dss')
    shutil.copy2(source, candidate)
    if digest_file(candidate) != digest_file(source):
        raise ValueError('Baseline copy verification failed')
    if original is not None and digest_file(live) != original:
        raise ValueError('Live forecast changed during staging')
    disable(root, token)
    os.replace(candidate, live)
    return str(backup) if original is not None else None


def load_baseline(root, context, run_code):
    data = registry(root)
    identity = data['current']
    if identity is None:
        raise ValueError('No saved baseline. Compute unaugmented, then Save as baseline first.')
    version = data['versions'][identity]
    if version['run_code'] != run_code:
        raise ValueError('Baseline belongs to a different run code')
    saved_context = version.get('context')
    scope = ('forecast_name', 'run_name', 'timezone', 'lookback', 'start', 'end')
    if saved_context is not None and any(saved_context.get(key) != context.get(key) for key in scope):
        raise ValueError('Forecast window differs from the saved baseline. Use a new forecast for different dates or extracted inputs.')
    source = baseline_directory(root) / 'forecast.dss'
    if digest_file(source) != version['sha256']:
        raise ValueError('Baseline checksum mismatch')
    backup = replace_live(root, source, 'baseline')
    atomic_json(Path(root) / 'augmentation-archives/baseline-edit-session.json',
                {'baseline_id': identity, 'context': context, 'run_code': run_code})
    event(root, 'baseline-loaded', baseline_id=identity, backup=backup)
    print('Loaded baseline:', identity, 'Augmentation disabled.', flush=True)
    print('Make model changes and compute in RTS; then Save as baseline.', flush=True)


def save_baseline(root, context, run_code, fingerprint=semantic_fingerprint):
    root = Path(root)
    archive = root / 'augmentation-archives'
    if (root / 'rts-augmentation-active.json').exists():
        raise ValueError('Augmentation is active. Load baseline and compute unaugmented before saving.')
    data = registry(root)
    current = data['current']
    session_path = archive / 'baseline-edit-session.json'
    if current:
        if not session_path.exists():
            raise ValueError('Load baseline first, then compute unaugmented and Save as baseline.')
        session = json.loads(session_path.read_text())
        if session['baseline_id'] != current or session['run_code'] != run_code or session['context'] != context:
            raise ValueError('Baseline edit session does not match the current baseline, forecast window, or run code')
        if data['versions'][current]['run_code'] != run_code:
            raise ValueError('Cannot change baseline run code within this forecast')
    archive.mkdir(exist_ok=True)
    pending = archive / ('baseline-pending-' + uuid.uuid4().hex)
    pending.mkdir()
    live = root / 'forecast.dss'
    try:
        shutil.copy2(live, pending / 'forecast.dss')
        snapshot_hash = digest_file(pending / 'forecast.dss')
        if snapshot_hash != digest_file(live):
            raise ValueError('Live forecast changed during capture')
        candidate_fp = fingerprint(pending / 'forecast.dss', run_code)
        changed_records = []
        if current:
            old = data['versions'][current]
            source = baseline_directory(root)
            if digest_file(source / 'forecast.dss') != old['sha256']:
                raise ValueError('Saved baseline checksum mismatch')
            old_fp = old.get('fingerprint') or fingerprint(source / 'forecast.dss', run_code)
            old['fingerprint'] = old_fp
            missing = set(old_fp['records']) - set(candidate_fp['records'])
            if missing:
                raise ValueError('Baseline capture lost {} previously archived series; inspect compute before saving'.format(len(missing)))
            if snapshot_hash != digest_file(live):
                raise ValueError('Live forecast changed during comparison; finish compute first')
            if old_fp['sha256'] == candidate_fp['sha256']:
                atomic_json(archive / 'baseline-versions.json', data)
                event(root, 'baseline-save-unchanged', baseline_id=current,
                      captured_sha256=snapshot_hash, compute_status='user-confirmed-not-verified')
                print('Baseline results unchanged. Keeping', current, flush=True)
                return current, False
            changed_records = [key for key in sorted(set(old_fp['records']) | set(candidate_fp['records']))
                               if old_fp['records'].get(key) != candidate_fp['records'].get(key)]
            # Preserve legacy ancillary files for existing CLI consumers.
            for path in source.iterdir():
                if path.is_file() and path.name not in ('forecast.dss', 'manifest.json'):
                    shutil.copy2(path, pending / path.name)
        identity = 'baseline-{:04d}'.format(len(data['versions']) + 1)
        destination = archive / ('baseline' if current is None else identity)
        if destination.exists():
            raise FileExistsError(destination)
        version = {'directory': destination.name, 'sha256': snapshot_hash,
                   'run_code': run_code, 'fingerprint': candidate_fp, 'context': context,
                   'created_utc': datetime.now(timezone.utc).isoformat()}
        atomic_json(pending / 'manifest.json', {'sha256': snapshot_hash, 'forecast_root': str(root),
                    'run_code': run_code, 'baseline_id': identity})
        if snapshot_hash != digest_file(live):
            raise ValueError('Live forecast changed during comparison; finish compute first')
        pending.rename(destination)
        data['versions'][identity] = version
        data['current'] = identity
        atomic_json(archive / 'baseline-versions.json', data)
        atomic_json(archive / 'baseline-context.json', context)
        atomic_json(session_path, {'baseline_id': identity, 'context': context, 'run_code': run_code})
        event(root, 'baseline-saved', baseline_id=identity, previous_baseline=current,
              changed_records=changed_records, compute_status='user-confirmed-not-verified')
        write_archive_index(root)
        print('Saved baseline:', identity, flush=True)
        if current:
            print('Older augmented results are now labelled Previous baseline; their original pairings remain available.', flush=True)
        return identity, True
    finally:
        if pending.exists():
            shutil.rmtree(pending)


def result_directory(root, folder):
    archive = (Path(root) / 'augmentation-archives').resolve()
    requested = Path(folder)
    if requested.is_symlink() or requested.parent.is_symlink():
        raise ValueError('Invalid result archive link')
    folder = requested.resolve()
    if folder.parent.parent != archive or not folder.name.startswith('results-') or not (folder / 'capture.json').is_file():
        raise ValueError('Choose an archived results-* folder inside a scheme, not a baseline or scheme folder')
    if (folder / 'FAILED.txt').exists():
        raise ValueError('Invalid or failed result archive')
    scheme = json.loads((folder.parent / 'manifest.json').read_text())
    capture = json.loads((folder / 'capture.json').read_text())
    if capture['scheme'] != scheme['scheme'] or capture['baseline_sha256'] != scheme['baseline_sha256']:
        raise ValueError('Result provenance differs from its scheme')
    baseline_directory(root, scheme)
    return folder


def write_archive_index(root):
    root = Path(root)
    archive = root / 'augmentation-archives'
    data = registry(root)
    rows = []
    for capture_path in sorted(archive.glob('*/results-*/capture.json')):
        if (capture_path.parent / 'FAILED.txt').exists():
            continue
        capture = json.loads(capture_path.read_text())
        identity = baseline_identity(root, capture)
        rows.append({'directory': str(capture_path.parent), 'scheme': capture['scheme'],
                     'captured_utc': capture.get('captured_utc'), 'baseline_id': identity,
                     'baseline_status': 'Current baseline' if identity == data['current'] else 'Previous baseline'})
    atomic_json(archive / 'archive-index.json', {'current_baseline': data['current'], 'results': rows})
    return rows


def delete_result(root, folder):
    folder = result_directory(root, folder)
    event(root, 'result-delete-requested', directory=str(folder),
          capture=json.loads((folder / 'capture.json').read_text()))
    shutil.rmtree(folder)
    event(root, 'result-deleted', directory=str(folder))
    write_archive_index(root)
    print('Deleted archived result and its plots:', folder, flush=True)
    print('Baseline, scheme configuration, and action history retained.', flush=True)
