import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('prep',HERE/'prepare_config_timing.py')
prep=importlib.util.module_from_spec(spec);spec.loader.exec_module(prep)


class PreparationTests(unittest.TestCase):
    def test_copy_instrument_and_rebase_without_touching_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);install=root/'v2';ws=root/'watershed'
            (install/'jar').mkdir(parents=True)
            app=install/'jar/ResSimApp-4.1.0.jar';app.write_bytes(b'V2 sentinel')
            (install/'compiler-isolation-test.json').write_text(json.dumps({
                'compiler_isolation_version':2,'patched_sha256':hashlib.sha256(app.read_bytes()).hexdigest()}))
            cfile=ws/'scripts/NWDJyLib/cFile.py';cfile.parent.mkdir(parents=True)
            cfile.write_bytes(b'def fileOpenReadClose(path):\n    return [path]\n')
            compiled=cfile.with_name('cFile$py.class');compiled.write_bytes(b'old bytecode')
            rule=ws/'scripts/externalRules/Example.py';rule.parent.mkdir(parents=True)
            rule.write_text('def loadConfig(path):\n    return path\n\ndef runRuleScript(rule, network, step):\n    return None\n')
            mapping=ws/'mapping.fits';mapping.write_text(str(ws/'rss/test/simulation.dss'))
            dss=ws/'simulation.dss';dss.write_bytes(b'\x00'+str(ws).encode())
            before={p.relative_to(ws):p.read_bytes() for p in ws.rglob('*') if p.is_file()}
            dest_install=root/'diagnostic-install';dest_ws=root/'diagnostic-watershed'
            command=[sys.executable,str(HERE/'prepare_config_timing.py'),'--installation',str(install),
                     '--watershed',str(ws),'--destination-installation',str(dest_install),
                     '--destination-watershed',str(dest_ws)]
            result=subprocess.run(command,text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(before,{p.relative_to(ws):p.read_bytes() for p in ws.rglob('*') if p.is_file()})
            self.assertEqual(app.read_bytes(),b'V2 sentinel')
            self.assertIn('CONFIG_READ_TIMING_DIAGNOSTIC',(dest_ws/'scripts/NWDJyLib/cFile.py').read_text())
            self.assertFalse((dest_ws/'scripts/NWDJyLib/cFile$py.class').exists())
            self.assertEqual((dest_ws/'mapping.fits').read_text(),str(dest_ws/'rss/test/simulation.dss'))
            self.assertEqual((dest_ws/'simulation.dss').read_bytes(),dss.read_bytes())
            self.assertTrue((dest_install/'jar/config-read-timing-diagnostic.jar').exists())
            self.assertFalse(json.loads((dest_ws/'config-read-timing-diagnostic.json').read_text())['cache_enabled'])
            result=subprocess.run(command,text=True,capture_output=True)
            self.assertNotEqual(result.returncode,0)

    def test_only_top_level_loaders_are_selected(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws=Path(tmp);cfile=ws/'scripts/NWDJyLib/cFile.py';cfile.parent.mkdir(parents=True)
            cfile.write_text('def fileOpenReadClose(path): pass\n')
            rule=ws/'scripts/externalRules/Example.py';rule.parent.mkdir(parents=True)
            rule.write_text('def loadDailyConfig(path): pass\nclass Model:\n    def loadConfig(self): pass\ndef runRuleScript(rule): pass\n')
            selected=prep.plans(ws)
            self.assertEqual(selected[1][2],['loadDailyConfig'])
            rule.write_text(rule.read_text()+'\n# CONFIG_READ_TIMING_DIAGNOSTIC\n')
            with self.assertRaises(ValueError):prep.plans(ws)


if __name__=='__main__':unittest.main()
