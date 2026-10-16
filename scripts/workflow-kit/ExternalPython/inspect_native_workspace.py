"""Start installed ResSim's JVM and inspect only an isolated trial workspace."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import uuid
import time
import zipfile


def seed_trial_inputs(root, output, members):
    """Forecast mode reads inputs from its output DSS; seed inputs only."""
    from inspect_parallel_inputs import key, records
    from pydsstools.heclib.dss import HecDss
    from pydsstools.core import TimeSeriesContainer
    import numpy as np
    needed = {key(record['DssPathname'])[0]
              for name in ('_Con_Season.fits', '_Con_SeasonRTS.fits')
              for record in records(root / 'rss' / name)}
    count = 0
    with HecDss.Open(str(root / 'forecast.dss')) as source, HecDss.Open(str(output)) as target:
        for path in source.getPathnameList('/*/*/*/*/*/*/'):
            logical, member = key(path)
            if logical not in needed or member not in members:
                continue
            ts = source.read_ts(path, trim_missing=True)
            if ts.pytimes is None or not len(ts.pytimes):
                raise ValueError('Empty trial input: ' + path)
            container = TimeSeriesContainer()
            container.pathname = path
            container.startDateTime = ts.pytimes[0].strftime('%d%b%Y %H%M').upper()
            container.interval = {'1DAY': 1440, '6HOUR': 360}[path.split('/')[5].upper()]
            container.values = np.ma.asarray(ts.values, dtype=float).filled(-901.0)
            container.numberValues = len(container.values)
            container.units, container.type = ts.units, ts.type
            target.put_ts(container)
            count += 1
    print('Seeded input blocks:', count, 'No pool outputs copied.', flush=True)


def verify_trial_outputs(output, members):
    from pydsstools.heclib.dss import HecDss
    import numpy as np
    found = {member: set() for member in members}
    with HecDss.Open(str(output)) as source:
        for path in source.getPathnameList('/*/*/*/*/*/*/'):
            parts = path.split('/')
            for member in found:
                if (parts[6].upper() in ('C:%06d|C0' % member, 'C:%06d|' % member) and
                        parts[2].upper().endswith('-POOL') and
                        parts[3].upper() in ('ELEV', 'ELEVATION', 'FLOW-OUT')):
                    ts = source.read_ts(path, trim_missing=True)
                    if ts.values is None:
                        continue
                    values = np.ma.asarray(ts.values, dtype=float).filled(np.nan)
                    valid = np.isfinite(values) & (values > -1e20) & ~np.isin(values, [-901, -902, -903])
                    if valid.sum() > 1:
                        found[member].add((parts[2].upper(), parts[3].upper()))
    for member, groups in found.items():
        if not any(c in ('ELEV', 'ELEVATION') for b, c in groups) or not any(c == 'FLOW-OUT' for b, c in groups):
            raise ValueError('No valid fresh pool elevations/outflows for member %s; launcher return code is insufficient' % member)
        print('Fresh pool output groups, member %s: %s' % (member, len(groups)))
    print('Outputs exist; complete coverage and agreement with RTS still require comparison.')


JYTHON = r'''
import os
import sys
import traceback
from java.lang import System

status = 1
try:
    from hec.io import Identifier
    from hec.lang import UserId
    from hec.rss.server import RssRmiWorkspaceImpl
    from hec.clientapp.server import HecRmiWorkspaceImpl
    from hec.rss.plugins.ensemble import EnsemblePlugin
    from hec.rss.plugins.ensemble.compute import EnsembleComputeLauncher
    from mil.army.usace.hec.rmi.server import RmiFileManagerImpl, RemoteWrapper
    root = sys.argv[1].replace('\\', '/')
    user = UserId.getUserId()
    workspace = RssRmiWorkspaceImpl(8089)
    workspace.setLocal(True)
    # The workspace fallback still names hec.server.RmiFileManagerImpl,
    # while this installation ships the implementation in mil.army....
    manager = RmiFileManagerImpl()
    wrapper = RemoteWrapper()
    wrapper.setRemote(manager)
    # Configure both the inherited portable-object file manager and the
    # workspace's own cached wrapper, preventing its legacy fallback.
    cls = workspace.getClass()
    portable_setter = None
    while cls is not None:
        for method in cls.getDeclaredMethods():
            if method.getName() == 'setFileManager' and len(method.getParameterTypes()) == 1 and method.getParameterTypes()[0] == wrapper.getClass():
                portable_setter = method
                break
        if portable_setter is not None:
            break
        cls = cls.getSuperclass()
    if portable_setter is None:
        raise RuntimeError('No compatible file-manager setter found')
    portable_setter.setAccessible(True)
    portable_setter.invoke(workspace, [wrapper])
    cache = workspace.getClass().getSuperclass().getDeclaredField('_fileManager')
    cache.setAccessible(True)
    cache.set(workspace, wrapper)
    print('FILE MANAGER: ' + str(type(manager)))
    # setIdentifier appends the workspace extension when given rss.conf,
    # then may create an empty file. Open the existing config explicitly.
    opened = manager.openFile(user, Identifier(root + '/rss/rss.conf'))
    if opened is None or opened.getFile() is None or not opened.getFile().canRead():
        raise RuntimeError('Existing rss.conf could not be opened for reading')
    workspace.identifier = opened
    cls = workspace.getClass()
    path_setter = None
    while cls is not None:
        for method in cls.getDeclaredMethods():
            if method.getName() == 'setPath' and len(method.getParameterTypes()) == 1:
                path_setter = method
                break
        if path_setter is not None:
            break
        cls = cls.getSuperclass()
    if path_setter is None:
        raise RuntimeError('Protected workspace path setter not found')
    from java.lang import String
    path_setter.setAccessible(True)
    path_setter.invoke(workspace, [String(root)])
    workspace.setWorkspacePath(root)
    print('CONFIGURATION FILE: ' + str(opened.getFile().getPath()))
    parent = HecRmiWorkspaceImpl(8089)
    parent.setLocal(True)
    portable_setter.invoke(parent, [wrapper])
    cache.set(parent, wrapper)
    parent_file = manager.openFile(user, Identifier(root + '/' + os.path.basename(root) + '.wksp'))
    if parent_file is None or parent_file.getFile() is None or not parent_file.getFile().canRead():
        raise RuntimeError('Existing parent watershed workspace could not be opened')
    parent.identifier = parent_file
    path_setter.invoke(parent, [String(root)])
    parent.setWorkspacePath(root)
    if not parent.load():
        raise RuntimeError('Parent watershed workspace load returned false')
    workspace.setParentWorkspace(parent)
    print('PARENT WORKSPACE: %s; UNIT SYSTEM: %s' % (parent.getWorkspacePath(), parent.getUnitSystem()))
    # Normal ResSim startup loads plugins. Headless workspace construction
    # does not; the ensemble singleton registers its alternative data type.
    EnsemblePlugin.getPlugin()
    if not workspace.load():
        raise RuntimeError('Workspace load returned false')
    print('WORKSPACE: ' + workspace.getWorkspacePath())
    print('REGISTERED ALTERNATIVES: ' + str(workspace.getManagerIDList('main', 'hec.rss.model.RssAlt')))
    alt = workspace.openManagerByName('main', 'hec.rss.model.RssAlt', ':Con_Season')
    if alt is None:
        raise RuntimeError('Registered :Con_Season alternative could not be opened')
    print('ALTERNATIVE CLASS: ' + str(type(alt)))
    launcher = alt.getComputeLauncher()
    if launcher is None:
        raise RuntimeError('No ensemble launcher loaded')
    print('LAUNCHER: ' + str(type(launcher)))
    if not isinstance(launcher, EnsembleComputeLauncher):
        raise RuntimeError('Expected native EnsembleComputeLauncher; refusing default launcher')
    for variant in ('', 'RTS'):
        data = alt.getInputTSDataSet() if not variant else alt.getInputTSDataSet(variant, False)
        if data is None:
            raise RuntimeError('Missing input dataset: ' + variant)
        ts = data.getTSRecords()
        print('INPUT VARIANT: %s; RECORDS: %s' % (variant or 'base', ts.size()))
        for record in ts:
            print('INPUT: ' + str(record.getDSSPathname()))
    if len(sys.argv) > 2 and sys.argv[2] == 'compute':
        from hec.clientapp.model import ComputeInfo
        from java.io import File
        scripts = File(alt.getSystem().makeAbsolutePathFromWatershed('scripts')).getCanonicalPath()
        expected = File(root + '/scripts').getCanonicalPath()
        if scripts != expected:
            raise RuntimeError('Scripts resolve outside trial copy: ' + scripts)
        print('SCRIPT ROOT: ' + scripts)
        run = workspace.getRssRun('C0', False)
        if run is None:
            raise RuntimeError('Copied C0 run could not be loaded')
        run.setComputeType(ComputeInfo.FORECAST_COMPUTE)
        run.setVariantName('RTS')
        run.setForecastDir(root)
        run.setDSSOutputFile(sys.argv[3])
        run.setRunId('C0')
        run.setAltPath(alt.getIdentifier().getPath())
        run.setAlternative(alt)
        run.setProxyList(workspace.getManagerProxyList('main'))
        run_wrapper = RemoteWrapper()
        run_wrapper.setRemote(workspace)
        run.setWorkspace(run_wrapper)
        info = ComputeInfo()
        info.computeType = ComputeInfo.FORECAST_COMPUTE
        info.forecastpath = root
        info.modelAltname = 'C0'
        info.altname = ':Con_Season'
        info.outputDSSFileName = sys.argv[3]
        info.runTimeWindow = run.getRunTimeWindow()
        info.user = user
        info.doCompute = True
        info.variant = 'RTS'
        print('TRIAL COMPUTE: members ' + sys.argv[4] + '; configured workers: ' + System.getProperty('ResSim.ComputeThreadCount'))
        print('OUTPUT DSS: ' + sys.argv[3])
        print('TIME WINDOW: ' + run.getTimeWindowString())
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from native_worker_state import isolate_native_workers
        isolate_native_workers()
        launcher.setComputeInformation(info, workspace, run, alt, None)
        result = launcher.compute()
        print('NATIVE COMPUTE RETURN CODE: ' + str(result))
        status = 0 if result == 0 else 1
    else:
        print('INSPECTION COMPLETE: no compute invoked.')
        status = 0
except:
    traceback.print_exc()
finally:
    System.exit(status)
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installation', type=Path, required=True)
    parser.add_argument('--trial-root', type=Path, required=True)
    parser.add_argument('--compute', action='store_true', help='Compute only the prepared two-member trial')
    parser.add_argument('--watershed', type=Path, help='Source watershed whose scripts are copied into the trial')
    args = parser.parse_args()
    root = args.trial_root.resolve()
    if not root.parent.name.startswith('ressim-parallel-trial-'):
        parser.error('Only a prepared ressim-parallel-trial-* copy is accepted')
    if not (root / 'rss' / 'rss.conf').is_file():
        parser.error('Trial workspace configuration missing')
    manifest = root / 'native-trial.json'
    members = json.loads(manifest.read_text(encoding='utf-8'))['members'] if manifest.exists() else [1981, 1982]
    if len(members) != 2 or len(set(members)) != 2 or any(type(m) is not int or not 0 <= m <= 999999 for m in members):
        parser.error('Invalid two-member trial manifest')
    if args.compute:
        if args.watershed is None or not (args.watershed / 'scripts').is_dir():
            parser.error('--compute requires --watershed with an existing scripts folder')
        if (root / 'rts-augmentation-active.json').exists():
            parser.error('First native trial must have augmentation disabled')
        alternative_text = (root / 'rss' / '_Con_Season.ralt').read_text(encoding='utf-8-sig')
        expected_members = ','.join(str(m) for m in members) if manifest.exists() else '1981-1982'
        if ('\nEnsembleMembersString:' + expected_members + '\n') not in alternative_text:
            parser.error('Trial alternative does not match its two-member manifest')
        if not (root / 'scripts').exists():
            shutil.copytree(args.watershed / 'scripts', root / 'scripts')
        print('Using trial script snapshot:', root / 'scripts', flush=True)
    app = args.installation.resolve() / 'HEC-ResSim' / '4.1'
    java = app / 'java' / 'bin' / 'java.exe'
    if not java.is_file():
        parser.error('Installed ResSim Java executable not found')
    jars = sorted((app / 'jar').rglob('*.jar'))
    jars += sorted((args.installation / 'shared' / 'jar').glob('*.jar'))
    jars += sorted((args.installation / 'shared' / 'jar' / 'sys').glob('*.jar'))
    jars += sorted((args.installation / 'HEC-RTS' / 'jar' / 'ext').glob('*.jar'))
    required_class = 'mil/army/usace/hec/rmi/server/RmiFileManagerImpl.class'
    def contains_class(filename):
        with zipfile.ZipFile(filename) as archive:
            return required_class in archive.namelist()
    if not any(contains_class(filename) for filename in jars):
        # The file-manager implementation is shipped separately from the
        # client interfaces. Locate its actual owner rather than guess a name.
        candidates = sorted(args.installation.resolve().rglob('*.jar'),
                            key=lambda p: (0 if p.is_relative_to(app) else
                                           1 if 'shared' in p.parts else
                                           2 if 'HEC-RTS' in p.parts else 3, str(p)))
        compatible = [filename for filename in candidates if filename.is_relative_to(app)
                      or 'shared' in filename.parts or 'HEC-RTS' in filename.parts]
        owner = next((filename for filename in compatible if contains_class(filename)), None)
        if owner is None:
            print('FILE-MANAGER IMPLEMENTATIONS IN THIS INSTALLATION:', flush=True)
            for filename in candidates:
                with zipfile.ZipFile(filename) as archive:
                    for entry in archive.namelist():
                        if entry.endswith('.class') and 'filemanager' in entry.lower() and 'impl' in entry.lower() and '$' not in entry:
                            print(str(filename) + ' -> ' + entry, flush=True)
            parser.error('No ResSim/RTS/shared JAR provides the current file manager. '
                         'Inspection stopped; do not substitute an older HMS implementation.')
        jars.append(owner)
        print('Local file-manager implementation:', owner, flush=True)
    if not any('jython-standalone' in p.name for p in jars):
        parser.error('Jython standalone JAR missing from installed classpath')
    script = root.parent / 'inspect-workspace-jython.py'
    script.write_text(JYTHON, encoding='utf-8')
    if args.compute:
        shutil.copy2(Path(__file__).with_name('native_worker_state.py'), root.parent / 'native_worker_state.py')
    token = uuid.uuid4().hex[:8]
    output = root / ('native-parallel-' + token + '.dss')
    log = root.parent / ('native-compute-' + token + '.log' if args.compute else 'native-workspace-inspection.log')
    arguments = ['-Xmx3600m', '-DResSim.ComputeThreadCount=2',
               '-Djava.library.path=' + str(app / 'lib'), '-Dproperties.path=config',
               '-Dpython.path=' + str(root / 'scripts'),
               '-cp', os.pathsep.join(str(p.resolve()) for p in jars),
               'org.python.util.jython', str(script), str(root)]
    if args.compute:
        seed_trial_inputs(root, output, members)
        arguments += ['compute', str(output), ','.join(str(m) for m in members)]
    # Windows CreateProcess limits the command line to 32,767 characters.
    # Java 9+ reads these options from a file without that command-line limit.
    argfile = root.parent / 'native-workspace-java.args'
    argfile.write_text('\n'.join(json.dumps(value.replace('\\', '/'), ensure_ascii=False)
                                 for value in arguments) + '\n', encoding='utf-8')
    command = [str(java), '@' + str(argfile)]
    print('TWO-MEMBER TRIAL COMPUTE.' if args.compute else 'INSPECTION ONLY: no compute.', 'Log:', log, flush=True)
    with log.open('w', encoding='utf-8') as handle:
        process = subprocess.Popen(command, cwd=app, stdout=handle,
                                   stderr=subprocess.STDOUT)
        print('Java PID:', process.pid, 'Full compute output goes directly to the log.', flush=True)
        started = time.monotonic()
        try:
            while True:
                try:
                    status = process.wait(timeout=15)
                    break
                except subprocess.TimeoutExpired:
                    print('Java still running: %.0f seconds; log %.1f MB' %
                          (time.monotonic() - started, log.stat().st_size / 1048576), flush=True)
        except KeyboardInterrupt:
            print('Stopping only the trial Java process; trial output is incomplete.', flush=True)
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            root.parent.joinpath('native-compute-' + token + '.interrupted').write_text(
                'Trial interrupted; do not use its output as completed results.\n', encoding='utf-8')
            raise
    print('Exit code:', status, 'Log:', log)
    with log.open(encoding='utf-8', errors='replace') as handle:
        summary = [line.strip() for line in handle if any(word in line for word in
                   ('Total Compute Time', 'NATIVE COMPUTE RETURN CODE:', 'TRIAL COMPUTE:',
                    'OUTPUT DSS:', 'SCRIPT ROOT:', 'Traceback', 'ERROR Ensemble', 'RuntimeError:'))]
    for line in summary[-12:]:
        print(line)
    if args.compute and status == 0:
        verify_trial_outputs(output, members)
    sys.exit(status)


if __name__ == '__main__':
    main()
