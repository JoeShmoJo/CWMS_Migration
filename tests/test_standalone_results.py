import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'migration-review/ExternalPython'))
import standalone_results as results


class StandaloneResultTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.source=self.root/'simulation.dss';self.source.write_bytes(b'original')
        self.value=100.;self.fail=False
        self.paths=['//Lookout Point-Pool/'+param+'/01Jan2027/1DAY/C:002000|CON_SEASON0/' for param in ('ELEV','FLOW-OUT','STOR')]
        self.paths+=['//Willamette_at Salem/FLOW/01Jan2027/1DAY/C:002000|CON_SEASON0/']
        outer=self
        class DSS:
            def __init__(self,path):
                if str(path)!=str(outer.source):raise AssertionError('Reopened DSS archive')
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def getPathnameList(self,pattern):return outer.paths
            def read_ts(self,path,**kwargs):
                if outer.fail:raise ValueError('bad record')
                param=path.split('/')[3]
                return SimpleNamespace(pytimes=pd.date_range('2027-04-01',periods=3),values=[outer.value]*3,
                                       units='FT' if param=='ELEV' else 'AC-FT' if param=='STOR' else 'CFS',type='PER-AVER')
        self.fake=SimpleNamespace(HecDss=SimpleNamespace(Open=DSS))
        patcher=patch.dict(sys.modules,{'pydsstools.heclib.dss':self.fake});patcher.start();self.addCleanup(patcher.stop)

    def test_named_baseline_and_result_survive_live_changes_and_plot_without_dss(self):
        baseline=results.capture(self.root,'Con_Season','Original baseline','CON_SEASON0','baseline',confirmed=True)
        self.value=120.
        augmented=results.capture(self.root,'Con_Season','Augmented scheme A','CON_SEASON0','result',baseline['id'],True)
        self.value=140.
        newer=results.capture(self.root,'Con_Season','Changed baseline','CON_SEASON0','baseline',confirmed=True)
        self.assertEqual(len(results.catalog(self.root)),3)
        self.assertEqual(augmented['baseline_id'],baseline['id'])
        self.assertNotEqual(newer['baseline_id'],baseline['id'])
        self.source.unlink()
        with patch.object(self.fake.HecDss,'Open',side_effect=AssertionError('Read live DSS')):
            plot=results.plot(self.root,[baseline['id'],augmented['id']])
        self.assertTrue(plot.is_file())
        self.assertTrue((plot.parent/'plotly.min.js').is_file())
        self.assertTrue(json.loads((plot.parent/'selection.json').read_text())['same_baseline'])
        self.assertEqual(len(list(plot.parent.glob('*.csv'))),6)

    def test_capture_records_common_synthetic_ids_without_relabeling_legacy_archives(self):
        self.paths += [path.replace('002000','003003') for path in self.paths]
        captured=results.capture(self.root,'Con_Season','OSI included','CON_SEASON0','baseline',confirmed=True)
        self.assertEqual(captured['synthetic_members'],[3003])
        self.assertEqual(captured['members'],[2000,3003])
        self.source.unlink()
        self.assertTrue(results.plot(self.root,[captured['id']]).is_file())

    def test_single_por_capture_and_plot_without_ensemble_prefix_or_live_dss(self):
        self.paths=[path.replace('C:002000|','') for path in self.paths]
        self.assertEqual(results.outputs(self.root,'ensemble'),[])
        self.assertEqual(results.outputs(self.root,'por'),['CON_SEASON0'])
        baseline=results.capture(self.root,'Con_Season','POR baseline','CON_SEASON0','baseline',confirmed=True,run_type='por')
        self.assertEqual(baseline['run_type'],'por');self.assertEqual(baseline['members'],[])
        self.value=150.
        result=results.capture(self.root,'Con_Season','POR result','CON_SEASON0','result',baseline['id'],True,run_type='por')
        self.source.unlink()
        path=results.plot(self.root,[baseline['id'],result['id']])
        self.assertTrue(path.is_file())
        frame=pd.read_csv(next(path.parent.glob('*.csv')))
        self.assertIn('POR',frame.columns)
        figure=next(path.parent.glob('plot-*.html')).read_text()
        self.assertNotIn('5–95%',figure)
        self.assertIn('POR',figure)

    def test_capture_guards_confirmation_alternative_and_failed_archive(self):
        with self.assertRaisesRegex(ValueError,'Confirm'):results.capture(self.root,'Con_Season','x','CON_SEASON0','baseline')
        with self.assertRaisesRegex(ValueError,'alternative'):results.capture(self.root,'Other','x','CON_SEASON0','baseline',confirmed=True)
        with self.assertRaisesRegex(ValueError,'baseline'):results.capture(self.root,'Con_Season','x','CON_SEASON0','result',confirmed=True)
        self.fail=True
        with self.assertRaisesRegex(ValueError,'required series'):results.capture(self.root,'Con_Season','x','CON_SEASON0','baseline',confirmed=True)
        self.assertEqual(results.catalog(self.root),[])
        self.assertEqual(self.source.read_bytes(),b'original')

if __name__=='__main__':unittest.main()
