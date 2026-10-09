import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'migration-review/ExternalPython'))
from run_data_cache import open_cached_run
from baseline_versions import digest_file
from prepare_rts_augmentation import read_series, validate_daily
from plot_rts_forecast import clean_series


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / 'augmentation-archives/baseline/forecast.dss'
        self.source.parent.mkdir(parents=True)
        self.source.write_bytes(b'immutable DSS fixture')
        self.path = '//Detroit-Pool/Flow-OUT//1Day/C:001981|C0/'
        self.calls = []
        self.times = pd.to_datetime(['2027-04-01', '2027-04-02', '2027-04-04'])
        outer = self
        class FakeDss:
            def __init__(self, filename): outer.calls.append(('open', filename))
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def getPathnameList(self, pattern):
                return [outer.path.replace('//1Day', '/01Jan2026/1Day'),
                        outer.path.replace('//1Day', '/01Jan2027/1Day'),
                        outer.path.replace('C0', 'C1'), '//DETROIT/ELEV//1DAY/RULE CURVE/']
            def read_ts(self, path, **kwargs):
                outer.calls.append(('read', path))
                return SimpleNamespace(values=[1., -3.4028234663852886e38, 3.],
                    pytimes=outer.times, units='CFS', type='PER-AVER')
        self.fake = SimpleNamespace(HecDss=SimpleNamespace(Open=FakeDss))

    def build(self):
        with patch.dict(sys.modules, {'pydsstools.heclib.dss': self.fake}):
            return open_cached_run(self.source, 'C0', digest_file(self.source))

    def test_catalog_deduplicates_blocks_and_cache_reuses_without_dss(self):
        with self.build() as cache:
            record = cache.read_ts(self.path.lower())
            self.assertEqual(record.units, 'CFS')
            self.assertEqual(record.type, 'PER-AVER')
            self.assertEqual(record.pytimes[-1], pd.Timestamp('2027-04-04'))
            self.assertEqual(len(cache.getPathnameList('*')), 1)
            self.assertEqual(record.values.tolist(), [1., -3.4028234663852886e38, 3.])
            self.assertTrue(pd.isna(clean_series(record).iloc[1]))
            # Plot cleaning cannot alter data used by the augmentation validator.
            self.assertLess(cache.read_ts(self.path).values[1], -1e30)
        self.assertEqual(len([call for call in self.calls if call[0] == 'read']), 1)
        with patch.dict(sys.modules, {'pydsstools.heclib.dss': SimpleNamespace(HecDss=SimpleNamespace(Open=lambda *args: self.fail('DSS reopened')))}):
            with open_cached_run(self.source, 'C0') as cache:
                series = read_series(cache, self.path, {'CFS'})
                with self.assertRaisesRegex(ValueError, 'Missing/invalid'):
                    validate_daily(series.to_frame('flow'), series.index[0], series.index[-1])
                with self.assertRaisesRegex(ValueError, 'absent'):
                    cache.read_ts(self.path.replace('1981', '1982'))

    def test_reads_only_plot_outputs_and_required_augmentation_inputs(self):
        required = [self.path,
                    '//Lookout Point-Pool/STOR//1DAY/C:001981|C0/',
                    '//Hills Creek-Pool/FLOW-IN//1DAY/C:001981|C0/',
                    '//Green Peter-Combined Min Trib/FLOW-SPEC//1DAY/C:001981|C0/',
                    '//WATERYEARTYPEVARIABLE/STOR-MAF//1DAY/C:001981|C0/',
                    '//Willamette_at Salem/FLOW//1DAY/C:001981|C0/']
        irrelevant = ['//Detroit-Power Plant/FLOW-OUT//1DAY/C:001981|C0/',
                      '//Diversion 1 up/FLOW//1DAY/C:001981|C0/',
                      '//Return 2/FLOW//1DAY/C:001981|C0/',
                      '//Willamette_at Albany to Willamette+Santiam/FLOW//1DAY/C:001981|C0/',
                      '//Detroit-Flood Min/FLOW-SPEC//1DAY/C:001981|C0/',
                      '//Dexter-Pool/STOR//1DAY/C:001981|C0/']
        with patch.object(self.fake.HecDss.Open, 'getPathnameList', return_value=required + irrelevant):
            with self.build() as cache:
                self.assertEqual(set(cache.getPathnameList('*')), set(required))
        self.assertEqual({path for action, path in self.calls if action == 'read'}, set(required))

    def test_microsecond_indexes_and_timezone_round_trip(self):
        self.times = pd.DatetimeIndex(np.array(['2027-04-01', '2027-04-02', '2027-04-04'], dtype='datetime64[us]'))
        with self.build() as cache:
            pd.testing.assert_index_equal(cache.read_ts(self.path).pytimes, self.times.as_unit('ns'))
        # A separate immutable archive exercises timezone-bearing timestamps.
        self.source = self.source.parent.parent / 'another/forecast.dss'
        self.source.parent.mkdir()
        self.source.write_bytes(b'another immutable DSS fixture')
        self.times = self.times.tz_localize('Etc/GMT+8')
        with self.build() as cache:
            pd.testing.assert_index_equal(cache.read_ts(self.path).pytimes, self.times.as_unit('ns'))

    def test_corrupt_arrays_are_rebuilt_from_source(self):
        with self.build(): pass
        (self.source.parent / 'run-data-cache-C0/series.npz').write_bytes(b'broken')
        with self.build() as cache:
            self.assertEqual(cache.read_ts(self.path).values[0], 1)
        self.assertEqual(len([call for call in self.calls if call[0] == 'read']), 2)

    def test_changed_archived_source_cannot_reuse_verified_cache(self):
        expected = digest_file(self.source)
        with self.build(): pass
        self.source.write_bytes(b'changed source')
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            open_cached_run(self.source, 'C0', expected)

    def test_schema_changes_rebuild_and_live_files_are_rejected(self):
        with self.build(): pass
        manifest_path = self.source.parent / 'run-data-cache-C0/manifest.json'
        metadata = json.loads(manifest_path.read_text())
        metadata['schema'] = 0
        manifest_path.write_text(json.dumps(metadata))
        with self.build(): pass
        self.assertEqual(len([call for call in self.calls if call[0] == 'read']), 2)
        with self.assertRaisesRegex(ValueError, 'restricted'):
            open_cached_run(Path(self.temp.name) / 'forecast.dss', 'C0')


if __name__ == '__main__':
    unittest.main()
