"""Read-only RTS augmentation input audit. Does not calculate or write releases."""
import argparse
from pathlib import Path
import re

import numpy as np
import pandas as pd

from augmentation_mapping import MINIMUM_LOCATIONS, minimum_path


def logical_outputs(paths, run_code, members):
    outputs = {}
    for path in paths:
        parts = path.split('/')
        if len(parts) != 8:
            continue
        match = re.fullmatch(r'C:(\d{6})\|' + re.escape(run_code), parts[6], re.I)
        if not match or int(match.group(1)) not in members:
            continue
        parts[4] = ''
        logical = '/'.join(parts)
        outputs.setdefault(int(match.group(1)), set()).add(logical)
    return outputs


def inspect_series(dss, path, start, end):
    record = dss.read_ts(path, trim_missing=True)
    series = pd.Series(np.asarray(record.values, dtype=float),
                       index=pd.DatetimeIndex(record.pytimes)).sort_index()
    if series.index.has_duplicates:
        raise ValueError('Duplicate timestamps')
    series = series.loc[start:end]
    if series.empty:
        raise ValueError('No values in requested season')
    bad = ~np.isfinite(series.to_numpy()) | (np.abs(series.to_numpy()) > 1e30)
    if bad.any():
        raise ValueError('{} missing/invalid values'.format(int(bad.sum())))
    if series.index[0] > start or series.index[-1] < end:
        raise ValueError('Coverage {} to {}'.format(series.index[0], series.index[-1]))
    if (series.index.to_series().diff().dropna() != pd.Timedelta(days=1)).any():
        raise ValueError('Not a continuous daily series')
    return len(series), record.units


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--forecast-root', required=True)
    parser.add_argument('--run-code', default='C0')
    parser.add_argument('--members', default='1981-1991,3000-3002')
    parser.add_argument('--season-year', type=int, required=True)
    parser.add_argument('--season-end', help='ISO date; default October 31')
    args = parser.parse_args()
    members = set()
    for item in args.members.split(','):
        bounds = item.strip().split('-')
        members.update(range(int(bounds[0]), int(bounds[-1]) + 1))
    start = pd.Timestamp('{}-04-01'.format(args.season_year))
    end = pd.Timestamp(args.season_end or '{}-10-31'.format(args.season_year))
    if end < start:
        raise ValueError('Season end precedes April 1')
    filename = Path(args.forecast_root) / 'forecast.dss'
    if not filename.is_file():
        raise FileNotFoundError(filename)
    from pydsstools.heclib.dss import HecDss
    failures = []
    print('READ ONLY:', filename, flush=True)
    print('Checking daily coverage:', start.date(), 'through', end.date(), flush=True)
    with HecDss.Open(str(filename)) as dss:
        paths = dss.getPathnameList('/*/*/*/*/*/*/')
        outputs = logical_outputs(paths, args.run_code, members)
        # Report naming once: the legacy calculator's rule/state-variable names
        # may differ from the imported network. No guessing or substitutions.
        exemplar = min(members)
        print('\nRULE / STATE VARIABLE CANDIDATES (member {}):'.format(exemplar))
        for path in sorted(outputs.get(exemplar, [])):
            parts = path.upper().split('/')
            if parts[3] in ('FLOW-MIN', 'FLOW-SPEC') or 'WATERYEAR' in parts[2] or 'WATER YEAR' in parts[2]:
                print(path)
        reservoirs = ('LOOKOUT POINT', 'HILLS CREEK', 'DETROIT', 'GREEN PETER',
                      'COUGAR', 'BLUE RIVER', 'FALL CREEK', 'DORENA', 'COTTAGE GROVE', 'FERN RIDGE')
        requirements = [(name + '-POOL', parameter) for name in reservoirs
                        for parameter in ('STOR', 'FLOW-IN', 'FLOW-OUT')]
        requirements += [('WILLAMETTE_AT SALEM', 'FLOW'), ('WILLAMETTE_AT ALBANY', 'FLOW'),
                         ('WATERYEARTYPEVARIABLE', 'STOR-MAF')]
        for member in sorted(members):
            passed = 0
            for location, parameter in requirements:
                matches = [p for p in outputs.get(member, [])
                           if p.upper().split('/')[2:4] == [location, parameter]
                           and p.upper().split('/')[5] == '1DAY']
                if len(matches) != 1:
                    failures.append((member, location, parameter, 'Expected one path, found {}'.format(len(matches))))
                    continue
                try:
                    inspect_series(dss, matches[0], start, end)
                    passed += 1
                except Exception as exc:
                    failures.append((member, location, parameter, str(exc)))
            print('Member {}: {}/{} core inputs pass'.format(member, passed, len(requirements)), flush=True)
            minimum_passed = 0
            available = {p.upper() for p in outputs.get(member, [])}
            for alias in sorted(MINIMUM_LOCATIONS):
                path = minimum_path(alias, member, args.run_code)
                if path.upper() not in available:
                    failures.append((member, alias + '_minflow', 'FLOW-SPEC', 'Missing ' + path))
                    continue
                try:
                    count, units = inspect_series(dss, path, start, end)
                    if str(units).strip().upper() != 'CFS':
                        raise ValueError('Expected CFS, found {}'.format(units))
                    minimum_passed += 1
                except Exception as exc:
                    failures.append((member, alias + '_minflow', 'FLOW-SPEC', str(exc)))
            print('Member {}: {}/{} Combined Min Trib inputs pass'.format(
                member, minimum_passed, len(MINIMUM_LOCATIONS)), flush=True)
    print('\nINPUT ISSUES:')
    for member, location, parameter, message in failures:
        print('{} | {} | {} | {}'.format(member, location, parameter, message))
    scripts = Path(__file__).resolve().parent
    print('\nCONFIGURATION FILES:')
    for path in [scripts / 'median_remaining_by_day.pkl'] + [scripts.parent / 'externalSVs' / name
                 for name in ('MinFlowSalemAlbanyConfig.csv', 'MinFlowSalem_2008BiOp.csv', 'MinFlowAlbany_2008BiOp.csv')]:
        print('{}: {}'.format('FOUND' if path.is_file() else 'MISSING', path))
        if not path.is_file():
            failures.append(('configuration', str(path), '', 'Missing'))
    print('\nGPR_minflow uses Foster-Combined Min Trib, preserving the legacy Foster requirement.')
    print('No DSS records changed. This check does not calculate or apply augmentation.')
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
