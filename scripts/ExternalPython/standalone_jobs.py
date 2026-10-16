"""Run standalone jobs using applied browser settings, never the shared CONFIG.py.

Each child invocation receives a private, temporary CONFIG compatibility module.
Legacy importlib.reload(CONFIG) resolves that same private module.
"""
import argparse
import json
from pathlib import Path
import runpy
import sys
import tempfile

DEFAULTS={'run_type':'ensemble','osi_source_member':2011}
JOBS={'extract':['CWMS_Downloader_Module.py','RFC_Downloader_Module.py',
                 'Dummy_0_and_WY_Abundant_Module.py','OSI_Ensemble_Year.py'],
      'augmentation':['MainstemAugmentation.py']}


def validate(settings):
    # Older saved sets may carry retired plot controls. They are ignored, never
    # consulted by the saved-run archive/plot workflow.
    allowed={'run_type','osi_source_member','plot_trial','comparison_trials','plot_reference_lines'}
    if not isinstance(settings,dict) or not set(settings)<=allowed :
        raise ValueError('Invalid standalone workflow settings')
    if settings.get('run_type','ensemble') not in ('ensemble','por'):raise ValueError('Invalid run type')
    if settings.get('run_type','ensemble')=='por':return settings
    value=settings.get('osi_source_member')
    if isinstance(value,bool) or not isinstance(value,int) or value<0:raise ValueError('Expected nonnegative whole number: osi_source_member')
    if value==3003:raise ValueError('OSI source member cannot be destination member 3003')
    return settings


def defaults(scripts):
    # No dependency on the watershed CONFIG.py. Review the source member before
    # extraction; targets always come from the selected simulation/alternative.
    return dict(DEFAULTS)


def include(configuration,scripts):
    import copy
    result=copy.deepcopy(configuration)
    settings=result.get('standalone_workflow',defaults(scripts));validate(settings)
    result['standalone_workflow']={'run_type':settings.get('run_type','ensemble'),'osi_source_member':settings.get('osi_source_member')}
    return result


def compatibility(context,settings):
    validate(settings)
    return {'SIM_NAME':context['run_name'],'ALTERNATIVE_NAME_STEP1':context['model_alternative'],
            'ENSEMBLE_YEAR_TO_COPY':settings.get('osi_source_member'),'RUN_TYPE':settings.get('run_type','ensemble')}


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


def execute(watershed,simulation,alternative,job,run_type=None):
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
    settings=data['standalone_workflow'];mode=settings.get('run_type','ensemble')
    if run_type is not None and mode!=run_type:raise ValueError('Run type differs from applied configuration; open Baseline Configuration and Apply for the selected mode')
    if mode=='por' and job=='extract':
        raise ValueError('RFC ensemble extraction is unavailable in POR mode. Use existing POR inputs. No OSI copy was run.')
    values=compatibility(ctx,settings)
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
    parser.add_argument('--run-type',choices=('ensemble','por'))
    parser.add_argument('--watershed',type=Path)
    parser.add_argument('--simulation');parser.add_argument('--alternative');parser.add_argument('--job',choices=tuple(JOBS))
    args=parser.parse_args()
    if args.request:
        request=json.loads(args.request.read_text());script=Path(request['script'])
        run_script(script,script.parent,request['values'])
    else:
        if not all((args.watershed,args.simulation,args.alternative,args.job)):parser.error('watershed, simulation, alternative and job are required')
        execute(args.watershed,args.simulation,args.alternative,args.job,args.run_type)
