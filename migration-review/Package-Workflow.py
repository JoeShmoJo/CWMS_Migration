"""Embed a portable, checksummed workflow kit in an existing standalone watershed."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import sys
import os
from datetime import datetime, timezone
from importlib import metadata

HERE=Path(__file__).resolve().parent


def inventory(watershed,destination):
    files=[]
    for directory,folders,names in os.walk(watershed/'scripts'):
        folders[:]=[name for name in folders if not name.startswith('workflow-kit')
                     and name not in ('__pycache__','raw_rfc_csv','logs','.git')]
        for name in sorted(names):
            path=Path(directory)/name
            if path.suffix.lower() in ('.py','.csv','.json','.pkl','.txt'):
                files.append({'path':str(path.relative_to(watershed)),
                              'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                              'bytes':path.stat().st_size})
    rss=watershed/'rss'
    simulations=[]
    if rss.is_dir():
        for folder in sorted(rss.iterdir()):
            if folder.is_dir():
                dss=folder/'simulation.dss'
                simulations.append({'folder':folder.name,'path':str(folder),
                                    'simulation_dss_exists':dss.is_file(),
                                    'simulation_dss_bytes':dss.stat().st_size if dss.is_file() else None})
    packages=sorted([{'name':dist.metadata.get('Name','unknown'),'version':dist.version}
                     for dist in metadata.distributions()],key=lambda item:item['name'].lower())
    data={'created_utc':datetime.now(timezone.utc).isoformat(),'watershed':str(watershed),
          'mode':'standalone','python_executable':sys.executable,'python_version':sys.version,
          'python_packages':packages,'simulations':simulations,'installed_script_data_files':files,
          'scope':'Packaging-time inventory. No DSS records read; no credentials captured. Not a compute-success certificate or environment lockfile.'}
    (destination/'installation-inventory.json').write_text(json.dumps(data,indent=2),encoding='utf-8')


def package(watershed):
    watershed=Path(watershed).resolve()
    destination=watershed/'scripts/workflow-kit'
    with tempfile.TemporaryDirectory(prefix='workflow-kit-') as temp:
        stage=Path(temp)/'kit';stage.mkdir()
        for name in ('ExternalPython','baseline-runtime','baseline-editor-design','externalSVs','optional-diversion-postprocess'):
            shutil.copytree(HERE/name,stage/name,ignore=shutil.ignore_patterns('__pycache__','*$py.class','*.pyc','logs'))
        for name in ('Install-StandaloneConfiguration.py','Package-Workflow.py','render_documentation.py',
                     'Install-ForecastExtraction.ps1','Install-BaselineConfiguration.ps1','Install-RunArchives.ps1',
                     'STANDALONE_WORKFLOW_MENU.py','RTS_WORKFLOW_MENU.py','RTS_FORECAST_EXTRACT.py'):
            shutil.copy2(HERE/name,stage/name)
        for doc in HERE.glob('*.md'):
            shutil.copy2(doc,stage/doc.name)
        renderer_spec=importlib.util.spec_from_file_location('workflow_docs',stage/'render_documentation.py')
        renderer=importlib.util.module_from_spec(renderer_spec);renderer_spec.loader.exec_module(renderer)
        renderer.build(stage)
        manifest={str(p.relative_to(stage)):hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in sorted(stage.rglob('*')) if p.is_file()}
        (stage/'manifest.json').write_text(json.dumps(manifest,indent=2))
        spec=importlib.util.spec_from_file_location('workflow_installer',stage/'Install-StandaloneConfiguration.py')
        installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)
        installer.install(watershed,'standalone')
        # Preserve a previous kit without copying the large watershed or DSS outputs.
        if destination.exists():
            import uuid
            destination.rename(destination.with_name('workflow-kit-previous-'+uuid.uuid4().hex[:8]))
        shutil.copytree(stage,destination)
        inventory(watershed,destination)
        entry=watershed/'WORKFLOW_README.md'
        if not entry.exists():
            entry.write_text('# Willamette workflow documentation\n\nStart with [project handoff](scripts/workflow-kit/PROJECT_START_HERE.md).\n\n[Operator SOP](scripts/workflow-kit/WORKFLOW_SOP.md) · [Standalone reference](scripts/workflow-kit/STANDALONE_WORKFLOW_REFERENCE.md) · [RTS reference](scripts/workflow-kit/RTS_WORKFLOW_REFERENCE.md)\n',encoding='utf-8')
        (watershed/'WORKFLOW_README.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>Willamette workflow documentation</title><meta http-equiv="refresh" content="0;url=scripts/workflow-kit/documentation/PROJECT_START_HERE.html"><p><a href="scripts/workflow-kit/documentation/PROJECT_START_HERE.html">Open standalone and RTS documentation</a></p></html>',encoding='utf-8')
        notes=watershed/'PROJECT_LOCAL_NOTES.md'
        if not notes.exists():notes.write_text('# Local project notes\n\nRecord local validation, dates, application versions, target simulations/alternatives, configuration IDs, changes and unresolved issues here. This file is not overwritten by packaging.\n',encoding='utf-8')
        for relative,digest in manifest.items():
            if hashlib.sha256((destination/relative).read_bytes()).hexdigest()!=digest:
                raise ValueError('Packaged checksum mismatch: '+relative)
    print('Portable workflow kit:',destination)
    print('Start with:',watershed/'WORKFLOW_README.html')
    return destination


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--watershed',required=True,type=Path)
    args=parser.parse_args();package(args.watershed)
