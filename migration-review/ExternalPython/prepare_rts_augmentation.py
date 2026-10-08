"""Prepare a named RTS augmentation scheme from an immutable baseline copy.

No live DSS records or rule switches are changed. Calculation functions are
loaded from the maintained legacy script without executing its top-level run.
"""
import argparse
import ast
import csv
import datetime
import hashlib
import json
from pathlib import Path
import pickle
import shutil
import types
import uuid

import numpy as np
import pandas as pd

from augmentation_mapping import minimum_path


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def load_functions(source, namespace):
    # Only function definitions: importing the old module would run its entire
    # standalone compute against CONFIG.SIM_NAME and open simulation.dss.
    tree = ast.parse(source.read_text(encoding='utf-8-sig'))
    module = ast.Module(body=[node for node in tree.body if isinstance(node, ast.FunctionDef)], type_ignores=[])
    exec(compile(module, str(source), 'exec'), namespace)
    return types.SimpleNamespace(**namespace)


def read_config(path):
    # Excel-style comment rows may contain commas followed by empty cells.
    # pandas comment='#' can retain their suffix as an apparent header.
    # Locate the actual Variable header using CSV parsing, not line splitting.
    with open(path, encoding='utf-8-sig', newline='') as handle:
        rows = list(csv.reader(handle))
    header_index = next((i for i, row in enumerate(rows)
                         if row and row[0].strip() == 'Variable'), None)
    if header_index is None:
        raise ValueError('No Variable header found in ' + str(path))
    header = [cell.strip() for cell in rows[header_index]]
    while header and not header[-1]:
        header.pop()
    if len(set(header)) != len(header) or any(not cell for cell in header):
        raise ValueError('Empty or duplicate configuration column names')
    records = []
    for row in rows[header_index + 1:]:
        if not row or not row[0].strip() or row[0].lstrip().startswith('#'):
            continue
        if any(cell.strip() for cell in row[len(header):]):
            raise ValueError('Unexpected extra configuration cells: ' + row[0])
        records.append((row[:len(header)] + [''] * len(header))[:len(header)])
    table = pd.DataFrame(records, columns=header).fillna('')
    table['Variable'] = table['Variable'].str.strip()
    if table['Variable'].duplicated().any():
        raise ValueError('Duplicate configuration variables')
    table = table.set_index('Variable')
    aliases, flags, floors, limits, travel = {}, {}, {}, {}, {}
    for name in table.columns:
        aliases[name] = table.loc['Abbreviation', name].strip()
        flags[name] = {}
        for gauge in ('Salem', 'Albany'):
            text = table.loc['Supports' + gauge, name].strip().upper()
            if text not in ('TRUE', 'FALSE'):
                raise ValueError('Invalid Supports{} for {}'.format(gauge, name))
            flags[name][gauge] = text == 'TRUE'
        floors[name] = float(table.loc['MinConStor', name])
        limits[name] = float(table.loc['MaxRelease', name])
        travel[name] = int(table.loc['TravelTimeDays', name])
        if not np.isfinite(floors[name]) or not np.isfinite(limits[name]) or floors[name] < 0 or limits[name] < 0 or travel[name] < 0:
            raise ValueError('Invalid floor, release limit, or travel time for ' + name)
    if len(set(aliases.values())) != len(aliases):
        raise ValueError('Duplicate abbreviations')
    # Current SV applies only to SupportsSalem reservoirs. Do not prepare a
    # scheme that it cannot faithfully consume.
    if any(flags[name]['Salem'] != flags[name]['Albany'] for name in flags):
        raise ValueError('Current model requires identical Salem/Albany supporting reservoirs')
    selected = [name for name in aliases if flags[name]['Salem']]
    if not selected or 'Hills Creek' in selected or 'Lookout Point' not in selected:
        raise ValueError('This version requires Lookout Point/Hills Creek combined, with Hills Creek not independently selected')
    return aliases, flags, floors, limits, travel, selected


def read_series(dss, path, units):
    record = dss.read_ts(path, trim_missing=True)
    actual_units = str(record.units).strip().upper()
    if actual_units not in units:
        raise ValueError('{}: unexpected units {}'.format(path, actual_units))
    series = pd.Series(np.asarray(record.values, dtype=float), index=pd.DatetimeIndex(record.pytimes)).sort_index()
    if series.empty or series.index.has_duplicates:
        raise ValueError('Empty series or duplicate timestamps: ' + path)
    return series


