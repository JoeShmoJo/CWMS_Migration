import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'migration-review/ExternalPython'))
spec = importlib.util.spec_from_file_location('augmentation_check', Path(__file__).resolve().parents[1] /
    'migration-review/ExternalPython/check_augmentation_inputs.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AuditTests(unittest.TestCase):
    def test_minimum_mapping_uses_converted_green_peter_release(self):
        self.assertEqual(module.minimum_path('GPR', 1981, 'C0'),
                         '//GREEN PETER-COMBINED MIN TRIB/FLOW-SPEC//1DAY/C:001981|C0/')
        self.assertEqual(module.minimum_path('BLU', 3000, 'C0'),
                         '//BLUE RIVER-COMBINED MIN TRIB/FLOW-SPEC//1DAY/C:003000|C0/')

    def test_catalog_excludes_inputs_and_merges_year_blocks(self):
        paths = ['//DETROIT-POOL/STOR/01Jan2026/1Day/C:001981|C0/',
                 '//DETROIT-POOL/STOR/01Jan2027/1Day/C:001981|C0/',
                 '//DETROIT-POOL/STOR/01Jan2027/1Day/C:001981|C0-INPUT/',
                 '//DETROIT-POOL/STOR/01Jan2027/1Day/C:001982|C0/']
        self.assertEqual(module.logical_outputs(paths, 'C0', {1981}),
                         {1981: {'//DETROIT-POOL/STOR//1Day/C:001981|C0/'}})

    def test_rejects_missing_values_and_truncated_coverage(self):
        start, end = pd.Timestamp('2027-04-01'), pd.Timestamp('2027-04-03')
        def handle(values, dates):
            return SimpleNamespace(read_ts=lambda *a, **k: SimpleNamespace(
                values=values, pytimes=dates, units='ACRE-FT'))
        dates = pd.date_range(start, end)
        self.assertEqual(module.inspect_series(handle([1, 2, 3], dates), '/', start, end)[0], 3)
        with self.assertRaisesRegex(ValueError, 'missing/invalid'):
            module.inspect_series(handle([1, -3.4e38, 3], dates), '/', start, end)
        with self.assertRaisesRegex(ValueError, 'Coverage'):
            module.inspect_series(handle([1, 2], dates[:2]), '/', start, end)


if __name__ == '__main__':
    unittest.main()
