"""Disposable, verified arrays for immutable archived RTS DSS runs.

DSS remains the source archive. Cache only logical computed series used by
plots and augmentation; never search for absent rule curves or fill data gaps.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from time import perf_counter
from types import SimpleNamespace

import numpy as np
import pandas as pd

from baseline_versions import digest_file

SCHEMA = 1
PARAMETERS = {'ELEV', 'ELEVATION', 'FLOW', 'FLOW-IN', 'FLOW-OUT',
              'STOR', 'STOR-MAF', 'FLOW-SPEC'}


def logical_path(path):
    parts = str(path).split('/')
    if len(parts) != 8:
        raise ValueError('Malformed DSS pathname: ' + str(path))
    parts[4] = ''
    return '/'.join(parts)


def is_archived(filename):
    return 'augmentation-archives' in Path(filename).parts


class CachedRun:
    def __init__(self, directory, metadata):
        self.metadata = metadata
        self.arrays = np.load(Path(directory) / 'series.npz', allow_pickle=False)
        self.records = {}
    def __enter__(self):
        return self
    def __exit__(self, *args):
        self.arrays.close()
    def getPathnameList(self, pattern):
        return [item['pathname'] for item in self.metadata['records'].values()]
    def read_ts(self, path, **kwargs):
        key = logical_path(path).upper()
        item = self.metadata['records'].get(key)
        if item is None:
            raise ValueError('Required record is absent from the archived run: ' + path)
        if 'error' in item:
            raise ValueError('Archived record could not be cached: ' + item['error'])
        if key not in self.records:
            times = pd.DatetimeIndex(self.arrays[item['array'] + '_times'])
            if item['timezone']:
                times = times.tz_localize('UTC').tz_convert(item['timezone'])
            self.records[key] = SimpleNamespace(values=self.arrays[item['array'] + '_values'],
                pytimes=times, units=item['units'], type=item['type'])
        record = self.records[key]
        # Return independent values: plotting cleans missing sentinels in place.
        return SimpleNamespace(values=record.values.copy(), pytimes=record.pytimes,
                               units=record.units, type=record.type)


def open_cached_run(filename, run_code, expected_sha256=None):
    """Rebuild absent/stale/corrupt derived caches, never alter the source DSS."""
    filename = Path(filename)
    if not re.fullmatch(r'[A-Za-z]\d+', run_code):
        raise ValueError('Invalid archived run code')
    if not is_archived(filename):
        raise ValueError('Data caches are restricted to archived runs')
    started = perf_counter()
    source_hash = digest_file(filename)
    if expected_sha256 and source_hash != expected_sha256:
        raise ValueError('Archived DSS checksum mismatch')
    directory = filename.parent / ('run-data-cache-' + run_code.upper())
    try:
        metadata = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
        if (metadata['schema'] == SCHEMA and metadata['source_sha256'] == source_hash
                and metadata['run_code'] == run_code.upper()
                and digest_file(directory / 'series.npz') == metadata['arrays_sha256']):
            print('Reusing archived data cache:', directory, '({:.2f}s validation)'.format(perf_counter() - started), flush=True)
            return CachedRun(directory, metadata)
    except (OSError, ValueError, KeyError):
        pass
    from pydsstools.heclib.dss import HecDss
    pending = Path(tempfile.mkdtemp(prefix='run-data-pending-', dir=str(filename.parent)))
    try:
        arrays, records, coverage = {}, {}, {}
        from plot_rts_forecast import target_record
        with HecDss.Open(str(filename)) as dss:
            paths = {}
            for path in dss.getPathnameList('/*/*/*/*/*/*/'):
                logical = logical_path(path)
                parts = logical.split('/')
                if parts[3].upper() in PARAMETERS and re.fullmatch(r'C:\d{6}\|' + re.escape(run_code), parts[6], re.I):
                    paths.setdefault(logical.upper(), logical)
            for number, (key, path) in enumerate(sorted(paths.items())):
                try:
                    record = dss.read_ts(path, trim_missing=True)
                    times = pd.DatetimeIndex(record.pytimes)
                    values = np.ma.asarray(record.values, dtype=float).filled(np.nan)
                    if len(times) != len(values) or times.hasnans or times.has_duplicates or not len(times):
                        raise ValueError('Empty series, invalid timestamps, or duplicate timestamps')
                    # pandas can retain microsecond-resolution input indexes;
                    # store an explicit nanosecond representation for round trips.
                    times_ns = times.to_numpy(dtype='datetime64[ns]').astype('int64')
                    order = np.argsort(times_ns)
                    array = 'record_' + str(number)
                    arrays[array + '_times'] = times_ns[order]
                    arrays[array + '_values'] = values[order]
                    records[key] = {'pathname': path, 'array': array, 'units': str(record.units),
                                    'type': str(getattr(record, 'type', '')),
                                    'timezone': str(times.tz) if times.tz is not None else None}
                    valid = np.isfinite(values[order]) & (np.abs(values[order]) <= 1e30)
                    if target_record(path.split('/')) and valid.any():
                        member = int(path.split('/')[6].split('|')[0][2:])
                        finite_times = times[order][valid]
                        coverage.setdefault(str(member), []).append([finite_times[0].isoformat(), finite_times[-1].isoformat()])
                except Exception as exc:
                    records[key] = {'pathname': path, 'error': str(exc)}
                if (number + 1) % 100 == 0:
                    print('Cached series:', number + 1, '/', len(paths), flush=True)
        if not records:
            raise ValueError('No computed records found for archived run ' + run_code)
        np.savez_compressed(pending / 'series.npz', **arrays)
        metadata = {'schema': SCHEMA, 'source_sha256': source_hash, 'run_code': run_code.upper(),
                    'created_utc': datetime.now(timezone.utc).isoformat(), 'records': records, 'coverage': coverage,
                    'arrays_sha256': digest_file(pending / 'series.npz')}
        (pending / 'manifest.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
        if digest_file(filename) != source_hash:
            raise ValueError('Archived DSS changed while building cache')
        if directory.exists():
            shutil.rmtree(directory)
        os.replace(pending, directory)
        errors = sum('error' in item for item in records.values())
        print('Built archived data cache:', len(records), 'series,', errors, 'record errors in {:.2f}s'.format(perf_counter() - started), flush=True)
        return CachedRun(directory, metadata)
    finally:
        if pending.exists():
            shutil.rmtree(pending)
