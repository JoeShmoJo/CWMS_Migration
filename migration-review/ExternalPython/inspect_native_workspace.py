"""Start installed ResSim's JVM and inspect only an isolated trial workspace."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


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
    root = sys.argv[1].replace('\\', '/')
    user = UserId.getUserId()
    workspace = RssRmiWorkspaceImpl(8089)
    workspace.setLocal(True)
    workspace.setIdentifier(user, Identifier(root + '/rss/rss.conf'))
    workspace.setWorkspacePath(root)
    if not workspace.load():
        raise RuntimeError('Workspace load returned false')
    print('WORKSPACE: ' + workspace.getWorkspacePath())
    alt = workspace.openManager(Identifier(root + '/rss/_Con_Season.ralt'))
    if alt is None:
        raise RuntimeError('Alternative could not be opened')
    print('ALTERNATIVE CLASS: ' + alt.getClass().getName())
    launcher = alt.getComputeLauncher()
    if launcher is None:
        raise RuntimeError('No ensemble launcher loaded')
    print('LAUNCHER: ' + launcher.getClass().getName())
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
