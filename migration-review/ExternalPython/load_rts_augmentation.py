"""Load a prepared RTS scheme, or explicitly disable augmentation.

Close RTS forecast/DSSVue views before loading. Live DSS is backed up and a
complete candidate copy is prepared before replacement. No compute is started.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import uuid

from prepare_rts_augmentation import sha256
from baseline_versions import baseline_directory, baseline_identity, registry, event


def validate_manifest(root, scheme, manifest):
    if manifest['status'] != 'prepared-not-computed' or (scheme / 'FAILED.txt').exists():
        raise ValueError('Scheme is not a completed preparation')
    if Path(manifest['forecast_root']).resolve() != root.resolve():
        raise ValueError('Scheme belongs to a different forecast')
    if sha256(scheme / 'augmentation.dss') != manifest['augmentation_sha256']:
        raise ValueError('Scheme DSS checksum mismatch')
    baseline = baseline_directory(root, manifest) / 'forecast.dss'
    if sha256(baseline) != manifest['baseline_sha256']:
        raise ValueError('Baseline checksum mismatch')
    for name, digest in manifest['configuration_sha256'].items():
        if sha256(scheme / name) != digest:
            raise ValueError('Archived configuration changed: ' + name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--forecast-root', required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--scheme')
    mode.add_argument('--reset', action='store_true', help='Disable RTS augmentation; retained records are ignored')
    args = parser.parse_args()
    root = Path(args.forecast_root).resolve()
    marker = root / 'rts-augmentation-active.json'
    if args.reset:
        if marker.exists():
            marker.rename(root / ('rts-augmentation-disabled-' + uuid.uuid4().hex + '.json'))
        event(root, 'augmentation-disabled')
        print('Augmentation disabled. No DSS records changed. The RTS rule returns zero for augmentation on the next compute.')
        return
    if any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in args.scheme) or not args.scheme:
        raise ValueError('Invalid scheme name')
    scheme = root / 'augmentation-archives' / args.scheme
    manifest = json.loads((scheme / 'manifest.json').read_text())
    validate_manifest(root, scheme, manifest)
    identity = baseline_identity(root, manifest)
    if identity != registry(root)['current']:
        raise ValueError('Scheme belongs to a Previous baseline. Its results remain plottable; prepare a new named scheme against the current baseline before computing.')
    live = root / 'forecast.dss'
    token = uuid.uuid4().hex
    backup = root / ('forecast.before-augmentation-' + token + '.dss')
    candidate = root / ('forecast.augmentation-pending-' + token + '.dss')
    shutil.copy2(live, backup)
    if sha256(live) != sha256(backup):
        raise ValueError('Live DSS changed during backup; close the forecast and DSSVue')
    shutil.copy2(backup, candidate)
    from pydsstools.heclib.dss import HecDss
    from pydsstools.core import TimeSeriesContainer
    import numpy as np
    with HecDss.Open(str(scheme / 'augmentation.dss')) as source, HecDss.Open(str(candidate)) as target:
        for path in manifest['paths']:
            ts = source.read_ts(path, trim_missing=True)
            values = np.asarray(ts.values, dtype=float)
            if not len(values) or not np.isfinite(values).all() or (values < 0).any():
                raise ValueError('Invalid prepared record: ' + path)
            container = TimeSeriesContainer()
            container.pathname = path
            container.startDateTime = ts.pytimes[0].strftime('%d%b%Y %H%M').upper()
            container.numberValues, container.interval = len(values), 1440
            container.units, container.type, container.values = 'CFS', 'PER-AVER', values
            target.put_ts(container)
    # Replace only after all DSS handles have closed. If Windows holds a lock,
    # replacement fails, preserving live DSS and leaving the backup/candidate.
    if sha256(live) != sha256(backup):
        raise ValueError('Live DSS changed during staging; nothing replaced')
    active = dict(manifest)
    active['scheme_directory'] = str(scheme)
    marker_candidate = root / ('rts-augmentation-active-' + token + '.pending')
    marker_candidate.write_text(json.dumps(active, indent=2))
    # Disable any old scheme before replacement. If activation fails, the model
    # remains baseline-only rather than silently using the previous scheme.
    if marker.exists():
        marker.rename(root / ('rts-augmentation-disabled-' + token + '.json'))
    os.replace(candidate, live)
    os.replace(marker_candidate, marker)
    session = root / 'augmentation-archives/baseline-edit-session.json'
    if session.exists():
        session.unlink()
    event(root, 'scheme-loaded', scheme=args.scheme, baseline_id=identity, backup=str(backup))
    print('Loaded scheme:', args.scheme)
    print('Backup:', backup)
    print('Reopen the forecast and compute manually. Scheme covers members:', manifest['members'])


if __name__ == '__main__':
    main()
