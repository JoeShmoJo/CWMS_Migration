"""Verify the delivered kit, offline guides and embedded mode transitions."""
import hashlib
from html.parser import HTMLParser
import importlib.util
import json
from pathlib import Path
import re
import shutil
import tempfile
import unittest
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT/'scripts/workflow-kit'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PortableDocumentationTests(unittest.TestCase):
    def test_packaged_kit_is_self_contained_and_switches_modes(self):
        with tempfile.TemporaryDirectory() as temporary:
            watershed = Path(temporary)/'model'
            shutil.copytree(ROOT/'standalone-review/scripts', watershed/'scripts')
            (watershed/'rss/Test_simulation').mkdir(parents=True)
            notes = watershed/'PROJECT_LOCAL_NOTES.md'
            notes.write_text('Operator findings must survive')
            config = watershed/'scripts/ExternalPython/CONFIG.py'
            original_config = config.read_bytes()
            builder = load('delivered_workflow_builder', KIT/'Package-Workflow.py')
            kit = builder.package(watershed)
            for entry in [watershed/'WORKFLOW_README.html', watershed/'scripts/START-HERE.html',
                          kit/'documentation/index.html', kit/'documentation/PIPELINE.html']:
                self.assertTrue(entry.is_file(), str(entry))
            self.assertFalse((kit/'PROJECT_START_HERE.md').exists())
            self.assertTrue((kit/'documentation/sources/PROJECT_START_HERE.md').is_file())
            self.assertEqual(notes.read_text(), 'Operator findings must survive')
            for name, digest in json.loads((kit/'manifest.json').read_text()).items():
                self.assertEqual(hashlib.sha256((kit/name).read_bytes()).hexdigest(), digest, name)
            installer = load('delivered_workflow_installer', kit/'Install-StandaloneConfiguration.py')
            installer.install(watershed, 'rts')
            self.assertTrue((watershed/'scripts/RTS_WORKFLOW_MENU.py').exists())
            self.assertTrue((watershed/'scripts/ExternalPython/rts_workflow.py').exists())
            self.assertEqual(json.loads((watershed/'scripts/workflow-mode.json').read_text())['mode'], 'rts')
            installer.install(watershed, 'standalone')
            self.assertEqual(json.loads((watershed/'scripts/workflow-mode.json').read_text())['mode'], 'standalone')
            self.assertEqual(config.read_bytes(), original_config)
            # Repackaging from the embedded copy preserves notes and the previous kit.
            embedded = load('repack_delivered_workflow', kit/'Package-Workflow.py')
            embedded.package(watershed)
            self.assertTrue(list((watershed/'scripts').glob('workflow-kit-previous-*')))
            self.assertEqual(notes.read_text(), 'Operator findings must survive')

    def test_checker_fallback_stays_in_local_watershed(self):
        import ast
        from unittest.mock import patch
        code = ast.parse((KIT/'model_check/check_model.py').read_text())
        function = next(node for node in code.body if isinstance(node, ast.FunctionDef) and node.name=='findConfigRoot')
        import os, sys
        with tempfile.TemporaryDirectory() as temporary:
            parent=Path(temporary)
            (parent/'scripts/alt_config').mkdir(parents=True)
            model=parent/'separate-model'
            (model/'scripts/alt_config').mkdir(parents=True)
            for relative in ['scripts/model_check','scripts/workflow-kit/model_check']:
                location=model/relative;location.mkdir(parents=True)
                scope={'CONFIG_ROOT':'','os':os,'sys':sys,'_here':lambda: str(location)}
                exec(compile(ast.Module(body=[function],type_ignores=[]),'<checker>','exec'),scope)
                self.assertEqual(scope['findConfigRoot']({'watershed_dir':str(parent)}),str(model))
            shutil.rmtree(model/'scripts/alt_config')
            with self.assertRaises(SystemExit):scope['findConfigRoot']({'watershed_dir':str(parent)})

    def test_all_guide_links_and_fragments_are_local_and_resolve(self):
        pages = list((KIT/'documentation').glob('*.html'))+[ROOT/'scripts/START-HERE.html']
        class Parser(HTMLParser):
            def __init__(self):
                super().__init__(); self.links=[]; self.ids=set()
            def handle_starttag(self, tag, attrs):
                for name, value in attrs:
                    if name in ('href','src') and value:self.links.append(value)
                    if name=='id':self.ids.add(value)
        for page in pages:
            parser=Parser();parser.feed(page.read_text())
            for link in parser.links:
                parts=urlsplit(link)
                self.assertFalse(parts.scheme or parts.netloc, (page.name,link))
                target=(page.parent/unquote(parts.path)).resolve() if parts.path else page
                self.assertTrue(target.exists(), (page.name,link))
                self.assertTrue(target.is_relative_to(ROOT/'scripts'), (page.name,link))
                if parts.fragment and target.suffix=='.html':
                    other=Parser();other.feed(target.read_text())
                    self.assertIn(parts.fragment,other.ids,(page.name,link))

    def test_project_scripts_and_markdown_have_no_external_project_instructions(self):
        pattern=re.compile(r'\b(?:git|github|repo|repository|repositories)\b',re.I)
        for file in (ROOT/'scripts').rglob('*'):
            if file.suffix.lower() in {'.py','.md','.ps1','.bat','.sh'}:
                self.assertIsNone(pattern.search(file.read_text(encoding='utf-8-sig')),str(file))
