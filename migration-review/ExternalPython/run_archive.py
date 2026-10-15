"""Primary, immutable compact run archives; legacy DSS snapshots remain readable."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

import numpy as np

from baseline_versions import digest_file

NAME = 'run-archive.json'


def is_compact(filename):
    return (Path(filename).parent / NAME).is_file()


def metadata(filename):
    directory = Path(filename).parent
    info = json.loads((directory / NAME).read_text(encoding='utf-8'))
    if info.get('format') != 'rts-compact-run' or info.get('schema') != 1:
        raise ValueError('Unsupported compact run archive')
    if digest_file(directory / 'series.npz') != info['arrays_sha256']:
        raise ValueError('Compact run arrays checksum mismatch; primary archive cannot be rebuilt')
    return info


def archive_digest(filename):
    if is_compact(filename):
        metadata(filename)
        return digest_file(Path(filename).parent / NAME)
    return digest_file(filename)


def open_archive(filename, run_code, expected_sha256=None):
    from run_data_cache import CachedRun
    info = metadata(filename)
    if info['run_code'] != run_code.upper():
        raise ValueError('Compact archive run code mismatch')
    if expected_sha256 and digest_file(Path(filename).parent / NAME) != expected_sha256:
        raise ValueError('Compact archive checksum mismatch')
    return CachedRun(Path(filename).parent, info)


def signature(filename):
    stat = Path(filename).stat()
    return (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


def capture_run(source, destination, run_code):
    """One catalog pass and one read per selected physical block; no DSS copy.

    Caller stages in a new directory and publishes it only on success. File stat
    checks detect normal concurrent writes, not adversarial preserved timestamps;
    operator confirmation that compute is finished remains required.
    """
    from pydsstools.heclib.dss import HecDss
    from baseline_versions import read_fingerprint_series
    from run_data_cache import needed_record, logical_path
    from plot_rts_forecast import target_record
    if not re.fullmatch(r'[A-Za-z]\d+', run_code):
        raise ValueError('Invalid run code')
    source, destination = Path(source), Path(destination)
    if any(destination.iterdir()):
        raise ValueError('Capture staging directory must be empty')
    before = signature(source)
    selected, arrays, records, contents = {}, {}, {}, {}
    matcher = re.compile(r'C:\d{6}\|' + re.escape(run_code), re.I)
    reads = 0
    with HecDss.Open(str(source)) as dss:
        for path in dss.getPathnameList('/*/*/*/*/*/*/'):
            path = str(path)
            parts = path.split('/')
            if len(parts) == 8 and needed_record(parts) and matcher.fullmatch(parts[6]):
                key = logical_path(path).upper()
                selected.setdefault(key, set()).add(path)
        for number, (key, paths) in enumerate(sorted(selected.items())):
            logical = logical_path(sorted(paths)[0])
            try:
                times, values, units, kind = read_fingerprint_series(dss, logical, paths)
                reads += len(paths)
                if not len(times) or not np.isfinite(values).any():
                    raise ValueError('Empty or wholly missing time series')
                times_ns = times.to_numpy(dtype='datetime64[ns]').astype('int64')
                array = 'record_' + str(number)
                arrays[array+'_times'], arrays[array+'_values'] = times_ns, values
                item = {'pathname': logical, 'array': array, 'units': units, 'type': kind,
                        'timezone': str(times.tz) if times.tz is not None else None}
                values_hash = hashlib.sha256(times_ns.astype('<i8').tobytes() + values.astype('<f8').tobytes()).hexdigest()
                contents[key] = dict(item, values_sha256=values_hash)
                records[key] = item
            except Exception as exc:
                # Optional cataloged rule/state outputs can be empty. Never
                # swallow failed pool/mainstem outputs or augmentation inputs.
                parameter = logical.split('/')[3].upper()
                if target_record(logical.split('/')) or parameter in ('STOR', 'FLOW-IN', 'FLOW-OUT'):
                    raise ValueError('Cannot archive required series '+logical+': '+str(exc)) from exc
                records[key] = {'pathname': logical, 'error': str(exc)}
                contents[key] = records[key]
            if (number+1) % 100 == 0:
                print('Archived selected series:', number+1, '/', len(selected), flush=True)
    if not records or not any(target_record(key.split('/')) for key in records):
        raise ValueError('No computed plot outputs found for selected run')
    if signature(source) != before:
        raise ValueError('Live DSS changed during capture; finish compute before archiving')
    np.savez_compressed(destination / 'series.npz', **arrays)
    info = {'format': 'rts-compact-run', 'schema': 1, 'run_code': run_code.upper(),
            'created_utc': datetime.now(timezone.utc).isoformat(), 'records': records,
            'source_signature': list(before), 'source_bytes': before[0],
            'content_sha256': hashlib.sha256(json.dumps(contents, sort_keys=True).encode()).hexdigest(),
            'arrays_sha256': digest_file(destination / 'series.npz')}
    if signature(source) != before:
        raise ValueError('Live DSS changed during capture; nothing published')
    (destination / NAME).write_text(json.dumps(info, indent=2), encoding='utf-8')
    digest = archive_digest(destination / 'forecast.dss')
    print('Compact archive:', len(records), 'selected series;', reads, 'DSS block reads;',
          (destination / 'series.npz').stat().st_size, 'compressed bytes. No DSS snapshot copied.', flush=True)
    return digest
