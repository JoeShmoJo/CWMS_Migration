"""Exercise the real extractor/checker against DSS 6 uppercase catalog names."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
def load(name,file):
    spec=importlib.util.spec_from_file_location(name,ROOT/'model_check'/file)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

class CasingTests(unittest.TestCase):
    def setUp(self):
        with patch.dict(sys.modules,{'pydsstools.heclib.dss':SimpleNamespace(HecDss=None)}):
            self.extract=load('case_extract','extract_dss.py')
        self.check=load('case_report','check_model.py')
        self.names=[('Blue River-Pool','Elev'),('Blue River-Pool','Flow-IN'),('Blue River-Pool','Flow-OUT'),
            ('Blue River-Rule Curve','Elev-ZONE'),('Blue River','Flow-MINLIM'),('Blue River','Flow-MAXLIM'),
            ('Blue River-Dam-FIRO_SPACE','Flow-SPEC'),('Blue River-Blue River-Conservation-ZBOp Rule','Flow-SPEC'),
            ('Blue River-Blue River-Inactive-ZBOp Rule','Flow-SPEC'),('Min_Flow_Target_Salem','Flow-Min'),
            ('Willamette_at Salem','Flow'),('Willamette_at Salem','Flow-Local'),
            ('Diversion 1 up','Flow-DECISION'),('Diversion 1 up-Diversion 1 up','Flow-SPEC')]

    def paths(self,upper=False):
        paths=['//'+b+'/'+c+'/01Jan2026/1DAY/C:001985|CON_SEASON0/' for b,c in self.names]
        return [p.upper() for p in paths] if upper else paths

    def test_all_groups_selected_equally_for_uppercase_and_mixed_catalogs(self):
        chosen=[]
        for upper in (False,True):
            grouped=self.extract.groupByseries(self.paths(upper),'C:001985|CON_SEASON0')
            selections={name:self.extract.selectSeries(grouped.keys(),rules) for name,rules in self.extract.SELECTIONS.items()}
            self.assertTrue(all(selections.values()))
            self.assertEqual(len(selections['limits']),3)
            self.assertEqual(len(selections['rules']),2)  # inactive guide excluded
            chosen.append({name:{(b.casefold(),c.casefold()) for b,c in pairs} for name,pairs in selections.items()})
            for block_paths in grouped.values():
                self.assertIn(block_paths[0],self.paths(upper))  # native path unchanged
        self.assertEqual(chosen[0],chosen[1])

    def test_uppercase_native_extract_writes_all_groups_and_preserves_source(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'rss/Ensebmle_Test/simulation.dss'
            source.parent.mkdir(parents=True);source.write_bytes(b'unchanged native file')
            paths=self.paths(True)
            class DSS:
                def getPathnameList(self,*args,**kwargs):return paths
                def read_ts(self,path,**kwargs):
                    return SimpleNamespace(values=[100.,110.],pytimes=pd.date_range('2026-10-16',periods=2),
                        units='CFS',nodata=[False,False])
                def close(self):pass
            self.extract.HecDss=SimpleNamespace(Open=lambda filename:DSS())
            self.extract.OUTPUT_ROOT=str(root/'reports')
            self.extract.fPartFor=lambda paths,alternative:'C:001985|CON_SEASON0'
            report=Path(self.extract.main(str(source),'Con_Season'))
            for group in self.extract.SELECTIONS:
                self.assertTrue((report/(group+'.csv')).is_file(),group)
            groups=self.check.loadGroups(str(report))
            self.assertEqual(self.check.col(groups,'reservoirs','Blue River-Pool Flow-OUT').tolist(),[100.,110.])
            self.assertEqual(self.check.col(groups,'limits','Blue River Flow-MINLIM').tolist(),[100.,110.])
            self.assertEqual(source.read_bytes(),b'unchanged native file')

    def test_report_finds_uppercase_rule_in_mixed_case_operation_stack(self):
        dates=pd.date_range('2026-10-15',periods=2)
        groups={'reservoirs':pd.DataFrame({'Blue River-Pool Elev':[1200.,1201.]},index=dates),
                'rules':pd.DataFrame({'Blue River-DAM-FIRO_SPACE Flow-SPEC':[100.,110.]},index=dates),
                'stack':{'Blue River':[('Conservation',['FIRO_SPACE'])]}}
        found=self.check.reservoirRules(groups,'Blue River',dates)
        self.assertEqual(found[0][1],'script')
        self.assertEqual(found[0][2].tolist(),[100.,110.])
        self.assertEqual(self.check.stackPosition(groups['stack']['Blue River'],'Conservation','DAM-FIRO_SPACE'),1)
        self.assertEqual(self.check.col(groups,'rules','BLUE RIVER-Dam-firo_space FLOW-SPEC').tolist(),[100.,110.])
        self.assertEqual(self.check.reservoirNames(groups),['Blue River'])
