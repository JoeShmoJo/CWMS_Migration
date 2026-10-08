from pathlib import Path
import sys
import unittest
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'migration-review' / 'ExternalPython'))
from ensemble_ids import add_percentile_members


class PercentileTests(unittest.TestCase):
    def test_forecast_does_not_overwrite_real_year(self):
        original = pd.DataFrame({1981: [0.0, 10.0], 2026: [100.0, 30.0]})
        result = add_percentile_members(original, forecast=True)
        pd.testing.assert_series_equal(result[2026], original[2026])
        self.assertEqual(result[3000].tolist(), [25.0, 15.0])
        self.assertEqual(result[3001].tolist(), [50.0, 20.0])
        self.assertEqual(result[3002].tolist(), [75.0, 25.0])

    def test_standalone_collision_fails_instead_of_overwrite(self):
        with self.assertRaises(ValueError):
            add_percentile_members(pd.DataFrame({2026: [1.0]}))

    def test_standalone_legacy_ids_retained(self):
        result = add_percentile_members(pd.DataFrame({1981: [1.0], 1982: [3.0]}))
        self.assertEqual(result[2027].tolist(), [2.0])
