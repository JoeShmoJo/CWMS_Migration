"""Compare selected reservoir outflows and Salem flow; never write DSS records."""
import argparse
from collections import defaultdict
import csv
import math
from pathlib import Path
import re
import sys

import numpy as np
import pandas as pd

RESERVOIRS = ('Hills Creek', 'Lookout Point', 'Dexter', 'Fall Creek',
              'Cottage Grove', 'Dorena', 'Fern Ridge', 'Cougar', 'Blue River',
              'Green Peter', 'Foster', 'Detroit', 'Big Cliff')
LOCATIONS = RESERVOIRS + ('Willamette_at Salem',)


def normalize(value):
    return re.sub('[^A-Z0-9]', '', value.upper())


def groups(paths, members, run):
    lookup = {normalize(n+'-Pool'): n for n in RESERVOIRS}
    lookup[normalize('Willamette_at Salem')] = 'Willamette_at Salem'
    found = defaultdict(list)
    available = defaultdict(set)
    for path in paths:
        parts = str(path).split('/')[1:-1]
        if len(parts) != 6: continue
        a, b, c, d, e, f = parts
        location = lookup.get(normalize(b))
        if location is None: continue
        parameter = 'FLOW' if location == 'Willamette_at Salem' else 'FLOW-OUT'
        if c.upper() != parameter: continue
        match = re.fullmatch(r'C:(\d+)\|(.*)', f, re.I)
        if not match: continue
        member = int(match[1]); suffix = match[2]
        available[suffix].add(member)
        if member in members and suffix.upper() == run.upper():
            found[location, member].append(str(path))
    return found, available


def read_series(dss, paths):
    samples = {}; metadata = None
    for path in sorted(paths):
        record = dss.read_ts(path, trim_missing=True)
        times = getattr(record, 'pytimes', None)
        values = getattr(record, 'values', None)
        if times is None or values is None:
            raise ValueError('No timestamps/values: '+path)
        times = pd.DatetimeIndex(times)
        values = np.ma.asarray(values, dtype=float).filled(np.nan).copy()
        if len(times) != len(values) or not len(times) or times.hasnans or times.has_duplicates:
            raise ValueError('Empty or ambiguous block: '+path)
        parts = path.split('/')[1:-1]
        units = str(record.units).strip().upper()
        if units in ('FT3/S', 'FT^3/S', 'CFS'): units = 'CFS'
        current = (units, str(getattr(record, 'type', '')).strip().upper(),
                   parts[0].upper(), parts[4].upper())
        if metadata is not None and current != metadata:
            raise ValueError('Mixed units/type/A-part/interval in logical series')
        metadata = current
        values[~np.isfinite(values) | (np.abs(values) > 1e30) |
               np.isin(values, [-901., -902., -903.])] = np.nan
        for time, value in zip(times, values):
            if time in samples and np.isfinite(samples[time]):
                if np.isfinite(value) and samples[time] != value:
                    raise ValueError('Conflicting overlapping blocks at '+str(time))
                continue
            samples[time] = value
    series = pd.Series(samples, dtype=float).sort_index()
    return series, metadata


