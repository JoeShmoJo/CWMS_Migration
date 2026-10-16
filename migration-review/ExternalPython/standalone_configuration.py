"""Standalone entry point for the shared baseline editor; no Java modifications."""
import argparse
import ast
import json
from pathlib import Path

import baseline_configuration as editor


def current(root,scripts,context):
    marker=Path(root)/'standalone-baseline-config-active.json'
    if marker.exists():
        pointer=json.loads(marker.read_text())
        if pointer.get('model_alternative') != context['model_alternative']:
            raise ValueError('This simulation has settings applied to another alternative; select that alternative or use another simulation')
    from standalone_jobs import include
    return include(editor.current_configuration(root,scripts,context['model_alternative'],
        'standalone-baseline-config-active.json','_standalone_baseline_originals'),scripts)


def import_legacy(root,scripts,alternative):
    # Use a deliberately nonexistent marker location: import presets must not
    # return the currently applied set instead of the requested legacy settings.
    import tempfile
    with tempfile.TemporaryDirectory(prefix='standalone-preset-') as empty:
        return editor.current_configuration(Path(empty),scripts,alternative,
            'standalone-baseline-config-active.json','_standalone_baseline_originals')


def context(watershed,alternative,simulation=None):
    watershed=Path(watershed).resolve()
    config=watershed/'scripts/ExternalPython/CONFIG.py'
    if simulation is None:
        tree=ast.parse(config.read_text(encoding='utf-8-sig'))
        for node in tree.body:
            if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='SIM_NAME' for t in node.targets):
                simulation=ast.literal_eval(node.value)
    if not isinstance(simulation,str) or not simulation or Path(simulation).name!=simulation or simulation in ('.','..') or any(c in simulation for c in ('/','\\',':')):
        raise ValueError('SIM_NAME must be a simple simulation name')
    if not alternative or any(c in alternative for c in ('/','\\',':')):
        raise ValueError('Use the model alternative name, for example Con_Season')
    simulation_dir=watershed/'rss'/simulation.replace(' ','_')
    if not simulation_dir.is_dir():
        raise ValueError('Standalone simulation directory missing: '+str(simulation_dir))
    return {'mode':'standalone','watershed':str(watershed),'model_alternative':alternative,
            'run_name':simulation,'forecast_name':'Standalone ResSim',
            'dss_path':str(simulation_dir/'simulation.dss')}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--watershed',required=True,type=Path)
    parser.add_argument('--alternative',required=True)
    parser.add_argument('--simulation',required=True,help='Existing simulation folder under watershed/rss; must match ResSim Simulation Control')
    args=parser.parse_args()
    scripts=args.watershed.resolve()/'scripts/ExternalPython'
    editor.serve_editor(scripts,context(args.watershed,args.alternative,args.simulation))
