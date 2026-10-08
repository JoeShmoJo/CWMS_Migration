from pathlib import Path
import sys
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'migration-review/ExternalPython'))
from plot_rts_augmentation import paired_frames, comparison_figure
from plot_rts_forecast import index_page


class ComparisonTests(unittest.TestCase):
    def test_statistics_use_paired_values(self):
        dates = pd.date_range('2027-04-01', periods=2)
        baseline = pd.DataFrame({1981: [1, 2], 1982: [10, 20]}, index=dates)
        augmented = pd.DataFrame({1981: [3, float('nan')], 1982: [12, 22]}, index=dates)
        left, right = paired_frames(baseline, augmented)
        self.assertTrue(pd.isna(left.loc[dates[1], 1981]))
        self.assertEqual(left.loc[dates[1]].median(), 20)
        self.assertEqual(right.loc[dates[1]].median(), 22)

    def test_targets_and_synthetic_traces_are_separate_from_historical_median(self):
        dates = pd.date_range('2027-04-01', periods=2)
        baseline = pd.DataFrame({1981: [10, 20]}, index=dates)
        augmented = pd.DataFrame({1981: [11, 22]}, index=dates)
        synthetic = pd.DataFrame({3000: [1000, 2000]}, index=dates)
        targets = pd.DataFrame({1981: [15, 15], 3000: [15, 15]}, index=dates)
        fig = comparison_figure(baseline, augmented, 'Comparison', 'CFS', synthetic, synthetic,
                                targets, 'Flow target')
        median = next(t for t in fig.data if t.name == 'Augmented median')
        self.assertEqual(list(median.y), [11, 22])
        target = next(t for t in fig.data if t.name == 'Flow target')
        self.assertEqual(list(target.y), [15, 15])
        self.assertTrue(any('Baseline Daily' in t.name for t in fig.data if t.name))
        page = index_page([('comparison-001.html', 'Comparison', 'Blue River-Pool', 'ELEV')], 'test', 'C0')
        self.assertIn('href="comparison-001.html"', page)


if __name__ == '__main__':
    unittest.main()
