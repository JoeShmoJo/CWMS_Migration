import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
import tempfile
import types
import io
from contextlib import redirect_stdout
from unittest.mock import patch
import numpy as np
import pandas as pd

spec = importlib.util.spec_from_file_location('compare_flows',Path(__file__).resolve().parents[1]/'migration-review/ExternalPython/compare_simulation_flows.py')
m = importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class FlowCompareTests(unittest.TestCase):
    def test_selects_only_requested_outputs_members_and_trial(self):
        paths = ['//Detroit-Pool/Flow-OUT/01Jan2026/1Day/C:001982|Con_Season1/',
                 '//Detroit-Pool/Flow-OUT/01Jan2027/1Day/C:001982|Con_Season1/',
                 '//Detroit-Powerplant/Flow-OUT/01Jan2026/1Day/C:001982|Con_Season1/',
                 '//Detroit-Pool/Elev/01Jan2026/1Day/C:001982|Con_Season1/',
                 '//Detroit-Pool/Flow-OUT/01Jan2026/1Day/C:001982|Con_Season0/',
                 '//Detroit-Pool/Flow-OUT/01Jan2026/1Day/C:003000|Con_Season1/',
                 '//Willamette_at Salem/Flow/01Jan2026/1Day/C:001982|Con_Season1/']
        groups,_=m.groups(paths,{1982},'Con_Season1')
        self.assertEqual(set(groups),{('Detroit',1982),('Willamette_at Salem',1982)})
        self.assertEqual(len(groups['Detroit',1982]),2)

    def test_missing_timestamps_and_common_undefined_fail(self):
        dates=pd.date_range('2026-10-15',periods=3)
        a=pd.Series([1.,np.nan,3.],index=dates)
        b=pd.Series([1.,np.nan],index=dates[:2])
        _,_,_,missing,different,maximum=m.compare_series(a,b)
        self.assertEqual(missing.tolist(),[False,True,True])
        self.assertFalse(different.any());self.assertEqual(maximum,0.)

    def test_exact_default_and_optional_absolute_tolerance(self):
        a=pd.Series([1.,2.],index=pd.date_range('2026-01-01',periods=2));b=a.copy();b.iloc[1]+=0.001
        self.assertEqual(m.compare_series(a,b)[4].sum(),1)
        self.assertEqual(m.compare_series(a,b,0.01)[4].sum(),0)

    def test_block_merge_and_conflicts(self):
        paths=['//Detroit-Pool/Flow-OUT/01Jan2026/1Day/C:001982|T/',
               '//Detroit-Pool/Flow-OUT/01Jan2027/1Day/C:001982|T/']
        records={paths[0]:SimpleNamespace(pytimes=pd.date_range('2026-12-30',periods=3),values=np.array([1.,2.,3.]),units='CFS',type='PER-AVER'),
                 paths[1]:SimpleNamespace(pytimes=pd.date_range('2027-01-01',periods=2),values=np.array([3.,4.]),units='CFS',type='PER-AVER')}
        dss=SimpleNamespace(read_ts=lambda p,**kw:records[p])
        series,metadata=m.read_series(dss,paths)
        self.assertEqual(series.tolist(),[1.,2.,3.,4.])
        records[paths[1]].values[0]=30.
        with self.assertRaisesRegex(ValueError,'Conflicting overlapping'):
            m.read_series(dss,paths)


    def test_cli_reports_match_then_rejects_missing_salem(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);left=root/'parallel.dss';right=root/'serial.dss'
            left.write_bytes(b'parallel input');right.write_bytes(b'serial input')
            paths=[]
            for location in m.LOCATIONS:
                b=location if location=='Willamette_at Salem' else location+'-Pool'
                c='FLOW' if location=='Willamette_at Salem' else 'Flow-OUT'
                paths.append('//'+b+'/'+c+'/01Jan2026/1Day/C:001982|Con_Season1/')
            missing_salem=[False]
            class FakeDss:
                def __init__(self,filename):self.serial=filename==str(right)
                def __enter__(self):return self
                def __exit__(self,*args):pass
                def getPathnameList(self,pattern):
                    return paths[:-1] if self.serial and missing_salem[0] else paths
                def read_ts(self,path,**kwargs):
                    return SimpleNamespace(pytimes=pd.date_range('2026-10-15',periods=3),
                        values=np.array([1.,2.,3.]),units='CFS',type='PER-AVER')
            packages={name:types.ModuleType(name) for name in ('pydsstools','pydsstools.heclib','pydsstools.heclib.dss')}
            packages['pydsstools.heclib.dss'].HecDss=SimpleNamespace(Open=FakeDss)
            base=['compare','--parallel',str(left),'--serial',str(right),'--members','1982-1982',
                  '--run-code','Con_Season1','--report-dir']
            with patch.dict('sys.modules',packages),redirect_stdout(io.StringIO()):
                with patch('sys.argv',base+[str(root/'match')]):self.assertEqual(m.main(),0)
                missing_salem[0]=True
                with patch('sys.argv',base+[str(root/'missing')]):self.assertEqual(m.main(),1)
            self.assertIn('Matching series: 14 / 14',(root/'match/result.txt').read_text())
            self.assertIn('Missing serial series',(root/'missing/summary.csv').read_text())
            self.assertEqual(left.read_bytes(),b'parallel input')
            self.assertEqual(right.read_bytes(),b'serial input')


if __name__=='__main__':unittest.main()
