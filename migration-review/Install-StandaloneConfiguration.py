"""Install configuration menu/adapters into an existing standalone test watershed.

Back up only affected scripts; do not copy watersheds or change application JARs.
"""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import shutil
import uuid

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('shared_editor',HERE/'ExternalPython/baseline_configuration.py')
import sys
sys.path.insert(0,str(HERE/'ExternalPython'))
editor=importlib.util.module_from_spec(spec);spec.loader.exec_module(editor)


def runtime_source():
    code=(HERE/'baseline-runtime/rts_baseline_runtime.py').read_text()
    code=code.replace('rts-baseline-config-active.json','standalone-baseline-config-active.json')
    code=code.replace('_rts_baseline_originals','_standalone_baseline_originals')
    code=code.replace('RTS baseline','Standalone baseline')
    needle="            source = os.path.abspath(os.path.join(directory, pointer['directory']))"
    assert code.count(needle)==1
    code=code.replace(needle,"            if pointer.get('model_alternative') != str(network.getAlternative().getName()).split(':')[-1]:\n                return None\n"+needle)
    needle="        if not match:\n            raise RuntimeError('Cannot identify ensemble member for baseline initialization receipt')"
    assert code.count(needle)==1
    code=code.replace(needle,"        # Non-ensemble standalone runs also receive a configuration receipt.")
    code=code.replace("'member': int(match.group(1)),", "'member': int(match.group(1)) if match else None,\n                       'output_fpart': str(network.getRssRun().getOutputFPart()),")
    return code.encode('utf-8')


def install(watershed):
    watershed=Path(watershed).resolve();scripts=watershed/'scripts'
    if not (scripts/'ExternalPython/CONFIG.py').is_file():raise ValueError('Expected existing standalone scripts/ExternalPython/CONFIG.py')
    originals=scripts/'_standalone_baseline_originals/externalRules'
    writes={};preserve={}
    for module in editor.MODULE_KEYS:
        target=scripts/'externalRules'/(module+'.py')
        current=target.read_bytes()
        if b'from rts_baseline_runtime import' in current:raise ValueError('RTS adapter detected: '+str(target))
        saved=originals/target.name
        adapted=b'from standalone_baseline_runtime import' in current
        if adapted and not saved.is_file():raise ValueError('Preserved standalone source missing: '+module)
        source=saved.read_bytes() if adapted else current
        if b'def initRuleScript(' not in source or b'def runRuleScript(' not in source:raise ValueError('Unknown rule structure: '+module)
        footer=(HERE/'baseline-runtime'/(module+'.py')).read_bytes().replace(b'rts_baseline_runtime',b'standalone_baseline_runtime')
        writes[target]=source+footer
        if not adapted:preserve[saved]=source
    setup=scripts/'externalSVs/Alternative_Setup.py';source=setup.read_text(encoding='utf-8-sig')
    if 'from rts_baseline_runtime import' in source:raise ValueError('RTS Alternative_Setup adapter detected')
    needle='        configDict.update(parseConfigListJSON(altConfigList))'
    if 'from standalone_baseline_runtime import alternative_overrides' not in source:
        if source.count(needle)!=1:raise ValueError('Alternative_Setup initialization differs; no files changed')
        source=source.replace(needle,needle+'\n        from standalone_baseline_runtime import alternative_overrides\n        configDict.update(alternative_overrides(network))')
    writes[setup]=source.encode('utf-8')
    writes[scripts/'standalone_baseline_runtime.py']=runtime_source()
    for name in ('baseline_configuration.py','baseline_versions.py','standalone_configuration.py'):
        writes[scripts/'ExternalPython'/name]=(HERE/'ExternalPython'/name).read_bytes()
    for name,sourcefile in [('baseline-editor.html','editor-mockup.html'),('baseline-configuration.example.json','baseline-configuration.example.json')]:
        writes[scripts/'ExternalPython'/name]=(HERE/'baseline-editor-design'/sourcefile).read_bytes()
    writes[scripts/'STANDALONE_WORKFLOW_MENU.py']=(HERE/'STANDALONE_WORKFLOW_MENU.py').read_bytes()
    # Every source/guard above is checked before the first mutation.
    backup=watershed/'standalone-configuration-backups'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8])
    backup.mkdir(parents=True)
    paths=dict(preserve);paths.update(writes)
    manifest=[]
    for target in paths:
        relative=target.relative_to(watershed)
        existed=target.exists()
        manifest.append({'path':str(relative),'existed':existed})
        if existed:
            dest=backup/relative;dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(target,dest)
            if editor.digest_file(target)!=editor.digest_file(dest):raise ValueError('Backup verification failed')
    (backup/'files.json').write_text(json.dumps(manifest,indent=2))
    try:
        for target,raw in paths.items():
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    except BaseException:
        for item in manifest:
            target=watershed/item['path']
            if item['existed']:shutil.copy2(backup/item['path'],target)
            else:target.unlink(missing_ok=True)
        raise
    for target in writes:
        target.with_name(target.stem+'$py.class').unlink(missing_ok=True)
    print('Installed standalone configuration menu. Script backup:',backup)
    print('No application JAR, alt_config file, CSV schedule, CONFIG.py, or simulation output changed.')
    print('Restart ResSim, open the same test watershed, and run scripts/STANDALONE_WORKFLOW_MENU.py.')
    return backup


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--watershed',required=True,type=Path)
    args=parser.parse_args();install(args.watershed)
