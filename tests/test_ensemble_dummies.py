from pathlib import Path
import sys
import unittest
import tempfile
import types
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'migration-review' / 'ExternalPython'))
from write_ensemble_dummies import member_prefixes, copy_records


class MemberTests(unittest.TestCase):
    def test_shared_copy_preserves_values_and_six_hour_clock(self):
        import pandas as pd
        import numpy as np
        writes = []
        class FakeDss:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def getPathnameList(self, pattern):
                return ['//DETO3/FLOW-UNREG/01JAN2026/1DAY/C:001981|/',
                        '//DETO3/FLOW-UNREG/01JAN2026/1DAY/C:001982|/']
            def read_ts(self, path, **kwargs):
                return types.SimpleNamespace(pytimes=pd.date_range('2026-10-07 22:00', periods=7, freq='6h').to_pydatetime(),
                                             values=np.arange(7, dtype=float) + 100)
            def put_ts(self, record):
                writes.append(record)
        modules = {'pydsstools': types.ModuleType('pydsstools'),
                   'pydsstools.heclib': types.ModuleType('pydsstools.heclib'),
                   'pydsstools.heclib.dss': types.SimpleNamespace(HecDss=types.SimpleNamespace(Open=lambda path: FakeDss())),
                   'pydsstools.core': types.SimpleNamespace(TimeSeriesContainer=types.SimpleNamespace)}
        with tempfile.NamedTemporaryFile() as file, patch.dict(sys.modules, modules):
            copy_records(file.name, [('//DET/ELEV-FOREBAY//6HOUR/RFC-FCST/', 'FT', 360, 'INST-VAL')])
        self.assertEqual(len(writes), 2)
        self.assertEqual(writes[0].pathname, '//DET/ELEV-FOREBAY//6HOUR/C:001981|RFC-FCST/')
        for record in writes:
            self.assertEqual(record.interval, 360)
            self.assertEqual(record.startDateTime, '07Oct2026 2200')
            np.testing.assert_array_equal(record.values, np.arange(7, dtype=float) + 100)

    def test_only_downloaded_flow_collections(self):
        paths = ['//DETO3/FLOW-UNREG/01JAN2026/1DAY/C:001981|/',
                 '//SLMO3/FLOW-LOC/01JAN2026/1DAY/C:001981|/',
                 '//SLMO3/FLOW-LOC/01JAN2027/1DAY/C:002027|/',
                 '/ZERO/ZERO/FLOW/01JAN2026/1DAY/C:001928|DUMMY/',
                 '//DET/ELEV/01JAN2026/1DAY/C:001929|/',
                 '//SLMO3/FLOW-LOC/01JAN2026/1DAY/A0/']
        self.assertEqual(member_prefixes(paths), ['C:001981|', 'C:002027|'])
