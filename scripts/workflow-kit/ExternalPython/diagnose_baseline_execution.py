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


def compare_configurations(original, applied):
    differences=[]
    def normalized(value):
        if isinstance(value,bool) or value is None: return value
        if isinstance(value,str):
            value=value.strip()
            try: return float(value)
            except ValueError: return value
        return value
    for key,rule in original['rules'].items():
        other=applied['rules'][key]
        for setting,value in rule['settings'].items():
            if value != other['settings'].get(setting):
                differences.append('{} / {}: original={} applied={}'.format(key,setting,json.dumps(value),json.dumps(other['settings'].get(setting))))
        for name,table in rule['tables'].items():
            other_table=other['tables'][name]
            if table['columns'] != other_table['columns']:
                differences.append('{} / {}: column names/order differ'.format(key,name))
                continue
            rows,others=table['rows'],other_table['rows']
            if len(rows)!=len(others):
                differences.append('{} / {}: row counts {} vs {}'.format(key,name,len(rows),len(others)))
            cells=[]
            for row_number,(row,other_row) in enumerate(zip(rows,others),1):
                for column,value,new_value in zip(table['columns'],row,other_row):
                    if normalized(value)!=normalized(new_value):
                        cells.append('row {} {}: {!r} -> {!r}'.format(row_number,column,value,new_value))
            if cells:
                differences.append('{} / {}: {} changed cells; {}'.format(key,name,len(cells),'; '.join(cells[:8])))
    return differences


def compare(watershed,forecast):
    from baseline_configuration import current_configuration
    from baseline_versions import digest_file
    watershed=Path(watershed);forecast=Path(forecast)
    if (forecast/'rts-baseline-config-active.json').exists():
        raise ValueError('Run comparison while original diagnostic mode remains active')
    info=json.loads((forecast/'baseline-execution-test.json').read_text())
    pointer=json.loads((Path(info['backup'])/'active.json').read_text())
    stage=forecast/pointer['directory']
    path=stage/'resolved.json'
    if digest_file(path)!=pointer['resolved_sha256']: raise ValueError('Saved configuration checksum mismatch')
    applied=json.loads(path.read_text())
    original=current_configuration(forecast,watershed/'scripts/ExternalPython')
    differences=compare_configurations(original,applied)
    print('READ ONLY: comparing imported originals with '+pointer['name'])
    for module,expected in applied['script_sha256'].items():
        source=watershed/'scripts/_rts_baseline_originals/externalRules'/(module+'.py')
        if digest_file(source)!=expected: differences.append('Rule source changed since Apply: '+module)
    if differences:
        for difference in differences: print(difference)
    else: print('No differences in exposed settings, schedule values, or preserved rule source hashes.')
    print('No files changed. Original diagnostic mode remains active.')
    return differences


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--watershed',required=True);parser.add_argument('--forecast-root',required=True)
    parser.add_argument('--mode',choices=('original','configured','compare'),required=True)
    args=parser.parse_args()
    if args.mode=='compare': compare(args.watershed,args.forecast_root)
    else: switch(args.watershed,args.forecast_root,args.mode)


if __name__=='__main__': main()
