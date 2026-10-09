import sys
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'migration-review/ExternalPython'))
import inspect_rfc_archive as inspector

class ArchiveInspectionTests(unittest.TestCase):
    def test_inventory_uses_issue_dates_not_partition_order(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name in ['station=BLUO3I/issued_year=2015/BLUO3I_QINE.ESPF10_20150720.parquet',
                         'station=BLUO3I/issued_year=2016/BLUO3I_QINE.ESPF10_20160310.parquet']:
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'unchanged')
            stations,samples=inspector.inventory(root)
            self.assertEqual(stations[0]['files'],2)
            self.assertEqual(stations[0]['filename_issue_date_first'],'20150720')
            self.assertEqual(samples[0][2].name,'BLUO3I_QINE.ESPF10_20160310.parquet')
            self.assertTrue(all(path.read_bytes()==b'unchanged' for path in root.rglob('*.parquet')))
    def test_sample_exposes_legacy_uncertainty_and_member_counts(self):
        frame=pd.DataFrame({'valid_datetime':pd.to_datetime(['2015-07-20','2015-07-21']),
            'trace_year':[1949,1949],'value':[1.0,float('nan')],
            'issued_datetime':pd.to_datetime(['2015-07-20','2015-07-20'],utc=True),
            'issued_time_is_estimated':[True,True],'units':[None,None]})
        fake=SimpleNamespace(ParquetFile=lambda path:SimpleNamespace(schema_arrow='sample schema',read=lambda:SimpleNamespace(to_pandas=lambda:frame)))
        with patch.dict(sys.modules,{'pyarrow':SimpleNamespace(parquet=fake),'pyarrow.parquet':fake}):
            result=inspector.sample_info('sample.parquet')
        self.assertEqual(result['trace_years'],[1949]);self.assertEqual(result['units'],[None])
        self.assertEqual(result['issued_time_is_estimated'],[True])
        self.assertEqual(result['missing_values'],1)
