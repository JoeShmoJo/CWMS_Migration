"""Read-only comparison of input templates with a forecast DSS catalog.

Does not read time-series values, change mappings, or start a compute.
Catalog matches establish record presence, not time coverage or validity.
"""
import argparse
from collections import defaultdict
from pathlib import Path
import re


def records(filename):
    current = {}
    for line in filename.read_text(encoding='utf-8-sig').splitlines():
        if line.startswith('TSRecord='):
            current = {}
        elif line.startswith('TSRecord End='):
            yield current
        elif line.startswith('TSRecord ') and '=' in line:
            key, value = line.split('=', 1)
            current[key.removeprefix('TSRecord ')] = value


def key(path):
    parts = path.split('/')
    if len(parts) != 8:
        raise ValueError('Invalid DSS pathname: ' + path)
    match = re.match(r'^C:(\d+)\|(.*)$', parts[6], re.I)
    member, suffix = (int(match[1]), match[2]) if match else (None, parts[6])
    return tuple(p.upper() for p in (parts[1], parts[2], parts[3], parts[5], suffix)), member


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--forecast-root', type=Path, required=True)
    parser.add_argument('--members', default='1981,1982')
    args = parser.parse_args()
    members = [int(value) for value in args.members.split(',')]
    from pydsstools.heclib.dss import HecDss
    catalog = defaultdict(set)
    with HecDss.Open(str(args.forecast_root / 'forecast.dss')) as dss:
        for path in dss.getPathnameList('/*/*/*/*/*/*/'):
            logical, member = key(path)
            catalog[logical].add(member)
    print('READ ONLY: catalog presence only; no values read or compute started.')
    for filename in ('_Con_Season.fits', '_Con_SeasonRTS.fits'):
        print('\nINPUT TEMPLATE:', filename)
        counts = defaultdict(int)
        for record in records(args.forecast_root / 'rss' / filename):
            logical, _ = key(record['DssPathname'])
            present = catalog.get(logical, set())
            if all(member in present for member in members):
                status = 'MEMBER RECORDS PRESENT'
            elif None in present:
                status = 'SHARED RECORD PRESENT'
            else:
                status = 'MISSING MEMBERS ' + ','.join(str(m) for m in members if m not in present)
            counts[status] += 1
            print(status, '|', record.get('Name', ''), '|', record['DssPathname'])
        print('SUMMARY:', dict(counts))
    print('\nPresence does not verify coverage, input-position overrides, or native batch compatibility.')


if __name__ == '__main__':
    main()
