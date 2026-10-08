"""Read DSS catalogs for plotting diagnostics; no downloads or record writes."""
import argparse
from pathlib import Path
import re


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--forecast-root', required=True)
    args = parser.parse_args()
    root = Path(args.forecast_root)
    if not root.is_dir():
        raise FileNotFoundError(root)
    files = sorted(p for p in root.rglob('*.dss')
                   if not any(part.startswith('extraction-test-') for part in p.relative_to(root).parts)
                   and '.backup-' not in p.name and '.before-' not in p.name)
    print('Forecast:', root)
    print('DSS files:', len(files))
    for path in files:
        print('FILE:', path.relative_to(root))
    # Catalog central DSS and up to two existing ensemble directories.
    groups = {}
    for path in files:
        parts = path.relative_to(root).parts
        if 'EnsembleRuns' in parts:
            index = parts.index('EnsembleRuns')
            if len(parts) > index + 1:
                groups.setdefault(parts[index + 1], []).append(path)
    selected = [p for p in files if 'EnsembleRuns' not in p.relative_to(root).parts]
    for member in sorted(groups)[:2]:
        selected.extend(groups[member])
    from pydsstools.heclib.dss import HecDss
    for path in selected:
        print('\nCATALOG:', path.relative_to(root))
        with HecDss.Open(str(path)) as dss:
            paths = sorted(dss.getPathnameList('/*/*/*/*/*/*/'))
        print('Record count:', len(paths))
        parts = [p.split('/') for p in paths if len(p.split('/')) == 8]
        print('Collection member IDs:', sorted({int(re.match(r'C:(\d+)\|', p[6]).group(1))
              for p in parts if re.match(r'C:(\d+)\|', p[6])}))
        outputs = [p for p in parts if p[3].upper() in ('ELEV', 'ELEVATION', 'FLOW-OUT', 'FLOW')
                   and p[6].upper() not in ('RULE CURVE', 'DUMMY')
                   and not p[6].upper().endswith('|RULE CURVE')
                   and not p[6].upper().endswith('|DUMMY')]
        print('Output F-parts:', sorted({p[6] for p in outputs}))
        print('Output intervals:', sorted({p[5] for p in outputs}))
        # Show block/path conventions once per location/parameter/F-part.
        seen = set()
        for p in outputs:
            key = (p[2], p[3], p[5], p[6])
            if key not in seen:
                seen.add(key)
                if len(seen) <= 30:
                    print('OUTPUT:', '/'.join(p))
    print('\nCatalog inspection complete; no DSS records written.')


if __name__ == '__main__':
    main()
