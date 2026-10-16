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

    def test_standalone_preserves_real_2026_member(self):
        original=pd.DataFrame({2026:[1.0],2025:[3.0]})
        result=add_percentile_members(original)
        pd.testing.assert_series_equal(result[2026],original[2026])
        self.assertEqual(result[3001].tolist(),[2.0])

    def test_augmentation_uses_computed_baseline_members_including_3003(self):
        from ensemble_ids import computed_standalone_members
        from types import SimpleNamespace
        from unittest.mock import patch
        class DSS:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def getPathnameList(self,pattern):return [
                '//Lookout Point-Pool/FLOW-OUT//1DAY/C:002000|CON_SEASON0/',
                '//Lookout Point-Pool/FLOW-OUT//1DAY/C:003003|CON_SEASON0/',
                '//Lookout Point-Pool/FLOW-OUT//1DAY/C:002001|OTHER0/']
        with patch.dict(sys.modules,{'pydsstools.heclib.dss':SimpleNamespace(HecDss=SimpleNamespace(Open=lambda path:DSS()))}):
            self.assertEqual(computed_standalone_members('simulation.dss','Con_Season'),[2000,3003])

    def test_standalone_collision_fails_instead_of_overwrite(self):
        with self.assertRaises(ValueError):
            add_percentile_members(pd.DataFrame({3000: [1.0]}))

    def test_standalone_and_rts_use_identical_synthetic_ids(self):
        result = add_percentile_members(pd.DataFrame({1981: [1.0], 1982: [3.0]}))
        self.assertEqual(result[3001].tolist(), [2.0])
        pd.testing.assert_frame_equal(result,add_percentile_members(pd.DataFrame({1981:[1.0],1982:[3.0]}),forecast=True))
