"""Run the existing model check for exactly one POR output or ensemble member."""
import importlib.util
import json
from pathlib import Path
import re
import uuid
from baseline_versions import digest_file,atomic_json
from run_archive import signature


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def run(root,alternative,code,run_type,member=None):
    root=Path(root);watershed=root.parent.parent;source=root/'simulation.dss'
    if run_type not in ('ensemble','por'):raise ValueError('Invalid run type')
    if run_type=='ensemble' and (isinstance(member,bool) or not isinstance(member,int) or member<0):raise ValueError('Select a single ensemble member')
    suffix=alternative.replace(' ','-').ljust(10,'-')
    if not re.fullmatch(re.escape(suffix)+r'\d+',code,re.I):raise ValueError('Output does not match native alternative')
    fpart=('C:'+str(member).zfill(6)+'|' if run_type=='ensemble' else '')+code
    from pydsstools.heclib.dss import HecDss
    before=signature(source)
    with HecDss.Open(str(source)) as dss:
        available={str(path).split('/')[6] for path in dss.getPathnameList('/*/*/*/*/*/*/') if len(str(path).split('/'))==8}
    matches=[value for value in available if value.upper()==fpart.upper()]
    if len(matches)!=1:raise ValueError('Exact completed output/member is absent or ambiguous: '+fpart)
    fpart=matches[0]
    folder=watershed/'scripts/model_check'
    if not (folder/'extract_dss.py').is_file():raise ValueError('Install the model-check scripts into this watershed first')
    destination=root/'model-check-runs'/('check-'+uuid.uuid4().hex);destination.mkdir(parents=True)
    status={'status':'incomplete','source':str(source),'source_signature':before,'alternative':alternative,
            'run_type':run_type,'member':member if run_type=='ensemble' else None,'f_part':fpart,
            'note':'Checks current configured expectations against selected live results; native compute freshness and operation-report freshness must be verified by operator.'}
    try:
        extractor=load('workflow_check_extract',folder/'extract_dss.py')
        checker=load('workflow_check_report',folder/'check_model.py')
        extractor.OUTPUT_ROOT=str(destination)
        # Pass the real alternative for metadata/config names, but never let the
        # old prefix-based selector choose a different member or trial.
        extractor.fPartFor=lambda paths,unused:fpart
        def exact_model_report(simDir,selectedAlternative,outDir):
            import shutil
            for relative in extractor.MODEL_REPORT_DIRS:
                path=Path(simDir)/relative/('modelReport_'+selectedAlternative+'.json')
                if path.is_file():
                    shutil.copy2(path,Path(outDir)/'modelReport.json');return
            print('No matching model report for '+selectedAlternative+'; rule-stack checks will be limited',flush=True)
        extractor.copyModelReport=exact_model_report
        directory=Path(extractor.main(str(source),alternative))
        checker.CONFIG_ROOT=str(watershed)
        original=checker.configPath
        overrides={}
        pointer=root/'standalone-baseline-config-active.json'
        if pointer.exists():
            data=json.loads(pointer.read_text())
            if data.get('model_alternative')!=alternative:raise ValueError('Applied alternative differs; use matching configuration')
            applied=root/data['directory'];resolved=applied/'resolved.json'
            if digest_file(resolved)!=data['resolved_sha256']:raise ValueError('Applied configuration checksum mismatch')
            settings=json.loads(resolved.read_text());overrides={key:str((applied/path).resolve()) for key,path in settings['table_paths'].items()}
            status['configuration_id']=data['id']
        # Match the existing coupled diversion/withdrawal disable switch in
        # report-local expectations; never edit the real schedules.
        switch=watershed/'scripts/diversion-demands.json'
        if switch.exists():
            enabled=json.loads(switch.read_text()).get('diversion_demands_enabled')
            if not isinstance(enabled,bool):raise ValueError('Invalid diversion demand switch')
            status['diversion_demands_enabled']=enabled
            if not enabled:
                import pandas as pd
                from baseline_configuration import legacy_values
                legacy=legacy_values(watershed,alternative)
                for key,default in [('diversionConfigCSV','scripts/externalRules/DiversionConfig_ALT.csv'),('withdrawalConfigCSV','scripts/externalRules/WithdrawalConfig.csv')]:
                    path=Path(overrides.get(key,legacy.get(key,default)))
                    if not path.is_absolute():path=watershed/path
                    table=pd.read_csv(path,comment='#')
                    for column in table:
                        if column not in ('Month','Day','Notes','NOTES'):table[column]=0.
                    target=directory/(key+'-disabled.csv');table.to_csv(target,index=False);overrides[key]=str(target)
        checker.configPath=lambda configRoot,altConfig,key,default:overrides.get(key,original(configRoot,altConfig,key,default))
        checker.main(str(directory))
        if signature(source)!=before:raise ValueError('Simulation results changed during check')
        report=directory/'report.html'
        if not report.is_file():raise ValueError('Model check did not create a report')
        status['status']='complete';status['report']=str(report)
        return report
    except BaseException as error:
        status['error']=str(error);raise
    finally:
        atomic_json(destination/'check-context.json',status)
