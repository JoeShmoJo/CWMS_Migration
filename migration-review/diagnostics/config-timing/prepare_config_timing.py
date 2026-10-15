"""Copy a V2 installation and watershed, adding timing only to the copies."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

FOOTER = b'''\n\n# CONFIG_READ_TIMING_DIAGNOSTIC: copied-model measurement only
from config_read_timing_diagnostic import instrument_module as _config_timing_instrument
_config_timing_instrument(globals(), __name__, %s, %s)
'''


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rewrite_references(root, source):
    """Rebase known text model/script paths; never alter DSS or binary data."""
    extensions = {'.wksp', '.conf', '.simperiod', '.rssrun', '.ralt', '.malt',
                  '.fits', '.rsys', '.txt', '.json', '.csv', '.py', '.xml',
                  '.properties', '.igv', '.rssout'}
    replacements = [(str(source), str(root)), (source.as_posix(), root.as_posix()),
                    (str(source).replace('\\', '\\\\'), str(root).replace('\\', '\\\\'))]
    count = 0
    for path in root.rglob('*'):
        if not path.is_file() or path.suffix.lower() not in extensions:
            continue
        data = path.read_bytes()
        if b'\x00' in data:
            continue
        changed = data
        for old, new in sorted(set(replacements), key=lambda item: -len(item[0])):
            changed = re.sub(re.escape(old.encode('utf-8')),
                             lambda match: new.encode('utf-8'), changed, flags=re.I)
        if changed != data:
            path.write_bytes(changed)
            count += 1
    return count


def plans(watershed):
    scripts = watershed/'scripts'
    cfile = scripts/'NWDJyLib/cFile.py'
    if not cfile.is_file():
        raise ValueError('NWDJyLib/cFile.py missing')
    result = []
    files = [cfile]+sorted((scripts/'externalRules').glob('*.py'))
    files += sorted((scripts/'externalSVs').glob('*.py'))
    for file in files:
        raw = file.read_bytes()
        if b'CONFIG_READ_TIMING_DIAGNOSTIC' in raw:
            raise ValueError('Source already instrumented: '+str(file))
        definitions = re.findall(rb'^def\s+([A-Za-z_]\w*)\s*\(', raw, re.M)
        if file == cfile:
            names = [n.decode('ascii') for n in definitions
                     if n in (b'fileOpenReadClose', b'fileOpenReadCloseWithEncoding')]
            category = 'read'
        else:
            names = [n.decode('ascii') for n in definitions if b'config' in n.lower()
                     and n.lower().startswith((b'load', b'read'))]
            category = 'loader'
        names = sorted(set(names))
        if names:
            result.append((file, raw, names, category))
    if not any(p[3] == 'loader' for p in result):
        raise ValueError('No top-level config loaders found')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('installation', 'watershed', 'destination-installation', 'destination-watershed'):
        parser.add_argument('--'+name, required=True, type=Path)
    args = parser.parse_args()
    installation = args.installation.resolve()
    watershed = args.watershed.resolve()
    dest_install = args.destination_installation.resolve()
    dest_ws = args.destination_watershed.resolve()
    for dest in (dest_install, dest_ws):
        if dest.exists():
            raise ValueError('Destination already exists: '+str(dest))
        for source in (installation, watershed):
            if dest == source or source in dest.parents:
                raise ValueError('Destinations must be outside both source trees')
    if dest_install in dest_ws.parents or dest_ws in dest_install.parents:
        raise ValueError('Destination trees must be separate')
    marker = json.loads((installation/'compiler-isolation-test.json').read_text())
    if marker.get('compiler_isolation_version') != 2:
        raise ValueError('Source installation must be V2')
    app = installation/'jar/ResSimApp-4.1.0.jar'
    if digest(app) != marker['patched_sha256']:
        raise ValueError('V2 application checksum differs from marker')
    candidates = plans(watershed)
    tools = Path(__file__).resolve().parent
    runtime = tools/'config_read_timing_diagnostic.py'
    helper = tools/'config-read-timing-diagnostic.jar'
    if not runtime.is_file() or not helper.is_file():
        raise ValueError('Diagnostic helper files missing')
    if (watershed/'scripts/config_read_timing_diagnostic.py').exists():
        raise ValueError('Source already contains diagnostic module')
    shutil.copytree(installation, dest_install)
    shutil.copytree(watershed, dest_ws)
    rebased = rewrite_references(dest_ws, watershed)
    shutil.copy2(helper, dest_install/'jar'/helper.name)
    report_root = dest_ws/'config-read-timing-reports'
    replacement = ('REPORT_ROOT = u'+ascii(str(report_root))).encode('ascii')
    code = runtime.read_bytes().replace(b'REPORT_ROOT = None', replacement)
    (dest_ws/'scripts'/runtime.name).write_bytes(code)
    details = []
    for source, raw, names, category in candidates:
        target = dest_ws/source.relative_to(watershed)
        footer = FOOTER % (repr(names).encode('ascii'), repr(category).encode('ascii'))
        target.write_bytes(target.read_bytes()+footer)
        compiled = target.with_name(target.stem+'$py.class')
        if compiled.exists():
            compiled.unlink()
        details.append({'file': str(source.relative_to(watershed)), 'functions': names,
                        'category': category, 'source_sha256': hashlib.sha256(raw).hexdigest()})
    info = {'timing_only': True, 'cache_enabled': False,
            'source_installation': str(installation), 'source_watershed': str(watershed),
            'installation': str(dest_install), 'watershed': str(dest_ws),
            'reports': str(report_root), 'instrumented': details,
            'rebased_text_files': rebased}
    for dest in (dest_ws, dest_install):
        (dest/'config-read-timing-diagnostic.json').write_text(json.dumps(info, indent=2))
    if digest(app) != marker['patched_sha256']:
        raise RuntimeError('Original V2 integrity check failed')
    print('PREPARED ONLY: timing diagnostic; no caching and no compute started.')
    print('INSTALLATION:', dest_install)
    print('WATERSHED:', dest_ws)
    print('REPORTS:', report_root)
    print('Instrumented modules:', len(details), 'functions:', sum(len(d['functions']) for d in details))
    print('Copied text files rebased to the sandbox:', rebased)
    print('Launch the copied installation and open the copied watershed, then run ONE compute.')
    print('Close the copied application normally after compute to write the timing report.')
    print('Do not launch incomplete copies if preparation raises an error.')


if __name__ == '__main__':
    main()
