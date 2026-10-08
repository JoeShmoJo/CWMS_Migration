from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'migration-review' / 'ExternalPython'))
from plot_rts_forecast import output_groups, parse_members, clean_series, quantiles, main, load_rule_curve


class PlotTests(unittest.TestCase):
    def test_rule_curve_units_ignore_capitalization(self):
        fake = types.SimpleNamespace(read_ts=lambda *args, **kwargs: types.SimpleNamespace(
            values=np.array([1450.0, 1450.0]), pytimes=pd.date_range('2026-10-09', periods=2), units='FT'))
        curve, label = load_rule_curve(fake, 'Detroit-Pool', 'ft', pd.Timestamp('2026-10-09'), pd.Timestamp('2026-10-10'), Path('unused.csv'))
        self.assertEqual(label, 'Rule curve (DSS)')
        self.assertEqual(curve.tolist(), [1450.0, 1450.0])

    def test_rule_curve_falls_back_to_supplied_schedule(self):
        def missing(*args, **kwargs):
            raise ValueError('missing DSS record')
        csv_path = Path(__file__).resolve().parents[1] / 'migration-review' / 'ExternalPython' / 'CON_SEASON_RULE_CURVES.csv'
        curve, label = load_rule_curve(types.SimpleNamespace(read_ts=missing), 'Detroit-Pool', 'ft',
                                       pd.Timestamp('2026-10-09'), pd.Timestamp('2026-10-10'), csv_path)
        self.assertEqual(label, 'Rule curve (CSV schedule)')
        self.assertEqual(len(curve), 2)
        self.assertTrue(curve.notna().all())
    def test_selects_actual_run_outputs_and_ignores_input_copies(self):
        paths = ['//Detroit-Pool/Elev/01Jan2026/1Day/C:001981|C0/',
                 '//Detroit-Pool/Elev/01Jan2027/1Day/C:001981|C0/',
                 '//Detroit-Pool/Elev/01Jan2026/1Day/C:001981|RULE CURVE-C0/',
                 '//Detroit-Pool/Elev/01Jan2026/1Day/C:001981|C1/',
                 '//Detroit-Pool/Elev/01Jan2026/1Day/C:002026|C0/',
                 '//ALBO_ Albany_HMSsub_WillametteRv_S60/Flow/01Jan2026/1Day/C:001981|C0/']
        groups = output_groups(paths, 'C0', {1981})
        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[('', 'Detroit-Pool', 'Elev', '1Day')][1981], '//Detroit-Pool/Elev//1Day/C:001981|C0/')

    def test_missing_values_are_not_plotted_as_extreme_elevations(self):
        record = types.SimpleNamespace(values=[100.0, -3.4028234663852886e38, 102.0],
                                       pytimes=pd.date_range('2026-10-09', periods=3))
        series = clean_series(record)
        self.assertEqual(len(series), 3)
        self.assertTrue(pd.isna(series.iloc[1]))
        self.assertEqual(series.dropna().tolist(), [100.0, 102.0])

    def test_quantiles_and_counts(self):
        result = quantiles(pd.DataFrame({1981: [0.0, np.nan], 1982: [100.0, 20.0]}))
        self.assertEqual(result[0.50].tolist(), [50.0, 20.0])
        self.assertEqual(result['member_count'].tolist(), [2, 1])

    def test_member_ranges(self):
        self.assertEqual(parse_members('1981-1983,3000-3002'), {1981,1982,1983,3000,3001,3002})

    def test_generates_offline_html_and_audit_from_fixture(self):
        class FakeDss:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def getPathnameList(self, pattern):
                return ['//Detroit-Pool/Elev/01Jan2026/1Day/C:001981|C0/',
                        '//Detroit-Pool/Elev/01Jan2026/1Day/C:001982|C0/']
            def read_ts(self, pathname, **kwargs):
                return types.SimpleNamespace(values=np.array([100.0, 101.0, 102.0]),
                                             pytimes=pd.date_range('2026-10-09', periods=3), units='FT')
        modules = {'pydsstools': types.ModuleType('pydsstools'),
                   'pydsstools.heclib': types.ModuleType('pydsstools.heclib'),
                   'pydsstools.heclib.dss': types.SimpleNamespace(HecDss=types.SimpleNamespace(Open=lambda path: FakeDss()))}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'forecast.dss').touch()
            with patch.dict(sys.modules, modules), patch.object(sys, 'argv', ['plot', '--forecast-root', folder, '--members', '1981-1982']):
                main()
            output = next((root / 'output_plots').iterdir())
            self.assertTrue((output / 'index.html').is_file())
            self.assertTrue((output / '_plotly.min.js').is_file())
            self.assertEqual(len(list(output.glob('*_bands.csv'))), 1)
            report = pd.read_csv(output / 'read-report.csv')
            self.assertEqual(report['status'].tolist(), ['read', 'read'])
