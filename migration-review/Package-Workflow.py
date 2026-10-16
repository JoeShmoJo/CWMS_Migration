"""Embed a portable, checksummed workflow kit in an existing standalone watershed."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile

HERE=Path(__file__).resolve().parent


def package(watershed):
    watershed=Path(watershed).resolve()
    destination=watershed/'scripts/workflow-kit'
    with tempfile.TemporaryDirectory(prefix='workflow-kit-') as temp:
        stage=Path(temp)/'kit';stage.mkdir()
        for name in ('ExternalPython','baseline-runtime','baseline-editor-design','externalSVs'):
            shutil.copytree(HERE/name,stage/name,ignore=shutil.ignore_patterns('__pycache__','*$py.class','*.pyc'))
        for name in ('Install-StandaloneConfiguration.py','Install-ForecastExtraction.ps1',
                     'STANDALONE_WORKFLOW_MENU.py','RTS_WORKFLOW_MENU.py','RTS_FORECAST_EXTRACT.py',
                     'WORKFLOW_PACKAGE.md','STANDALONE_CONFIGURATION.md','RTS_OPERATOR_SOP.md',
                     'RTS_WORKFLOW_REFERENCE.md','RTS_DATA_IO.md'):
            shutil.copy2(HERE/name,stage/name)
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
        for relative,digest in manifest.items():
            if hashlib.sha256((destination/relative).read_bytes()).hexdigest()!=digest:
                raise ValueError('Packaged checksum mismatch: '+relative)
    print('Portable workflow kit:',destination)
    print('Start with:',destination/'WORKFLOW_PACKAGE.md')
    return destination


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--watershed',required=True,type=Path)
    args=parser.parse_args();package(args.watershed)