def read_water_year_type(dss, path, mode):
    if mode == 'fixed-abundant':
        # The existing ALL_ABUNDANT input is an explicit constant code of 4,
        # exported by this state variable with a storage unit label. It is not
        # a physical acre-foot volume. Require an explicit mode and verify it.
        series = read_series(dss, path, {'MAF', 'STOR-MAF', 'AC-FT', 'ACRE-FT', 'AF', 'ACRE-FEET'})
        if not (series.to_numpy(dtype=float) == 4.0).all():
            raise ValueError('fixed-abundant requires every water-year-type value to equal 4; inspect the model input')
        return series
    return read_series(dss, path, {'MAF', 'STOR-MAF'})


def validate_daily(data, start, end):
    data = data.reindex(pd.date_range(start, end, freq='D'))
    values = data.to_numpy(dtype=float)
    invalid = ~np.isfinite(values) | (np.abs(values) > 1e30)
    if invalid.any():
        columns = list(data.columns[invalid.any(axis=0)])
        raise ValueError('Missing/invalid daily inputs: ' + ', '.join(columns))
    return data


def calculate(data, calc, aliases, flags, floors, travel, selected, year, end, forecast_days, median, targets):
    data = data.copy()
    data['LOP_stor'] += data['HCR_stor']
    data['LOP_inflow'] += data['HCR_inflow'] - data['HCR_outflow']
    combined_floors = dict(floors)
    combined_floors['Lookout Point'] += combined_floors['Hills Creek']
    data = calc.compute_net_inflows(data, aliases)
    # The helper already subtracts storage floors. No second subtraction.
    usable = calc.calculate_storage_on_date(data, (4, 1), combined_floors)
    if year not in usable.index:
        raise ValueError('April 1 storage absent')
    period_end = (end.month, end.day)
    pivots = calc.create_net_inflow_pivot_tables(data, aliases, (4, 1), period_end)
    short = calc.create_short_forecast_volume_pivot_tables(pivots, forecast_days, 86400 / 43560.0)
    for name in selected:
        alias = aliases[name]
        if alias not in median or median[alias].empty:
            raise ValueError('Missing median remaining volume for ' + name)
        expected = short[alias].index
        values = median[alias].reindex(expected)
        if not np.isfinite(values.to_numpy(dtype=float)).all():
            raise ValueError('Incomplete median volume schedule for ' + name)
    available = calc.create_total_available_volume_pivot_tables(short, forecast_days, usable, median)
    for gauge, prefix in [('Salem', 'SLM'), ('Albany', 'ALB')]:
        data = calc.create_gauge_minflow_ts(targets[gauge], data, prefix)
        proportions = calc.create_augmentation_proportion_tables(available,
            {name: flags[name][gauge] for name in aliases}, aliases)
        deficits = calc.create_gauge_deficit_pivot_table(data, prefix, (4, 1), period_end)
        # Preserve legacy signed deficit behavior; do not silently redesign it.
        flows = calc.create_agumentation_flow_pivot_tables(proportions, deficits)
        for alias, pivot in flows.items():
            series = calc.melt_pivot_to_series(pivot, alias + '_augmentation_' + prefix + '_flow',
                data.index[0], data.index[-1])
            data[series.name] = series
        for name in selected:
            alias = aliases[name]
            delay = pd.Timedelta(days=travel[name])
            release_start = pd.Timestamp(year=year, month=4, day=1) - delay
            release_end = end - delay
            column = alias + '_min_flow_with_aug_' + prefix
            data[column] = 0.0
            mask = (data.index >= release_start) & (data.index <= release_end)
            # Only require future allocations inside the declared target window.
            # Outside that window augmentation is zero, not an invented extension.
            incoming = data[alias + '_augmentation_' + prefix + '_flow'].reindex(data.index[mask] + delay)
            if not np.isfinite(incoming.to_numpy(dtype=float)).all():
                raise ValueError('Missing travel-shifted allocation for ' + name)
            values = data.loc[mask, alias + '_outflow'].to_numpy() + incoming.to_numpy()
            data.loc[mask, column] = np.clip(values, 0, calc.MAX_FLOW_DICT[name])
    for name in selected:
        alias = aliases[name]
        data[alias + '_min_flow_with_aug'] = data[[alias + '_min_flow_with_aug_SLM',
                                                  alias + '_min_flow_with_aug_ALB']].max(axis=1)
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--forecast-root', required=True)
    parser.add_argument('--scheme', required=True)
    parser.add_argument('--members', default='1981-1991,3000-3002')
    parser.add_argument('--run-code', default='C0')
    parser.add_argument('--season-year', required=True, type=int)
    parser.add_argument('--season-end', required=True, help='Explicit ISO date; no invented extension of baseline coverage')
    parser.add_argument('--forecast-days', type=int, default=10)
    parser.add_argument('--wy-type-mode', choices=('storage-maf', 'fixed-abundant'), default='storage-maf',
                        help='fixed-abundant explicitly accepts the constant 4 input; never converts it as a physical volume')
    args = parser.parse_args()
    if not args.scheme or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in args.scheme):
        raise ValueError('Scheme name must contain only letters, numbers, underscore, or hyphen')
    if args.forecast_days < 1:
        raise ValueError('forecast-days must be positive')
    members = set()
    for item in args.members.split(','):
        bounds = item.split('-')
        members.update(range(int(bounds[0]), int(bounds[-1]) + 1))
    root = Path(args.forecast_root).resolve()
    live = root / 'forecast.dss'
    if not live.is_file():
        raise FileNotFoundError(live)
    start = pd.Timestamp('{}-04-01'.format(args.season_year))
    end = pd.Timestamp(args.season_end)
    if end.year != args.season_year or not start <= end <= pd.Timestamp('{}-10-31'.format(args.season_year)):
        raise ValueError('Season must be April 1 through an end date no later than October 31 in the same year')
    scripts = Path(__file__).resolve().parent
    archives = root / 'augmentation-archives'
    baseline = archives / 'baseline'
    scheme = archives / args.scheme
    if scheme.exists():
        raise FileExistsError('Scheme already exists; use a new name: ' + str(scheme))
    config_paths = [scripts.parent / 'externalSVs' / name for name in
        ('MinFlowSalemAlbanyConfig.csv', 'MinFlowSalem_2008BiOp.csv', 'MinFlowAlbany_2008BiOp.csv')]
    config_paths += [scripts / 'median_remaining_by_day.pkl', scripts / 'MainstemAugmentation.py']
    for path in config_paths:
        if not path.is_file():
            raise FileNotFoundError(path)
    aliases, flags, floors, limits, travel, selected = read_config(config_paths[0])
    if not baseline.exists():
        if (root / 'rts-augmentation-active.json').exists():
            raise ValueError('Cannot capture baseline while augmentation is active')
        # Create atomically; incomplete copies are never treated as a baseline.
        archives.mkdir(exist_ok=True)
        temporary = archives / ('baseline-pending-' + uuid.uuid4().hex)
        temporary.mkdir()
        shutil.copy2(live, temporary / 'forecast.dss')
        if sha256(live) != sha256(temporary / 'forecast.dss'):
            raise ValueError('Baseline changed during copy; close RTS/DSSVue before retrying')
        for path in config_paths:
            shutil.copy2(path, temporary / path.name)
        (temporary / 'manifest.json').write_text(json.dumps({'sha256': sha256(live),
            'forecast_root': str(root), 'run_code': args.run_code}, indent=2))
        temporary.rename(baseline)
    base_manifest = json.loads((baseline / 'manifest.json').read_text())
    source = baseline / 'forecast.dss'
    if base_manifest['run_code'] != args.run_code or sha256(source) != base_manifest['sha256']:
        raise ValueError('Baseline run code or checksum mismatch')
    scheme.mkdir()
    for path in config_paths:
        shutil.copy2(path, scheme / path.name)
    namespace = {'pd': pd, 'np': np, 'datetime': datetime, 'timedelta': datetime.timedelta,
                 'Path': Path, 'ALIAS_DICT': aliases, 'MAX_FLOW_DICT': limits}
    calc = load_functions(scheme / 'MainstemAugmentation.py', namespace)
    targets = {gauge: calc.load_wy_type_flow_dict(scheme / ('MinFlow' + gauge + '_2008BiOp.csv'))
               for gauge in ('Salem', 'Albany')}
    # Trusted local watershed file; retained unchanged and hashed in manifest.
    with open(scheme / 'median_remaining_by_day.pkl', 'rb') as handle:
        median = pickle.load(handle)
    from pydsstools.heclib.dss import HecDss
    from pydsstools.core import TimeSeriesContainer
    paths_written = []
    output = scheme / 'augmentation.dss'
    stats = []
    try:
        with HecDss.Open(str(source)) as dss, HecDss.Open(str(output), version=7) as out:
            for member in sorted(members):
                fpart = 'C:{:06d}|{}'.format(member, args.run_code)
                series = {}
                needed = set(selected) | {'Hills Creek'}
                for name in needed:
                    alias = aliases[name]
                    for parameter, suffix in [('STOR', 'stor'), ('FLOW-IN', 'inflow'), ('FLOW-OUT', 'outflow')]:
                        path = '//{}-POOL/{}//1DAY/{}/'.format(name.upper(), parameter, fpart)
                        series[alias + '_' + suffix] = read_series(dss, path,
                            {'ACRE-FT', 'AC-FT', 'AF', 'ACRE-FEET'} if suffix == 'stor' else {'CFS'})
                    series[alias + '_minflow'] = read_series(dss, minimum_path(alias, member, args.run_code), {'CFS'})
                for prefix, name in [('SLM', 'SALEM'), ('ALB', 'ALBANY')]:
                    series[prefix + '_flow'] = read_series(dss,
                        '//WILLAMETTE_AT {}/FLOW//1DAY/{}/'.format(name, fpart), {'CFS'})
                series['WY_type'] = read_water_year_type(dss, '//WATERYEARTYPEVARIABLE/STOR-MAF//1DAY/{}/'.format(fpart), args.wy_type_mode)
                # Keep a common validated forecast span, and require the whole
                # requested seasonal window plus travel-time lead-in.
                first = max(s.index[0] for s in series.values())
                last = min(s.index[-1] for s in series.values())
                lead = start - pd.Timedelta(days=max(travel[name] for name in selected))
                if first > lead or last < end:
                    raise ValueError('Member {} lacks seasonal/lead-in coverage: {} to {}'.format(member, first, last))
                data = validate_daily(pd.DataFrame(series), first, last)
                data = calculate(data, calc, aliases, flags, floors, travel, selected,
                    args.season_year, end, args.forecast_days, median, targets)
                data.to_csv(scheme / ('member-{}.csv'.format(member)), index_label='forecast_local_datetime')
                records = [(name, aliases[name] + '_min_flow_with_aug') for name in selected]
                records += [('Salem', 'SLM_minflow'), ('Albany', 'ALB_minflow')]
                for name, column in records:
                    values = data[column].to_numpy(dtype=float)
                    if not np.isfinite(values).all() or (values < 0).any():
                        raise ValueError('Invalid calculated release/target: ' + column)
                    if name in selected and (values > limits[name] + 0.051).any():
                        raise ValueError('Release limit exceeded: ' + name)
                    tsc = TimeSeriesContainer()
                    tsc.pathname = '//{}/FLOW-MIN-EXTERNALFLOWAUG//1DAY/{}/'.format(name.upper(), fpart)
                    tsc.startDateTime = data.index[0].strftime('%d%b%Y %H%M').upper()
                    tsc.interval, tsc.numberValues = 1440, len(values)
                    tsc.units, tsc.type = 'CFS', 'PER-AVER'
                    tsc.values = np.round(values, 1)
                    out.put_ts(tsc)
                    paths_written.append(tsc.pathname)
                    stats.append({'member': member, 'location': name, 'maximum_cfs': float(values.max())})
                print('Prepared member:', member, flush=True)
        manifest = {'status': 'prepared-not-computed', 'scheme': args.scheme,
                    'forecast_root': str(root), 'run_code': args.run_code,
                    'members': sorted(members), 'season_start': str(start), 'season_end': str(end),
                    'baseline_sha256': base_manifest['sha256'], 'supporting_reservoirs': selected,
                    'paths': paths_written, 'augmentation_sha256': sha256(output),
                    'configuration_sha256': {p.name: sha256(scheme / p.name) for p in config_paths},
                    'forecast_days': args.forecast_days, 'summary': stats,
                    'wy_type_mode': args.wy_type_mode,
                    'notes': ['Storage floor subtracted once.', 'Signed deficits preserved from legacy method.',
                              'Season ends at explicitly requested date; no extrapolated October inputs.']}
        (scheme / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    except Exception:
        (scheme / 'FAILED.txt').write_text('Preparation failed. Do not load this partial scheme. Use a new scheme name after correcting inputs.')
        raise
    print('PREPARED ONLY:', scheme)
    print('Live forecast DSS and RTS rule settings unchanged. Do not recompute for augmentation until the RTS switch and scheme loading are installed.')


if __name__ == '__main__':
    main()
