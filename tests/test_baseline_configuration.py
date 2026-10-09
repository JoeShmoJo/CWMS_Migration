import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'migration-review/ExternalPython'))
sys.path.insert(0,str(ROOT/'migration-review/baseline-runtime'))
import baseline_configuration as config
import rts_baseline_runtime as runtime


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'forecast';self.root.mkdir()
        self.scripts=Path(self.temp.name)/'watershed/model/scripts/ExternalPython';self.scripts.mkdir(parents=True)
        self.watershed=self.scripts.parent.parent
        shutil.copy2(ROOT/'migration-review/baseline-editor-design/baseline-configuration.example.json',self.scripts)
        shutil.copy2(ROOT/'migration-review/baseline-runtime/rts_baseline_runtime.py',self.scripts.parent)
        self.configuration=config.template(self.scripts)
        self.context={'forecast_name':'test','run_name':'ConSeason','dss_path':str(self.root/'forecast.dss')}
        legacy=self.scripts.parent/'_rts_baseline_originals/externalRules';legacy.mkdir(parents=True)
        for module in config.MODULE_KEYS:
            (legacy/(module+'.py')).write_text('DAYS_LOOKAHEAD=3\ndef initRuleScript(rule,network):\n    rule.varPut("lookahead",DAYS_LOOKAHEAD)\n    return True\ndef runRuleScript(rule,network,step):\n    return DAYS_LOOKAHEAD\n')
        runtime._CACHE.clear()
    def apply(self, configuration=None):
        return config.apply_configuration(self.root,self.context,configuration or self.configuration,self.scripts)
    def network(self, member=1981, root=None):
        watershed=self.watershed;root=root or self.root
        class Store:
            def __init__(self): self.values={}
            def varPut(self,k,v): self.values[k]=v
            def varGet(self,k): return self.values[k]
        store=Store();rule=Store()
        run=SimpleNamespace(getDSSOutputFile=lambda:str(root/'EnsembleRuns'/str(member)/'forecast.dss'),getOutputFPart=lambda:'C:{:06d}|C0'.format(member))
        network=SimpleNamespace(getRssRun=lambda:run,makeAbsolutePathFromWatershed=lambda p:str(watershed/p) if not Path(p).is_absolute() else str(p),getStateVariable=lambda name:store,printMessage=lambda msg:None)
        return network,rule,store
    def test_editor_serves_bound_configuration_and_stops_cleanly(self):
        import queue
        import threading
        import urllib.request
        import urllib.error
        from unittest.mock import patch
        self.apply()
        shutil.copy2(ROOT/'migration-review/baseline-editor-design/editor-mockup.html',self.scripts/'baseline-editor.html')
        urls=queue.Queue()
        errors=[]
        def run():
            try: config.serve_editor(self.scripts,self.context)
            except Exception as exc: errors.append(exc)
        with patch('webbrowser.open',side_effect=lambda url:urls.put(url)):
            thread=threading.Thread(target=run,daemon=True);thread.start()
            url=urls.get(timeout=10);base,token=url.rsplit('/',1)
            with urllib.request.urlopen(url) as response:
                page=response.read().decode()
            self.assertIn('Apply target: test / ConSeason',page)
            self.assertIn('Close Editor',page)
            request=urllib.request.Request(base+'/apply',data=b'{}',method='POST')
            with self.assertRaises(urllib.error.HTTPError) as rejected:
                urllib.request.urlopen(request)
            self.assertEqual(rejected.exception.code,403)
            changed=copy.deepcopy(self.configuration)
            changed['rules']['draft_to_rc']['settings']['days_lookahead']=7
            request=urllib.request.Request(base+'/apply',data=json.dumps(changed).encode(),headers={'X-Editor-Token':token},method='POST')
            with urllib.request.urlopen(request) as response:
                self.assertEqual(response.status,200)
            request=urllib.request.Request(base+'/close',headers={'X-Editor-Token':token},method='POST')
            urllib.request.urlopen(request).close()
            thread.join(timeout=10)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors,[])

    def test_real_configuration_validates_and_does_not_write_live_dss(self):
        live=self.root/'forecast.dss';live.write_bytes(b'original')
        (self.root/'rts-augmentation-active.json').write_text('{}')
        pointer=self.apply()
        self.assertEqual(live.read_bytes(),b'original')
        self.assertFalse((self.root/'rts-augmentation-active.json').exists())
        self.assertEqual(json.loads((self.root/'augmentation-archives/workflow-pending.json').read_text())['mode'],'baseline')
        stage=self.root/pointer['directory'];self.assertTrue((stage/'resolved.json').is_file())
        network,rule,store=self.network()
        runtime.initialize_rule('DraftToRC',rule,network)
        self.assertEqual(rule.varGet('lookahead'),3)
        self.assertIn('NoDraftConfigCSV',store.values)
        with self.assertRaisesRegex(ValueError,'members'):
            config.check_initialization(self.root,{'members':[1981,1982],'synthetic_members':[]})
        self.assertEqual(config.check_initialization(self.root,{'members':[1981],'synthetic_members':[]})['id'],pointer['id'])
    def test_changed_settings_reload_and_do_not_mutate_an_existing_rule(self):
        self.apply();network,old,store=self.network();runtime.initialize_rule('DraftToRC',old,network)
        changed=copy.deepcopy(self.configuration);changed['rules']['draft_to_rc']['settings']['days_lookahead']=7
        self.apply(changed);network,new,store=self.network();runtime.initialize_rule('DraftToRC',new,network)
        self.assertEqual(runtime.run_rule(old,network,None),3)
        self.assertEqual(runtime.run_rule(new,network,None),7)
    def test_forecasts_do_not_share_activation(self):
        self.apply();other=self.root.parent/'other';other.mkdir()
        network,rule,store=self.network(root=other)
        self.assertEqual(runtime.alternative_overrides(network),{})
        runtime.initialize_rule('DraftToRC',rule,network)
        self.assertEqual(rule.varGet('lookahead'),3)
        self.assertEqual(store.values,{})
    def test_linked_csv_is_resolved_and_archived_and_missing_link_never_falls_back(self):
        changed=copy.deepcopy(self.configuration);table=changed['rules']['firo_space']['tables']['schedule']
        source=self.watershed/'schedule.csv'
        import csv
        with source.open('w',newline='') as handle:
            writer=csv.writer(handle);writer.writerow(table['columns']);writer.writerows(table['rows'])
        table['mode']='csv';table['csv_path']='schedule.csv';table['rows']=[]
        pointer=self.apply(changed);stage=self.root/pointer['directory']
        self.assertEqual((stage/'linked-sources/firo_space-schedule.csv').read_bytes(),source.read_bytes())
        source.unlink()
        with self.assertRaises(FileNotFoundError): self.apply(changed)
        self.assertEqual(json.loads((self.root/'rts-baseline-config-active.json').read_text())['id'],pointer['id'])
    def test_invalid_values_fail_before_activation(self):
        for edit in (lambda c:c['rules']['firo_space']['settings'].update(glide_days=0),
                     lambda c:c['rules']['draft_to_rc']['settings'].update(active={'Detroit':'false'}),
                     lambda c:c['rules']['diversions']['tables']['schedule']['rows'].pop(),
                     lambda c:c['rules']['no_draft']['tables']['configuration']['rows'][0].__setitem__(3,'NaN')):
            changed=copy.deepcopy(self.configuration);edit(changed)
            with self.assertRaises(ValueError):self.apply(changed)
            self.assertFalse((self.root/'rts-baseline-config-active.json').exists())
    def test_table_tampering_is_rejected_and_acceptance_retains_original_inputs(self):
        pointer=self.apply();network,rule,store=self.network();runtime.initialize_rule('DraftToRC',rule,network)
        destination=self.root/'accepted';destination.mkdir();config.archive_configuration(self.root,destination,pointer)
        stage=self.root/pointer['directory'];table=stage/'tables/no_draft-configuration.csv';table.write_text('tampered')
        with self.assertRaisesRegex(RuntimeError,'table changed'):runtime.alternative_overrides(network)
        self.assertNotEqual((destination/'baseline-configuration/tables/no_draft-configuration.csv').read_text(),'tampered')


if __name__=='__main__':unittest.main()
