import importlib.util
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('execution_switch',Path(__file__).resolve().parents[1]/'migration-review/ExternalPython/diagnose_baseline_execution.py')
execution=importlib.util.module_from_spec(spec);spec.loader.exec_module(execution)

class ExecutionSwitchTests(unittest.TestCase):
    def test_switch_and_restore_preserve_configuration_and_dss(self):
        with tempfile.TemporaryDirectory() as directory:
            watershed=Path(directory)/'watershed/model';root=Path(directory)/'forecast';root.mkdir()
            originals=watershed/'scripts/_rts_baseline_originals/externalRules';originals.mkdir(parents=True)
            rules=watershed/'scripts/externalRules';rules.mkdir()
            for name in execution.MODULES:
                (originals/(name+'.py')).write_text('original '+name)
                (rules/(name+'.py')).write_text('adapter '+name)
                (rules/(name+'$py.class')).write_bytes(b'compiled')
            marker=root/'rts-baseline-config-active.json';marker.write_text('{"id":"test"}')
            live=root/'forecast.dss';live.write_bytes(b'unchanged')
            execution.switch(watershed,root,'original')
            self.assertFalse(marker.exists())
            self.assertEqual((rules/'DraftToRC.py').read_text(),'original DraftToRC')
            with self.assertRaises(ValueError): execution.switch(watershed,root,'original')
            execution.switch(watershed,root,'configured')
            self.assertEqual(marker.read_text(),'{"id":"test"}')
            self.assertEqual((rules/'DraftToRC.py').read_text(),'adapter DraftToRC')
            self.assertEqual(live.read_bytes(),b'unchanged')
            self.assertFalse((root/'baseline-execution-test.json').exists())
            self.assertFalse((rules/'DraftToRC$py.class').exists())
