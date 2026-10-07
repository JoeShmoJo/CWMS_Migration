from datetime import timedelta, timezone
from pathlib import Path
import sys
import unittest
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'migration-review' / 'ExternalPython'))
from cwms_time import dss_index, preserve_gaps


class CalendarTests(unittest.TestCase):
    def test_historical_gap_keeps_later_value_on_correct_day(self):
        s = pd.Series([100.0, 102.0], index=pd.to_datetime(['2026-07-20', '2026-07-22']))
        result = preserve_gaps(s, 1440)
        self.assertEqual(len(result), 3)
        self.assertTrue(pd.isna(result.loc['2026-07-21']))
        self.assertEqual(result.loc['2026-07-22'], 102.0)

    def test_off_grid_observation_rejected(self):
        s = pd.Series([1.0, 2.0], index=pd.to_datetime(['2026-07-20', '2026-07-21 01:00'], format='mixed'))
        with self.assertRaises(ValueError):
            preserve_gaps(s, 1440)
    def test_spring_daily_labels(self):
        utc = pd.to_datetime(['2026-03-08T08:00Z', '2026-03-09T07:00Z', '2026-03-10T07:00Z'])
        result = dss_index(utc, timezone(timedelta(hours=-8)), True)
        self.assertTrue(result.equals(pd.date_range('2026-03-08', periods=3, freq='D')))

    def test_fall_daily_labels(self):
        utc = pd.to_datetime(['2026-11-01T07:00Z', '2026-11-02T08:00Z'])
        result = dss_index(utc, timezone(timedelta(hours=-8)), True)
        self.assertTrue(result.equals(pd.date_range('2026-11-01', periods=2, freq='D')))

    def test_missing_day_not_filled(self):
        utc = pd.to_datetime(['2026-03-08T08:00Z', '2026-03-10T07:00Z'])
        result = dss_index(utc, timezone(timedelta(hours=-8)), True)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[1] - result[0], pd.Timedelta(days=2))

    def test_six_hour_uses_fixed_forecast_offset(self):
        utc = pd.date_range('2026-10-08', periods=12, freq='6h', tz='UTC')
        result = dss_index(utc, timezone(timedelta(hours=-8)))
        self.assertEqual(result[0], pd.Timestamp('2026-10-07 16:00'))
        self.assertTrue((result.to_series().diff().iloc[1:] == pd.Timedelta(hours=6)).all())
