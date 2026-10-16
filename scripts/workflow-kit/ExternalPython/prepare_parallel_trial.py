"""Prepare an isolated, two-member native batch trial; never start compute."""
import argparse
import json
from pathlib import Path
import re
import shutil
import tempfile

from inspect_parallel_inputs import key, records


def remap(text, first_member=1981):
    text = re.sub(r'^TSRecord DssFilename=.*$', 'TSRecord DssFilename=forecast.dss', text, flags=re.M)
    def collection(match):
        parts = match[1].split('/')
        key(match[1])  # Validate before changing anything.
        parts[6] = ('C:%06d|' % first_member) + re.sub(r'^C:\d+\|', '', parts[6], flags=re.I)
        return 'TSRecord DssPathname=' + '/'.join(parts)
    return re.sub(r'^TSRecord DssPathname=(.*)$', collection, text, flags=re.M)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--forecast-root', type=Path, required=True)
    parser.add_argument('--members', default='1985,1986', help='Exactly two historical member IDs')
    args = parser.parse_args()
    members = [int(value) for value in args.members.split(',')]
    if len(members) != 2 or len(set(members)) != 2 or any(m < 0 or m > 999999 for m in members):
        parser.error('Provide exactly two distinct six-digit member IDs')
    source = args.forecast_root.resolve()
    templates = [source / 'rss' / name for name in ('_Con_Season.fits', '_Con_SeasonRTS.fits')]
    from pydsstools.heclib.dss import HecDss
    available = set()
    with HecDss.Open(str(source / 'forecast.dss')) as dss:
        for path in dss.getPathnameList('/*/*/*/*/*/*/'):
            available.add(key(path))
    for template in templates:
        for record in records(template):
            logical, _ = key(record['DssPathname'])
            for member in members:
                if (logical, member) not in available:
                    raise ValueError('Missing member input: %s / %s' % (member, record['DssPathname']))
    alternative = source / 'rss' / '_Con_Season.ralt'
    alt_text = alternative.read_text(encoding='utf-8-sig')
    if alt_text.count('EnsembleMembersString:') != 1 or 'UseMultithreadedCompute:true' not in alt_text:
        raise ValueError('Expected exactly one multithreaded ensemble configuration')
    trial_parent = Path(tempfile.mkdtemp(prefix='ressim-parallel-trial-', dir=str(source.parent)))
    target = trial_parent / source.name
    excluded = {'augmentation-archives', 'EnsembleRuns', 'output_plots', 'workflow-logs', 'baseline-execution-tests'}
    def ignore(directory, names):
        if Path(directory) != source:
            return []
        return [name for name in names if name in excluded or name.startswith('extraction-test-')
                or (name.endswith('.dss') and name != 'forecast.dss')]
    try:
        shutil.copytree(source, target, ignore=ignore)
        for template in templates:
            copied = target / 'rss' / template.name
            copied.write_text(remap(template.read_text(encoding='utf-8-sig'), members[0]), encoding='utf-8')
        alt_text = re.sub(r'^EnsembleMembersString:.*$', 'EnsembleMembersString:' + ','.join(str(m) for m in members), alt_text, flags=re.M)
        (target / 'rss' / alternative.name).write_text(alt_text, encoding='utf-8')
    except Exception:
        print('INCOMPLETE TRIAL COPY (do not compute):', trial_parent)
        raise
    (target / 'native-trial.json').write_text(json.dumps({'members': members}, indent=2), encoding='utf-8')
    print('PREPARED ONLY:', target)
    print('Members:', members, 'Input files: copied forecast.dss. Live forecast unchanged.')
    print('No compute started. Existing C0.rssrun still records RTS mode 3; do not reuse it unchanged.')
    print('Next: native launcher setup, two workers, and comparison with RTS pool outputs.')
    print('Catalog presence checked; time coverage and script path isolation remain unverified.')


if __name__ == '__main__':
    main()
