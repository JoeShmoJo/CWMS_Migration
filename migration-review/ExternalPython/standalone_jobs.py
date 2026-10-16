"""Run standalone jobs using applied browser settings, never the shared CONFIG.py.

Each child invocation receives a private, temporary CONFIG compatibility module.
Legacy importlib.reload(CONFIG) resolves that same private module.
"""
import argparse
import ast
import json
import math
from pathlib import Path
import runpy
import sys
import tempfile

DEFAULTS={'plot_trial':1,'comparison_trials':[0,1],'osi_source_member':2011,'plot_reference_lines':{}}
LEGACY={'TRIAL':'plot_trial','TRIAL_SUFFIXES':'comparison_trials',
        'ENSEMBLE_YEAR_TO_COPY':'osi_source_member','H_LINE_DICT':'plot_reference_lines'}
JOBS={'extract':['CWMS_Downloader_Module.py','RFC_Downloader_Module.py',
                 'Dummy_0_and_WY_Abundant_Module.py','OSI_Ensemble_Year.py'],
      'augmentation':['MainstemAugmentation.py'],'plot':['Ensemble_Plots.py'],
      'compare':['ALT_COMPARISON_PLOTS.py']}


def validate(settings):
    if not isinstance(settings,dict) or set(settings)!=set(DEFAULTS):raise ValueError('Invalid standalone workflow settings')
    for name in ('plot_trial','osi_source_member'):
        value=settings[name]
        if isinstance(value,bool) or not isinstance(value,int) or value<0:raise ValueError('Expected nonnegative whole number: '+name)
    trials=settings['comparison_trials']
    if not isinstance(trials,list) or not trials or any(isinstance(v,bool) or not isinstance(v,int) or v<0 for v in trials) or len(set(trials))!=len(trials):
        raise ValueError('Comparison trials must be a nonempty list of distinct nonnegative integers')
    lines=settings['plot_reference_lines']
    if not isinstance(lines,dict):raise ValueError('Plot reference lines must be a reservoir-to-label/value map')
    for reservoir,values in lines.items():
        if not isinstance(reservoir,str) or not reservoir.strip() or not isinstance(values,dict):raise ValueError('Invalid plot reference lines')
        for label,value in values.items():
            if not isinstance(label,str) or not label.strip() or isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):raise ValueError('Plot reference lines require named finite numbers')
    return settings


def defaults(scripts):
    import copy
    settings=copy.deepcopy(DEFAULTS)
    path=Path(scripts)/'CONFIG.py'
    if path.is_file():
        # Read literals only. Never execute an old configuration or copy its target.
        for node in ast.parse(path.read_text(encoding='utf-8-sig')).body:
            if not isinstance(node,ast.Assign):continue
            for target in node.targets:
                if isinstance(target,ast.Name) and target.id in LEGACY:
                    settings[LEGACY[target.id]]=ast.literal_eval(node.value)
    return validate(settings)


def include(configuration,scripts):
    import copy
    result=copy.deepcopy(configuration)
    if 'standalone_workflow' not in result:result['standalone_workflow']=defaults(scripts)
    validate(result['standalone_workflow'])
    return result


def compatibility(context,settings):
    validate(settings)
    return {'SIM_NAME':context['run_name'],'ALTERNATIVE_NAME_STEP1':context['model_alternative'],
            'TRIAL':settings['plot_trial'],'TRIAL_SUFFIXES':settings['comparison_trials'],
            'ENSEMBLE_YEAR_TO_COPY':settings['osi_source_member'],'H_LINE_DICT':settings['plot_reference_lines']}


def run_script(script,scripts,values):
    """Keep the actual script location for its watershed-relative path logic."""
    old_path=sys.path[:];old_argv=sys.argv[:];old_config=sys.modules.pop('CONFIG',None)
    try:
        with tempfile.TemporaryDirectory(prefix='standalone-job-config-') as directory:
            path=Path(directory)/'CONFIG.py'
            path.write_text('\n'.join(name+' = '+repr(value) for name,value in values.items())+'\n',encoding='utf-8')
            sys.path[:]=[directory,str(scripts)]+[p for p in old_path if p!=str(scripts)]
            sys.argv=[str(script)]
            runpy.run_path(str(script),run_name='__main__')
    finally:
        sys.path[:]=old_path;sys.argv[:]=old_argv;sys.modules.pop('CONFIG',None)
        if old_config is not None:sys.modules['CONFIG']=old_config


def execute(watershed,simulation,alternative,job):
    from standalone_configuration import context
    from baseline_configuration import digest_file
    ctx=context(watershed,alternative,simulation);root=Path(ctx['dss_path']).parent
    scripts=Path(watershed).resolve()/'scripts/ExternalPython'
    mode=Path(watershed)/'scripts/workflow-mode.json'
    if mode.exists() and json.loads(mode.read_text())['mode']!='standalone':raise ValueError('Use the RTS workflow menu in RTS mode')
    marker=root/'standalone-baseline-config-active.json'
    if not marker.is_file():raise ValueError('Open Baseline Configuration and Apply settings for this simulation/alternative before running jobs')
    pointer=json.loads(marker.read_text())
    if pointer.get('model_alternative')!=alternative:raise ValueError('Applied alternative differs from menu selection; open configuration and Apply to this target')
    source=root/pointer['directory']/'resolved.json'
    if digest_file(source)!=pointer['resolved_sha256']:raise ValueError('Applied configuration checksum mismatch')
    data=json.loads(source.read_text())
    if 'standalone_workflow' not in data:raise ValueError('Older applied set has no standalone job settings. Open Baseline Configuration, review Standalone job settings, and Apply again')
    values=compatibility(ctx,data['standalone_workflow'])
    paths=[scripts/name for name in JOBS[job]]
    for path in paths:
        if not path.is_file():raise ValueError('Missing job script: '+str(path))
    print('Standalone job target:',ctx['run_name'],'/',alternative,flush=True)
    print('Applied configuration:',pointer['id'],flush=True)
    print('Job settings:',json.dumps(values),flush=True)
    # Extraction is a sequence of fresh interpreters so one legacy script cannot
    # retain or mutate another script's module state.
    import subprocess
    for path in paths:
        print('Running:',path.name,flush=True)
        with tempfile.TemporaryDirectory(prefix='standalone-job-') as directory:
            request=Path(directory)/'request.json';request.write_text(json.dumps({'script':str(path),'values':values}))
            subprocess.run([sys.executable,'-u',str(Path(__file__).resolve()),'--request',str(request)],cwd=scripts,check=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request',type=Path)
    parser.add_argument('--watershed',type=Path)
    parser.add_argument('--simulation');parser.add_argument('--alternative');parser.add_argument('--job',choices=tuple(JOBS))
    args=parser.parse_args()
    if args.request:
        request=json.loads(args.request.read_text());script=Path(request['script'])
        run_script(script,script.parent,request['values'])
    else:
        if not all((args.watershed,args.simulation,args.alternative,args.job)):parser.error('watershed, simulation, alternative and job are required')
        execute(args.watershed,args.simulation,args.alternative,args.job)
