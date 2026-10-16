import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'migration-review/ExternalPython'))
import baseline_configuration as editor
import standalone_configuration as standalone
spec=importlib.util.spec_from_file_location('standalone_installer',ROOT/'migration-review/Install-StandaloneConfiguration.py')
installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)


class StandaloneTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'watershed'
        shutil.copytree(ROOT/'standalone-review/scripts',self.root/'scripts')
        self.scripts=self.root/'scripts/ExternalPython'
        (self.scripts/'CONFIG.py').write_text('SIM_NAME="Test simulation"\n')
        (self.root/'rss/Test_simulation').mkdir(parents=True)
        self.before=(self.root/'scripts/alt_config/_default.txt').read_bytes()
        installer.install(self.root)
        runtime_spec=importlib.util.spec_from_file_location('standalone_baseline_runtime',self.root/'scripts/standalone_baseline_runtime.py')
        self.runtime=importlib.util.module_from_spec(runtime_spec);runtime_spec.loader.exec_module(self.runtime)
        sys.modules['standalone_baseline_runtime']=self.runtime
        self.addCleanup(sys.modules.pop,'standalone_baseline_runtime',None)
        self.context=standalone.context(self.root,'Con_Season')
        self.sim=Path(self.context['dss_path']).parent

    def test_legacy_presets_portable_save_apply_and_reload(self):
        config=standalone.import_legacy(self.sim,self.scripts,'HCR1511')
        self.assertEqual(config['rules']['irrm']['settings']['target_elevation_ft']['Hills Creek'],1511)
        config['name']='One alternative, saved set'
        first=editor.save_library_configuration(self.scripts,config)
        second=editor.save_library_configuration(self.scripts,config)
        self.assertNotEqual(first['id'],second['id'])
        applied=editor.apply_configuration(self.sim,self.context,config,self.scripts)
        self.assertEqual(applied['model_alternative'],'Con_Season')
        reloaded=standalone.current(self.sim,self.scripts,self.context)
        self.assertEqual(reloaded['name'],config['name'])
        self.assertEqual(reloaded['rules']['irrm']['settings']['target_elevation_ft']['Hills Creek'],1511)
        self.assertFalse((self.sim/'rts-baseline-config-active.json').exists())
        self.assertFalse((self.sim/'augmentation-archives').exists())
        self.assertEqual((self.root/'scripts/alt_config/_default.txt').read_bytes(),self.before)

    def test_runtime_reload_scoped_to_simulation_and_alternative_nonensemble(self):
        config=standalone.import_legacy(self.sim,self.scripts,'Con_Season')
        class Store:
            def varPut(self,key,value):pass
        outer=self
        class Network:
            alternative='Con_Season'
            def getAlternative(self):return SimpleNamespace(getName=lambda:':'+self.alternative)
            def getRssRun(self):return SimpleNamespace(getDSSOutputFile=lambda:str(outer.sim/'simulation.dss'),getOutputFPart=lambda:'CON_SEASON0')
            def makeAbsolutePathFromWatershed(self,path):return str(outer.root/path)
            def getStateVariable(self,name):return Store()
            def printMessage(self,message):pass
        network=Network();namespace={'DAYS_LOOKAHEAD':3,'_rts_original_initRuleScript':lambda rule,network:True}
        for days in (7,5):
            config['rules']['draft_to_rc']['settings']['days_lookahead']=days
            pointer=editor.apply_configuration(self.sim,self.context,config,self.scripts)
            self.runtime.initialize_rule('DraftToRC',Store(),network,namespace)
            self.assertEqual(namespace['DAYS_LOOKAHEAD'],days)
            receipts=list((self.sim/pointer['directory']/'initialization-receipts').glob('*.json'))
            self.assertEqual(len(receipts),1)
            self.assertIsNone(json.loads(receipts[0].read_text())['member'])
        network.alternative='HCR1511'
        self.runtime.initialize_rule('DraftToRC',Store(),network,namespace)
        self.assertEqual(namespace['DAYS_LOOKAHEAD'],3)
        outer.sim=outer.root/'rss/Other';outer.sim.mkdir()
        network.alternative='Con_Season'
        self.assertIsNone(self.runtime.active(network))

    def test_installer_repeat_preserves_sources_and_rejects_unknown_setup(self):
        source=self.root/'scripts/_standalone_baseline_originals/externalRules/DraftToRC.py'
        original=source.read_bytes();installer.install(self.root)
        self.assertEqual(source.read_bytes(),original)
        target=self.root/'scripts/externalRules/DraftToRC.py'
        self.assertEqual(target.read_text().count('_rts_original_initRuleScript = initRuleScript'),1)
        setup=self.root/'scripts/externalSVs/Alternative_Setup.py';setup.write_text('unknown setup')
        before=target.read_bytes()
        with self.assertRaisesRegex(ValueError,'initialization differs'):installer.install(self.root)
        self.assertEqual(target.read_bytes(),before)

    def test_import_alias_and_reject_cycle_and_simulation_escape(self):
        folder=self.root/'scripts/alt_config'
        (folder/'Alias.txt').write_text('@alias HCR1531\n')
        values=editor.legacy_values(self.root,'Alias')
        self.assertEqual(values['irrmTargetElevs']['Hills Creek'],1531)
        (folder/'Cycle.txt').write_text('@alias Cycle\n')
        with self.assertRaisesRegex(ValueError,'cycle'):editor.legacy_values(self.root,'Cycle')
        with self.assertRaises(ValueError):standalone.context(self.root,'Con_Season','../other')

if __name__=='__main__':unittest.main()
