import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import sys
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('diversion_post',ROOT/'migration-review/optional-diversion-postprocess/postprocess.py')
post=importlib.util.module_from_spec(spec);spec.loader.exec_module(post)


class PostprocessTests(unittest.TestCase):
    def setUp(self):
        self.mapping={'Diversion A':{'locations':['Gauge'],'junction':'Gauge','reservoir_barrier':None},
                      'Return A':{'locations':['Gauge'],'junction':'Gauge','reservoir_barrier':None}}
        self.index=pd.date_range('2026-07-01',periods=3,freq='D')
        self.table={(t.month,t.day):{'Diversion A':100.,'Return A':-20.} for t in self.index}
        self.config={'source_diversions':'none','schedule_day':'timestamp','timestep_hours':24,'conditions':[
            {'enabled':True,'reservoir':'Lookout Point','operator':'below','threshold_ft':900.,
             'elements':['Diversion A'],'withdrawal_multiplier':.5}]}

    def test_conditional_signs_and_double_subtraction_protection(self):
        levels={'Lookout Point':pd.Series([899.,900.,901.],index=self.index)}
        base,effective=post.demand(self.index,self.table,self.config,levels)
        raw={'Gauge':pd.Series(1000.,index=self.index)}
        result=post.calculate(raw,base,effective,self.mapping,'none')['Gauge']
        self.assertEqual(result.adjusted_flow_cfs.tolist(),[970.,920.,920.])
        result=post.calculate(raw,base,effective,self.mapping,'scheduled')['Gauge']
        self.assertEqual(result.adjusted_flow_cfs.tolist(),[1050.,1000.,1000.])
        self.assertEqual(raw['Gauge'].tolist(),[1000.]*3)

    def test_missing_elevation_gap_negative_result_and_leap_convention(self):
        with self.assertRaisesRegex(ValueError,'coverage'):
            post.demand(self.index,self.table,self.config,{'Lookout Point':pd.Series([899.],index=self.index[:1])})
        self.config['conditions']=[]
        with self.assertRaisesRegex(ValueError,'Uniform'):
            post.demand(self.index[[0,2]],self.table,self.config,{})
        base,effective=post.demand(self.index,self.table,self.config,{})
        with self.assertRaisesRegex(ValueError,'Negative'):
            post.calculate({'Gauge':pd.Series(10.,index=self.index)},base,effective,self.mapping,'none')
        index=pd.date_range('2024-02-29',periods=2,freq='D')
        self.config['schedule_day']='period_start'
        base,_=post.demand(index,{(2,28):{'A':3.}},self.config,{})
        self.assertEqual(base.A.tolist(),[3.,3.])

    def test_real_network_all_columns_and_reservoir_barriers(self):
        mapping=post.network_map(ROOT/'network/network.json')
        table=post.schedule(ROOT/'standalone-review/scripts/externalRules/DiversionConfig_ALT.csv',mapping)
        self.assertEqual(len(mapping),32);self.assertEqual(len(table),365)
        self.assertEqual(mapping['Diversion 3']['reservoir_barrier'],'Big Cliff')
        self.assertNotIn('Willamette_at Salem',mapping['Diversion 3']['locations'])
        self.assertIn('Willamette_at Salem',mapping['Diversion 1 up']['locations'])
        self.assertNotIn('Willamette_at Salem',mapping['Diversion 1 down']['locations'])

    def test_cli_pipeline_readonly_source_and_separate_audited_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            directory=Path(directory);source=directory/'simulation.dss';source.write_bytes(b'original')
            network=directory/'network.json'
            network.write_text(json.dumps({'network':{'elements':{
                'diversion:Diversion A':{'name':'Diversion A','type':'diversion','junction':'Gauge'},
                'diversion:Return A':{'name':'Return A','type':'diversion','junction':'Gauge'},
                'junction:Gauge':{'name':'Gauge','type':'junction'}}}}))
            schedule=directory/'schedule.csv'
            dates=pd.date_range('2001-01-01','2001-12-31')
            pd.DataFrame({'Month':dates.month,'Day':dates.day,'Diversion A':100,'Return A':-20}).to_csv(schedule,index=False)
            config=dict(self.config,method='instantaneous-bookkeeping-stop-at-reservoir',run_code='C0',members=[2000],
                        start=str(self.index[0]),end=str(self.index[-1]),locations=['Gauge'])
            config_file=directory/'config.json';config_file.write_text(json.dumps(config))
            paths=['//Gauge/FLOW//1DAY/C:002000|C0/','//Lookout Point-Pool/ELEV//1DAY/C:002000|C0/']
            class DSS:
                def __enter__(self):return self
                def __exit__(self,*args):pass
                def getPathnameList(self,pattern):return paths
                def read_ts(inner,path,**kwargs):
                    return SimpleNamespace(pytimes=self.index,values=[899.,900.,901.] if 'ELEV' in path else [1000.]*3,
                                           units='FT' if 'ELEV' in path else 'CFS',type='INST-VAL' if 'ELEV' in path else 'PER-AVER')
            fake=SimpleNamespace(HecDss=SimpleNamespace(Open=lambda path:DSS()))
            args=SimpleNamespace(source=source,network=network,schedule=schedule,config=config_file,output=directory/'output')
            with patch.dict(sys.modules,{'pydsstools':SimpleNamespace(),'pydsstools.heclib':SimpleNamespace(),'pydsstools.heclib.dss':fake}):
                post.run(args)
            self.assertEqual(source.read_bytes(),b'original')
            self.assertEqual(json.loads((args.output/'manifest.json').read_text())['status'],'complete')
            frame=pd.read_csv(args.output/'member-2000-Gauge.csv.gz')
            self.assertEqual(frame.adjusted_flow_cfs.tolist(),[970.,920.,920.])
            with self.assertRaisesRegex(ValueError,'existing outputs'):post.run(args)

if __name__=='__main__':unittest.main()
