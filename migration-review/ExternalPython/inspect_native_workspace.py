"""Start installed ResSim's JVM and inspect only an isolated trial workspace."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile


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
    workspace.setIdentifier(user, Identifier(root + '/rss/rss.conf'))
    workspace.setWorkspacePath(root)
    if not workspace.load():
        raise RuntimeError('Workspace load returned false')
    print('WORKSPACE: ' + workspace.getWorkspacePath())
    alt = workspace.openManager(Identifier(root + '/rss/_Con_Season.ralt'))
    if alt is None:
        raise RuntimeError('Alternative could not be opened')
    print('ALTERNATIVE CLASS: ' + str(type(alt)))
    launcher = alt.getComputeLauncher()
    if launcher is None:
        raise RuntimeError('No ensemble launcher loaded')
    print('LAUNCHER: ' + str(type(launcher)))
    for variant in ('', 'RTS'):
        data = alt.getInputTSDataSet() if not variant else alt.getInputTSDataSet(variant, False)
        if data is None:
            raise RuntimeError('Missing input dataset: ' + variant)
        ts = data.getTSRecords()
        print('INPUT VARIANT: %s; RECORDS: %s' % (variant or 'base', ts.size()))
        for record in ts:
            print('INPUT: ' + str(record.getDSSPathname()))
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
    args = parser.parse_args()
    root = args.trial_root.resolve()
    if not root.parent.name.startswith('ressim-parallel-trial-'):
        parser.error('Only a prepared ressim-parallel-trial-* copy is accepted')
    if not (root / 'rss' / 'rss.conf').is_file():
        parser.error('Trial workspace configuration missing')
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
    log = root.parent / 'native-workspace-inspection.log'
    arguments = ['-Xmx3600m', '-DResSim.ComputeThreadCount=2',
               '-Djava.library.path=' + str(app / 'lib'), '-Dproperties.path=config',
               '-cp', os.pathsep.join(str(p.resolve()) for p in jars),
               'org.python.util.jython', str(script), str(root)]
    # Windows CreateProcess limits the command line to 32,767 characters.
    # Java 9+ reads these options from a file without that command-line limit.
    argfile = root.parent / 'native-workspace-java.args'
    argfile.write_text('\n'.join(json.dumps(value.replace('\\', '/'), ensure_ascii=False)
                                 for value in arguments) + '\n', encoding='utf-8')
    command = [str(java), '@' + str(argfile)]
    print('INSPECTION ONLY: no compute. Log:', log, flush=True)
    with log.open('w', encoding='utf-8') as handle:
        process = subprocess.Popen(command, cwd=app, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, errors='replace')
        for line in process.stdout:
            print(line, end='', flush=True)
            handle.write(line)
        status = process.wait()
    print('Exit code:', status, 'Log:', log)
    sys.exit(status)


if __name__ == '__main__':
    main()
