from datetime import datetime
from pathlib import Path
import sys
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'migration-review' / 'ExternalPython'
sys.path.insert(0, str(SCRIPTS))
from write_rule_curves import annual_table, expand, RESERVOIRS


class RuleCurveTests(unittest.TestCase):
    def test_forecast_dates_and_reservoirs(self):
        schedule = annual_table(SCRIPTS / 'CON_SEASON_RULE_CURVES.csv')
        self.assertEqual(len(schedule), 365)
        dates, values = expand(schedule, datetime(2026, 10, 8), datetime(2026, 12, 8))
        self.assertEqual(dates[0], datetime(2026, 10, 7))
        self.assertEqual(dates[-1], datetime(2026, 12, 9))
        self.assertEqual(set(values), set(RESERVOIRS))
        for i, day in enumerate(dates):
            for name in RESERVOIRS:
                self.assertEqual(values[name][i], schedule[(day.month, day.day)][name])

    def test_leap_day_not_invented(self):
        schedule = annual_table(SCRIPTS / 'CON_SEASON_RULE_CURVES.csv')
        with self.assertRaises(ValueError):
            expand(schedule, datetime(2028, 2, 28), datetime(2028, 3, 1))
