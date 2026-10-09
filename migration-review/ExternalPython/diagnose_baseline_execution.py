"""Reversible diagnostic switch. Run only after compute stops and RTS closes."""
import argparse
import json
from pathlib import Path
import shutil
import uuid

MODULES=('DeepDrawdown','SpringSpill','NoDraft','SecondaryFloodDraftLimit','FIRO_SPACE','MinFlowPlusWithdrawal','DiversionFromCSV','IRRM','DraftToRC','FillLOPfirst','HCR_LOP_Balance')


def switch(watershed, forecast, mode):
    watershed=Path(watershed);forecast=Path(forecast)
    if 'watershed' not in [part.lower() for part in watershed.parts]:
        raise ValueError('Diagnostic switch must target an imported RTS watershed')
    scripts=watershed/'scripts';marker=forecast/'rts-baseline-config-active.json'
    state=forecast/'baseline-execution-test.json'
    if mode=='configured':
        info=json.loads(state.read_text())
        backup=Path(info['backup'])
        sources=[backup/(name+'.py') for name in MODULES]
        if marker.exists(): raise ValueError('Configuration already active; refusing to replace it')
        pointer=backup/'active.json'
        if not pointer.exists(): raise ValueError('No applied configuration was saved for restoration')
    else:
        if state.exists(): raise ValueError('Diagnostic switch already active; restore configured mode first')
        sources=[scripts/'_rts_baseline_originals/externalRules'/(name+'.py') for name in MODULES]
    targets=[scripts/'externalRules'/(name+'.py') for name in MODULES]
    for path in sources+targets:
        if not path.is_file(): raise ValueError('Missing rule file: '+str(path))
    if mode=='original':
        backup=forecast/'baseline-execution-tests'/uuid.uuid4().hex
        backup.mkdir(parents=True)
        for name,target in zip(MODULES,targets): shutil.copy2(target,backup/(name+'.py'))
        if marker.exists(): shutil.copy2(marker,backup/'active.json')
        info={'backup':str(backup),'mode':'original','purpose':'Timing diagnostic only; do not accept results as baseline'}
        state.write_text(json.dumps(info,indent=2))
    completed=[]
    try:
        for source,target in zip(sources,targets):
            shutil.copy2(source,target);completed.append(target)
        if mode=='original':
            if marker.exists(): marker.unlink()
        else:
            shutil.copy2(pointer,marker);state.unlink()
    except Exception:
        if mode=='original':
            for target in completed: shutil.copy2(backup/target.name,target)
            if (backup/'active.json').exists(): shutil.copy2(backup/'active.json',marker)
            state.unlink()
        raise
    for target in targets:
        compiled=target.with_name(target.stem+'$py.class')
        if compiled.exists(): compiled.unlink()
    print('Execution mode:',mode)
    print('Backup:',backup)
    print('DSS files and augmentation configuration were not changed.')
    print('Restart RTS. Do not extract, apply settings, or accept diagnostic results as baseline.')
    return backup


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--watershed',required=True);parser.add_argument('--forecast-root',required=True)
    parser.add_argument('--mode',choices=('original','configured'),required=True)
    args=parser.parse_args();switch(args.watershed,args.forecast_root,args.mode)


if __name__=='__main__': main()
