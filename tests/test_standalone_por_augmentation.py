from pathlib import Path
import sys
import unittest
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'migration-review/ExternalPython'))
from standalone_por_augmentation import daily_series

class PorDailyTests(unittest.TestCase):
    def test_three_hour_volume_and_day_end_storage(self):
        index=pd.date_range('1996-10-01 03:00',periods=16,freq='3h')
        source=pd.Series(np.arange(16.)+1,index=index)
        flow=daily_series(source,'3Hour','Flow-IN','PER-AVER')
        storage=daily_series(source,'3Hour','Stor','INST-VAL')
        self.assertEqual(list(flow),[4.5,12.5])
        self.assertEqual(list(storage),[8.,16.])
        self.assertEqual(flow.index[0],pd.Timestamp('1996-10-02'))
        self.assertEqual(float(flow.sum()*86400),float(source.sum()*3*3600))

    def test_reject_gaps_and_instantaneous_flow(self):
        source=pd.Series(1.,index=pd.date_range('1996-10-01 03:00',periods=24,freq='3h'))
        with self.assertRaisesRegex(ValueError,'Gap'):
            daily_series(source.drop(source.index[10]),'3Hour','FLOW-IN','PER-AVER')
        with self.assertRaisesRegex(ValueError,'period averages'):
            daily_series(source,'3Hour','FLOW-IN','INST-VAL')

    def test_reads_native_blocks_and_exact_por_fpart(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from standalone_por_augmentation import read_daily_por
        paths=['//Lookout Point-Pool/'+parameter+'/'+block+'/3Hour/Temp3Hour-0/'
               for parameter in ('Flow-IN','Stor') for block in ('01Oct1996','01Nov1996')]
        paths.append('//Lookout Point-Pool/Flow-IN/01Oct1996/3Hour/C:002000|Temp3Hour-0/')
        class DSS:
            def getPathnameList(self,pattern):return paths
            def read_ts(self,path,**kwargs):
                if 'C:' in path:raise AssertionError('Selected an ensemble record')
                offset=0 if '/01Oct1996/' in path else 8
                return SimpleNamespace(values=np.arange(8.)+1+offset,
                    pytimes=pd.date_range('1996-10-31 03:00',periods=16,freq='3h')[offset:offset+8],
                    type='PER-AVER' if '/Flow-IN/' in path else 'INST-VAL',nodata=np.zeros(8,dtype=bool))
        with patch.dict(sys.modules,{'pydsstools.heclib.dss':SimpleNamespace(HecDss=None)}):
            result=read_daily_por('unused',{'inflow':'//LOOKOUT POINT-POOL/FLOW-IN//1DAY/Temp3Hour-0/',
                                          'storage':'//LOOKOUT POINT-POOL/STOR//1DAY/Temp3Hour-0/'},['01Jan2026'],fid=DSS())
        self.assertEqual(result['inflow'].tolist(),[4.5,12.5])
        self.assertEqual(result['storage'].tolist(),[8.,16.])
        self.assertEqual(result.index[-1],pd.Timestamp('1996-11-02'))

    def test_native_daily_unchanged(self):
        source=pd.Series([12.,15.],index=pd.date_range('1996-10-02',periods=2))
        pd.testing.assert_series_equal(daily_series(source,'1DAY','FLOW-IN','PER-AVER'),source)
