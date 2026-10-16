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


def install(watershed, mode="standalone"):
    if mode not in ("standalone", "rts"):raise ValueError("Unknown workflow mode")
    watershed=Path(watershed).resolve();scripts=watershed/'scripts'
    if not (scripts/'ExternalPython').is_dir():raise ValueError('Expected existing scripts/ExternalPython directory')
    originals=scripts/('_'+mode+'_baseline_originals')/'externalRules'
    runtime=mode+'_baseline_runtime'
    writes={};preserve={}
    for module in editor.MODULE_KEYS:
        target=scripts/'externalRules'/(module+'.py')
        current=target.read_bytes()
        adapter=None
        for candidate in ('standalone','rts'):
            if ('from '+candidate+'_baseline_runtime import').encode() in current:
                adapter=candidate
        saved=originals/target.name
        source_path=scripts/('_'+adapter+'_baseline_originals')/'externalRules'/target.name if adapter else target
        if not source_path.is_file():raise ValueError('Preserved source missing: '+module)
        source=source_path.read_bytes()
        if b'def initRuleScript(' not in source or b'def runRuleScript(' not in source:raise ValueError('Unknown rule structure: '+module)
        footer=(HERE/'baseline-runtime'/(module+'.py')).read_bytes().replace(b'rts_baseline_runtime',runtime.encode())
        writes[target]=source+footer
        if adapter != mode:preserve[saved]=source
    setup=scripts/'externalSVs/Alternative_Setup.py';source=setup.read_text(encoding='utf-8-sig')
    for candidate in ('standalone','rts'):
        source=source.replace('\n        from '+candidate+'_baseline_runtime import alternative_overrides\n        configDict.update(alternative_overrides(network))','')
    needle='        configDict.update(parseConfigListJSON(altConfigList))'
    if source.count(needle)!=1:raise ValueError('Alternative_Setup initialization differs; no files changed')
    source=source.replace(needle,needle+'\n        from '+runtime+' import alternative_overrides\n        configDict.update(alternative_overrides(network))')
    writes[setup]=source.encode('utf-8')
    writes[scripts/(runtime+'.py')]=runtime_source() if mode=='standalone' else (HERE/'baseline-runtime/rts_baseline_runtime.py').read_bytes()
    for name in ('baseline_configuration.py','baseline_versions.py','standalone_configuration.py','standalone_jobs.py','standalone_results.py','standalone_model_check.py','standalone_por_augmentation.py','run_archive.py','run_data_cache.py','plot_rts_forecast.py','write_rule_curves.py','augmentation_mapping.py','ensemble_ids.py'):
        writes[scripts/'ExternalPython'/name]=(HERE/'ExternalPython'/name).read_bytes()
    for name,sourcefile in [('baseline-editor.html','editor-mockup.html'),('baseline-configuration.example.json','baseline-configuration.example.json')]:
        writes[scripts/'ExternalPython'/name]=(HERE/'baseline-editor-design'/sourcefile).read_bytes()
    writes[scripts/'STANDALONE_WORKFLOW_MENU.py']=(HERE/'STANDALONE_WORKFLOW_MENU.py').read_bytes()
    mainstem=scripts/'externalSVs/MainstemFlowAugSV.py'
    preserved_mainstem=scripts/'_workflow_originals/MainstemFlowAugSV.py'
    if mode=='rts':
        # Match the maintained RTS extraction installer, without copying CONFIG.py.
        import re
        extraction=(HERE/'Install-ForecastExtraction.ps1').read_text()
        names=re.findall(r"'([^']+)'",extraction.split('$names = @(',1)[1].split(')',1)[0])
        for name in names:
            target=scripts/'ExternalPython'/name
            saved=scripts/'_workflow_originals/ExternalPython'/name
            if target not in writes and target.exists() and not saved.exists():
                preserve[saved]=target.read_bytes()
            writes[target]=(HERE/'ExternalPython'/name).read_bytes()
        for name in ('RTS_WORKFLOW_MENU.py','RTS_FORECAST_EXTRACT.py'):
            writes[scripts/name]=(HERE/name).read_bytes()
        if not preserved_mainstem.exists():preserve[preserved_mainstem]=mainstem.read_bytes()
        writes[mainstem]=(HERE/'externalSVs/MainstemFlowAugSV.py').read_bytes()
    else:
        if preserved_mainstem.exists():writes[mainstem]=preserved_mainstem.read_bytes()
        for saved in (scripts/'_workflow_originals/ExternalPython').glob('*'):
            target=scripts/'ExternalPython'/saved.name
            if target not in writes:writes[target]=saved.read_bytes()
    if mode=='standalone':
        # Patch the actual installed scripts rather than replacing their local
        # mappings/date controls with a repository snapshot. Guards are checked
        # before backup/write, like the native rule adapters above.
        import re
        for filename in ('RFC_Downloader_Module.py','OSI_Ensemble_Year.py','MainstemAugmentation.py'):
            target=scripts/'ExternalPython'/filename
            source=writes.get(target,target.read_bytes()).decode('utf-8-sig').replace('\r\n','\n')
            if filename=='RFC_Downloader_Module.py':
                legacy=all('df1d['+str(member)+'] = pct.quantile' in source for member in (2026,2027,2028))
                if legacy:
                    start=source.index('                        df1d[2026] = pct.quantile')
                    end=source.index('\n',source.index('                        df1d[2028] = pct.quantile',start))
                    source=source[:start]+"                        from ensemble_ids import add_percentile_members\n                        df1d = add_percentile_members(pct)"+source[end:]
                    source=source.replace('# 2026 = 25th percentile, 2027 = 50th percentile, 2028 = 75th percentile','# Shared IDs: 3000 = 25%, 3001 = 50%, 3002 = 75%.')
                elif 'add_percentile_members' not in source:raise ValueError('Unknown RFC member creation code; no files changed')
            elif filename=='OSI_Ensemble_Year.py':
                if not re.search(r'^TARGET_ENSEMBLE_YEAR = (2029|3003)$',source,re.M):raise ValueError('Unknown OSI destination code; no files changed')
                source=re.sub(r'^TARGET_ENSEMBLE_YEAR = 2029$', 'TARGET_ENSEMBLE_YEAR = 3003',source,flags=re.M)
            else:
                needle='enesemble_years = list(range(1981, 2029))'
                replacement='from ensemble_ids import computed_standalone_members\nenesemble_years = [] if getattr(cfg, "RUN_TYPE", "ensemble") == "por" else computed_standalone_members(DSS_FILE_IN, ALTERNATIVE_NAME_STEP1)'
                if source.count(needle)==1:source=source.replace(needle,replacement)
                elif 'enesemble_years = computed_standalone_members(' in source:
                    source=source.replace('enesemble_years = computed_standalone_members(DSS_FILE_IN, ALTERNATIVE_NAME_STEP1)',replacement.split('\n')[-1])
                elif replacement not in source:raise ValueError('Unknown augmentation member selection; no files changed')
                if 'from standalone_por_augmentation import' not in source:
                    anchor='fparts = [f"C:00{year}|{FORMATTED_ALT_NAME}" for year in enesemble_years]'
                    if source.count(anchor)!=1:raise ValueError('Unknown augmentation F-part selection; no files changed')
                    source=source.replace(anchor,anchor+'\nif getattr(cfg, "RUN_TYPE", "ensemble") == "por":\n    from standalone_por_augmentation import por_fparts, read_daily_por\n    fparts = por_fparts(DSS_FILE_IN, ALTERNATIVE_NAME_STEP1)\n    readallpaths_dpart = read_daily_por')
            writes[target]=source.encode('utf-8')
    model_source=HERE/'model_check' if (HERE/'model_check').is_dir() else HERE.parent/'model_check'
    for name in ('extract_dss.py','check_model.py','catalog_dss.py','run_model_check.py','control_point_limits.csv','README.md'):
        writes[scripts/'model_check'/name]=(model_source/name).read_bytes()
    writes[scripts/'workflow-mode.json']=(json.dumps({'mode':mode},indent=2)+'\n').encode()
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
    print('Installed '+mode+' workflow. Script backup:',backup)
    print('No application JAR, alt_config file, CSV schedule, CONFIG.py, or simulation output changed.')
    print('Restart the application and run scripts/'+('STANDALONE_WORKFLOW_MENU.py' if mode=='standalone' else 'RTS_WORKFLOW_MENU.py'))
    return backup


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--watershed',required=True,type=Path)
    parser.add_argument('--mode',choices=('standalone','rts'),default='standalone')
    args=parser.parse_args();install(args.watershed,args.mode)
