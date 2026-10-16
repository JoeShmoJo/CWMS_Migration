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
        self.context=standalone.context(self.root,'Con_Season','Test_simulation')
        self.sim=Path(self.context['dss_path']).parent

    def test_menu_job_uses_applied_browser_settings_even_when_legacy_config_is_broken(self):
        import subprocess
        config=standalone.current(self.sim,self.scripts,self.context)
        config['standalone_workflow']={'plot_trial':4,'comparison_trials':[0,4],
            'osi_source_member':2008,'plot_reference_lines':{'DET':{'IRRM':1558.5}}}
        editor.apply_configuration(self.sim,self.context,config,self.scripts)
        # Job source paths are preserved; import and reload must both resolve
        # the private compatibility module, never the old watershed CONFIG.py.
        (self.scripts/'CONFIG.py').write_text('This is deliberately invalid Python!')
        (self.scripts/'MainstemAugmentation.py').write_text("import CONFIG as cfg\nimport importlib,json\nfrom pathlib import Path\nimportlib.reload(cfg)\nPath(__file__).resolve().parents[2].joinpath('captured.json').write_text(json.dumps({'simulation':cfg.SIM_NAME,'alternative':cfg.ALTERNATIVE_NAME_STEP1,'osi':cfg.ENSEMBLE_YEAR_TO_COPY,'config_source':cfg.__file__}))\n")
        result=subprocess.run([sys.executable,str(self.scripts/'standalone_jobs.py'),'--watershed',str(self.root),
            '--simulation','Test_simulation','--alternative','Con_Season','--job','augmentation'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        captured=json.loads((self.root/'captured.json').read_text())
        self.assertEqual(captured['simulation'],'Test_simulation')
        self.assertEqual(captured['alternative'],'Con_Season')
        self.assertEqual(captured['osi'],2008)
        self.assertNotEqual(Path(captured['config_source']),self.scripts/'CONFIG.py')
        self.assertEqual((self.scripts/'CONFIG.py').read_text(),'This is deliberately invalid Python!')

    def test_standalone_browser_serves_and_saves_job_settings(self):
        import queue,threading,urllib.request
        from unittest.mock import patch
        urls=queue.Queue();errors=[]
        def serve():
            try:editor.serve_editor(self.scripts,self.context)
            except Exception as error:errors.append(error)
        with patch('webbrowser.open',side_effect=urls.put):
            thread=threading.Thread(target=serve,daemon=True);thread.start()
            url=urls.get(timeout=10);base,token=url.rsplit('/',1)
            def post(endpoint,payload):
                request=urllib.request.Request(base+endpoint,data=json.dumps(payload).encode(),headers={'X-Editor-Token':token},method='POST')
                with urllib.request.urlopen(request) as response:return json.loads(response.read())
            try:
                with urllib.request.urlopen(url) as response:page=response.read().decode()
                self.assertIn('Standalone job settings',page)
                self.assertIn('standaloneJobDefaults',page)
                self.assertTrue('Standalone target: Test_simulation / Con_Season' in page,'Browser target differs')
                config=standalone.current(self.sim,self.scripts,self.context)
                config['standalone_workflow']['osi_source_member']=2005
                saved=post('/save',config)
                loaded=post('/load',{'id':saved['id']})
                self.assertEqual(loaded['standalone_workflow']['osi_source_member'],2005)
                post('/apply',loaded)
                active=standalone.current(self.sim,self.scripts,self.context)
                self.assertEqual(active['standalone_workflow']['osi_source_member'],2005)
            finally:
                request=urllib.request.Request(base+'/close',headers={'X-Editor-Token':token},method='POST')
                urllib.request.urlopen(request).close();thread.join(timeout=10)
            self.assertFalse(thread.is_alive());self.assertEqual(errors,[])

    def test_legacy_windows_crlf_member_scripts_are_migrated_without_replacing_mappings(self):
        for name in ('RFC_Downloader_Module.py','OSI_Ensemble_Year.py','MainstemAugmentation.py'):
            source=(ROOT/'standalone-review/scripts/ExternalPython'/name).read_text()
            (self.scripts/name).write_bytes(source.replace('\n','\r\n').encode())
        installer.install(self.root)
        self.assertIn('TARGET_ENSEMBLE_YEAR = 3003',(self.scripts/'OSI_Ensemble_Year.py').read_text())
        self.assertIn('computed_standalone_members',(self.scripts/'MainstemAugmentation.py').read_text())
        self.assertIn('GROUP_TO_BPART',(self.scripts/'RFC_Downloader_Module.py').read_text())
        self.assertNotIn('df1d[2026] = pct.quantile',(self.scripts/'RFC_Downloader_Module.py').read_text())

    def test_normal_workflow_installs_and_opens_without_config_py(self):
        (self.scripts/'CONFIG.py').unlink()
        installer.install(self.root)
        config=standalone.current(self.sim,self.scripts,self.context)
        self.assertEqual(config['standalone_workflow'],{'run_type':'ensemble','osi_source_member':2011})
        self.assertTrue((self.scripts/'standalone_results.py').is_file())

    def test_por_settings_have_no_osi_requirement_and_never_launch_ensemble_extract(self):
        import standalone_jobs as jobs
        config=standalone.current(self.sim,self.scripts,self.context)
        config['standalone_workflow']={'run_type':'por'}
        jobs.validate(config['standalone_workflow'])
        editor.apply_configuration(self.sim,self.context,config,self.scripts)
        with self.assertRaisesRegex(ValueError,'No OSI copy'):
            jobs.execute(self.root,'Test_simulation','Con_Season','extract','por')

    def test_por_augmentation_launches_with_private_por_settings(self):
        from unittest.mock import patch
        import standalone_jobs as jobs
        config=standalone.current(self.sim,self.scripts,self.context)
        config['standalone_workflow']={'run_type':'por'}
        editor.apply_configuration(self.sim,self.context,config,self.scripts)
        requests=[]
        def child(command,**kwargs):
            requests.append(json.loads(Path(command[-1]).read_text()))
        with patch('subprocess.run',side_effect=child):
            jobs.execute(self.root,'Test_simulation','Con_Season','augmentation','por')
        self.assertEqual(len(requests),1)
        self.assertEqual(requests[0]['values']['RUN_TYPE'],'por')
        self.assertTrue(requests[0]['script'].endswith('MainstemAugmentation.py'))
        installer.install(self.root)  # repeated installation preserves the hook
        source=(self.scripts/'MainstemAugmentation.py').read_text()
        self.assertEqual(source.count('from standalone_por_augmentation import'),1)
        self.assertTrue((self.scripts/'standalone_por_augmentation.py').is_file())

    def test_job_settings_validation_and_unapplied_target_rejected(self):
        import standalone_jobs as jobs
        settings=jobs.defaults(self.scripts)
        settings['osi_source_member']=True
        with self.assertRaisesRegex(ValueError,'whole number'):jobs.validate(settings)
        with self.assertRaisesRegex(ValueError,'Apply settings'):jobs.execute(self.root,'Test_simulation','Con_Season','augmentation')
        config=standalone.current(self.sim,self.scripts,self.context)
        editor.apply_configuration(self.sim,self.context,config,self.scripts)
        with self.assertRaisesRegex(ValueError,'alternative differs'):jobs.execute(self.root,'Test_simulation','Other','augmentation')

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

    def test_mode_round_trip_preserves_rules_setup_and_standalone_state_variable(self):
        rule=self.root/'scripts/_standalone_baseline_originals/externalRules/DraftToRC.py'
        original=rule.read_bytes()
        sv=self.root/'scripts/externalSVs/MainstemFlowAugSV.py'
        original_sv=sv.read_bytes()
        downloader=self.scripts/'RFC_Downloader_Module.py'
        original_downloader=downloader.read_bytes()
        self.assertIn(b'add_percentile_members',original_downloader)
        self.assertIn('TARGET_ENSEMBLE_YEAR = 3003',(self.scripts/'OSI_Ensemble_Year.py').read_text())
        self.assertIn('computed_standalone_members',(self.scripts/'MainstemAugmentation.py').read_text())
        installer.install(self.root,'rts')
        active=self.root/'scripts/externalRules/DraftToRC.py'
        self.assertIn(b'from rts_baseline_runtime import',active.read_bytes())
        self.assertNotIn(b'from standalone_baseline_runtime import',active.read_bytes())
        self.assertEqual((self.root/'scripts/_rts_baseline_originals/externalRules/DraftToRC.py').read_bytes(),original)
        installer.install(self.root,'rts')
        installer.install(self.root,'standalone')
        self.assertEqual(sv.read_bytes(),original_sv)
        self.assertEqual(downloader.read_bytes(),original_downloader)
        self.assertEqual(active.read_bytes().count(b'_rts_original_initRuleScript = initRuleScript'),1)
        setup=(self.root/'scripts/externalSVs/Alternative_Setup.py').read_text()
        self.assertNotIn('from rts_baseline_runtime import',setup)
        self.assertEqual(setup.count('configDict.update(alternative_overrides(network))'),1)
        self.assertEqual((self.scripts/'CONFIG.py').read_text(),'SIM_NAME="Test simulation"\n')

    def test_installed_archive_works_in_fresh_python_without_repository_imports(self):
        import subprocess
        # -I excludes PYTHONPATH and repository/test imports. Only the installed
        # watershed supplies workflow modules; DSS itself is a controlled fixture.
        script=r"""
import sys
from pathlib import Path
from types import SimpleNamespace
import pandas as pd
sys.path.insert(0,sys.argv[1])
import standalone_results
root=Path(sys.argv[2]);source=root/'simulation.dss';source.write_bytes(b'native results')
paths=['//LOOKOUT POINT-POOL/'+parameter+'/01Jan2026/1DAY/C:001985|CON_SEASON0/' for parameter in ('ELEV','FLOW-OUT')]
class DSS:
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def getPathnameList(self,*args):return paths
    def read_ts(self,path,**kwargs):
        return SimpleNamespace(pytimes=pd.date_range('2026-10-16',periods=3),values=[100.,101.,102.],
            units='FT' if '/ELEV/' in path else 'CFS',type='INST-VAL' if '/ELEV/' in path else 'PER-AVER')
sys.modules['pydsstools.heclib.dss']=SimpleNamespace(HecDss=SimpleNamespace(Open=lambda filename:DSS()))
assert standalone_results.outputs(root,'ensemble')==['CON_SEASON0']
result=standalone_results.capture(root,'Con_Season','Installed archive test','CON_SEASON0','baseline',confirmed=True)
assert result['members']==[1985]
assert (root/'standalone-results'/result['id']/'capture.json').is_file()
assert source.read_bytes()==b'native results'
"""
        result=subprocess.run([sys.executable,'-I','-c',script,str(self.scripts),str(self.sim)],
                              cwd=self.root,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)

    def test_portable_package_embedded_installer_and_manifest(self):
        spec=importlib.util.spec_from_file_location('workflow_package',ROOT/'migration-review/Package-Workflow.py')
        builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
        notes=self.root/'PROJECT_LOCAL_NOTES.md'
        notes.write_text('Keep my local findings')
        kit=builder.package(self.root)
        self.assertEqual(notes.read_text(),'Keep my local findings')
        for name in ('WORKFLOW_PACKAGE.md','PROJECT_START_HERE.md','WORKFLOW_SOP.md','STANDALONE_WORKFLOW_REFERENCE.md','RTS_WORKFLOW_REFERENCE.md','RTS_IMPORT_VALIDATION.md','Package-Workflow.py'):
            self.assertTrue((kit/name).is_file(),name)
        self.assertTrue((self.root/'WORKFLOW_README.md').is_file())
        self.assertTrue((self.root/'WORKFLOW_README.html').is_file())
        self.assertEqual((self.root/'PROJECT_RESUME.md').read_bytes(),(kit/'PROJECT_RESUME.md').read_bytes())
        self.assertTrue((kit/'documentation/PROJECT_RESUME.html').is_file())
        html=(kit/'documentation/WORKFLOW_SOP.html').read_text()
        self.assertIn('href="RTS_WORKFLOW_REFERENCE.html"',html)
        self.assertIn('<table>',html)
        self.assertIn('href="RTS_IMPORT_VALIDATION.html"',html)
        handoff=(kit/'documentation/RTS_IMPORT_VALIDATION.html').read_text()
        self.assertIn('Unresolved; inspect actual values',handoff)
        self.assertIn('Not yet tested',handoff)
        self.assertIn('<pre><code>',html)
        self.assertNotIn('<script',html)
        self.assertTrue((kit/'documentation/STANDALONE_WORKFLOW_REFERENCE.html').is_file())
        self.assertTrue((kit/'optional-diversion-postprocess/network.json').is_file())
        self.assertTrue((kit/'documentation/optional-diversion-postprocess-README.html').is_file())
        inventory=json.loads((kit/'installation-inventory.json').read_text())
        self.assertEqual(inventory['watershed'],str(self.root))
        self.assertIn('Test_simulation',[item['folder'] for item in inventory['simulations']])
        self.assertTrue(any(item['path'].replace('\\','/')=='scripts/ExternalPython/CONFIG.py' for item in inventory['installed_script_data_files']))
        import hashlib
        for name,digest in json.loads((kit/'manifest.json').read_text()).items():
            self.assertEqual(hashlib.sha256((kit/name).read_bytes()).hexdigest(),digest)
        spec=importlib.util.spec_from_file_location('embedded_installer',kit/'Install-StandaloneConfiguration.py')
        embedded=importlib.util.module_from_spec(spec);spec.loader.exec_module(embedded)
        embedded.install(self.root,'rts')
        self.assertTrue((self.root/'scripts/RTS_WORKFLOW_MENU.py').is_file())
        self.assertTrue((self.scripts/'run_extraction.py').is_file())
        embedded.install(self.root,'standalone')

    def test_import_alias_and_reject_cycle_and_simulation_escape(self):
        folder=self.root/'scripts/alt_config'
        (folder/'Alias.txt').write_text('@alias HCR1531\n')
        values=editor.legacy_values(self.root,'Alias')
        self.assertEqual(values['irrmTargetElevs']['Hills Creek'],1531)
        (folder/'Cycle.txt').write_text('@alias Cycle\n')
        with self.assertRaisesRegex(ValueError,'cycle'):editor.legacy_values(self.root,'Cycle')
        with self.assertRaises(ValueError):standalone.context(self.root,'Con_Season','../other')

    def test_explicit_target_overrides_config_and_applies_only_selected_simulation(self):
        selected=self.root/'rss/Flood_96_3hour'
        selected.mkdir()
        target=standalone.context(self.root,'Temp3Hour','Flood_96_3hour')
        self.assertEqual(Path(target['dss_path']).parent,selected)
        self.assertEqual(target['model_alternative'],'Temp3Hour')
        config=standalone.import_legacy(selected,self.scripts,'Con_Season')
        config['rules']['irrm']['settings']['target_elevation_ft']['Hills Creek']=1520
        editor.apply_configuration(selected,target,config,self.scripts)
        loaded=standalone.current(selected,self.scripts,target)
        self.assertEqual(loaded['rules']['irrm']['settings']['target_elevation_ft']['Hills Creek'],1520)
        self.assertFalse((self.sim/'standalone-baseline-config-active.json').exists())
        self.assertEqual((self.scripts/'CONFIG.py').read_text(),'SIM_NAME="Test simulation"\n')

if __name__=='__main__':unittest.main()