def compare_series(left, right, atol=0.):
    index = left.index.union(right.index).sort_values()
    x = left.reindex(index).to_numpy(); y = right.reindex(index).to_numpy()
    valid = np.isfinite(x) & np.isfinite(y)
    missing = ~valid
    delta = np.abs(x-y)
    different = valid & (delta > atol)
    return index, x, y, missing, different, float(delta[valid].max()) if valid.any() else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parallel', type=Path, required=True)
    parser.add_argument('--serial', type=Path, required=True)
    parser.add_argument('--members', default='1982-2024')
    parser.add_argument('--run-code', help='Exact F-part suffix after |; lists choices if omitted')
    parser.add_argument('--start', help='Optional ISO datetime, inclusive')
    parser.add_argument('--end', help='Optional ISO datetime, inclusive')
    parser.add_argument('--atol', type=float, default=0., help='Absolute tolerance; default exact')
    parser.add_argument('--report-dir', type=Path, required=True)
    args = parser.parse_args()
    if not math.isfinite(args.atol) or args.atol < 0: parser.error('atol must be finite and nonnegative')
    match = re.fullmatch(r'(\d+)-(\d+)', args.members)
    if not match or int(match[1]) > int(match[2]): parser.error('members must be FIRST-LAST')
    members = set(range(int(match[1]), int(match[2])+1))
    for path in (args.parallel, args.serial):
        if not path.is_file(): parser.error('DSS file missing: '+str(path))
    if args.parallel.resolve() == args.serial.resolve(): parser.error('Choose two different DSS files')
    start = pd.Timestamp(args.start) if args.start else None
    end = pd.Timestamp(args.end) if args.end else None
    if start is not None and end is not None and start > end: parser.error('start is after end')
    from pydsstools.heclib.dss import HecDss
    report = args.report_dir.resolve()
    # Fail rather than overwrite previous comparison evidence.
    if report.exists(): parser.error('Report directory already exists; choose a new name')
    report.mkdir(parents=True)
    rows = []; detail = []; timeline = {}; total_differences = 0
    with HecDss.Open(str(args.parallel.resolve())) as parallel, HecDss.Open(str(args.serial.resolve())) as serial:
        catalogs = [dss.getPathnameList('/*/*/*/*/*/*/') for dss in (parallel, serial)]
        grouped = [groups(paths, members, args.run_code or '') for paths in catalogs]
        common = sorted(set(grouped[0][1]) & set(grouped[1][1]))
        if not args.run_code:
            print('Available F-part run/trial suffixes (choose ONE with --run-code):')
            for run in common:
                shared = grouped[0][1][run] & grouped[1][1][run] & members
                print(' ', repr(run), ':', len(shared), 'selected members present in both catalogs')
            if not common: print('No common computed-flow run suffixes found.')
            report.rmdir()
            return 2
        if args.run_code.upper() not in {r.upper() for r in common}:
            print('Requested run/trial not found in BOTH files:',args.run_code)
            print('Available common suffixes:', ', '.join(repr(r) for r in common))
            report.rmdir()
            return 2
        for number, (location, member) in enumerate(
                ((n, m) for n in LOCATIONS for m in sorted(members)), 1):
            row = dict(location=location, member=member, status='ERROR', samples=0,
                       missing=0, differences=0, max_abs_difference='', first_time='', last_time='', note='')
            try:
                data = []
                for dss, (catalog, _), label in zip((parallel, serial), grouped, ('parallel','serial')):
                    paths = catalog.get((location,member))
                    if not paths: raise ValueError('Missing '+label+' series')
                    series, metadata = read_series(dss, paths)
                    if start is not None: series = series[series.index >= start]
                    if end is not None: series = series[series.index <= end]
                    if series.empty: raise ValueError('No '+label+' data in selected window')
                    data.append((series, metadata))
                if data[0][1] != data[1][1]: raise ValueError('Units/type/A-part/interval differ between files')
                index, x, y, missing, different, maximum = compare_series(data[0][0],data[1][0],args.atol)
                row.update(samples=len(index), missing=int(missing.sum()), differences=int(different.sum()),
                           max_abs_difference=maximum, first_time=str(index[0]), last_time=str(index[-1]))
                row['status'] = 'MATCH' if not missing.any() and not different.any() else 'DIFFERENT'
                timeline[location,member] = index
                total_differences += int(different.sum())
                for i in np.flatnonzero(missing | different):
                    if len(detail) < 2000:
                        detail.append(dict(location=location,member=member,time=str(index[i]),
                                           parallel=x[i],serial=y[i],reason='missing' if missing[i] else 'value'))
            except Exception as exc:
                row['note'] = str(exc)
            rows.append(row)
            if number % 50 == 0: print('Compared',number,'/',len(LOCATIONS)*len(members),flush=True)
    # Equal truncation of just one member must not produce a clean comparison.
    if timeline:
        union = next(iter(timeline.values()))
        for index in timeline.values(): union = union.union(index)
        # These standalone simulation comparisons use daily outputs.
        if all(str(path).split('/')[5].upper() == '1DAY'
               for catalog, _ in grouped for paths in catalog.values() for path in paths):
            union = pd.date_range(start if start is not None else union.min(),
                                  end if end is not None else union.max(), freq='D')
        for row in rows:
            key = row['location'],row['member']
            if key in timeline and not timeline[key].equals(union):
                row['status'] = 'DIFFERENT'
                row['note'] = 'Coverage differs from other selected series; inspect first/last times'
    for filename, records, fields in [
        ('summary.csv',rows,list(rows[0])),
        ('differences.csv',detail,['location','member','time','parallel','serial','reason'])]:
        with (report/filename).open('w',newline='',encoding='utf-8') as out:
            writer=csv.DictWriter(out,fieldnames=fields);writer.writeheader();writer.writerows(records)
    passed = sum(row['status']=='MATCH' for row in rows)
    text = ('Run/trial: '+args.run_code+'\nMembers: '+args.members+
            '\nMatching series: '+str(passed)+' / '+str(len(rows))+
            '\nValue differences beyond tolerance: '+str(total_differences)+
            '\nAbsolute tolerance: '+str(args.atol)+'\n')
    if timeline: text += 'Compared timestamp range: '+str(union.min())+' to '+str(union.max())+'\n'
    text += ('Missing/undefined data, absent series and coverage differences fail the comparison.\n'
             'Up to 2000 differing/missing samples are listed; summary counts cover all data.\n'
             'Matching both files cannot prove freshness or a simulation endpoint absent from both.\n'
             'No DSS records were written.\n')
    outcome = 'PASS' if passed == len(rows) else 'FAIL'
    text = outcome+'\nParallel: '+str(args.parallel.resolve())+'\nSerial: '+str(args.serial.resolve())+'\n'+text
    (report/'result.txt').write_text(text,encoding='utf-8')
    print(text,flush=True);print('Reports:',report)
    return 0 if outcome == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
