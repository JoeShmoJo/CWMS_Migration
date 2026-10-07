import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
import sys

SCRIPTS = Path(__file__).resolve().parents[1] / 'migration-review' / 'ExternalPython'
sys.path.insert(0, str(SCRIPTS))
from extraction_context import Context, load_context, parse_hec
import run_extraction


def data(path):
    return dict(forecast_name='ForecastTest2', run_name='ConSeason', dss_path=str(path),
                timezone='GMT-08:00', lookback=['07Oct2026', '2400'],
                start=['08Oct2026', '2400'], end=['07Dec2026', '2400'])


class ContextTests(unittest.TestCase):
    def test_midnight_and_utc(self):
        c = Context(data('forecast.dss'))
        self.assertEqual(c.lookback, datetime(2026, 10, 8))
        self.assertEqual(c.end, datetime(2026, 12, 8))
        self.assertEqual(c.utc(c.start), datetime(2026, 10, 9, 8, tzinfo=timezone.utc))

    def test_lookback_request_brackets_native_six_hour_grid(self):
        import pandas as pd
        c = Context(data('forecast.dss'))
        begin, end = c.lookback_request_bounds()
        self.assertEqual(begin, datetime(2026, 10, 8, 2, tzinfo=timezone.utc))
        self.assertEqual(end, datetime(2026, 10, 9, 14, tzinfo=timezone.utc))
        # Native UTC samples at 06/12/18/00 become 22/04/10/16 at GMT-08.
        native = pd.date_range('2026-10-08 06:00', '2026-10-09 12:00', freq='6h', tz='UTC')
        local = native.tz_convert(c.timezone).tz_localize(None)
        c.validate_series(pd.Series(1.0, index=local), 360, end=c.start)

    def test_bad_clock(self):
        with self.assertRaises(ValueError):
            parse_hec('07Oct2026', '2401')

    def test_bad_order(self):
        d = data('forecast.dss')
        d['end'] = d['lookback']
        with self.assertRaises(ValueError):
            Context(d)

    def test_standalone_has_no_override(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(load_context())

    def test_coverage_and_gaps(self):
        import pandas as pd
        c = Context(data('forecast.dss'))
        s = pd.Series(1.0, index=pd.date_range(c.lookback, c.end, freq='D'))
        c.validate_series(s, 1440)
        with self.assertRaises(ValueError):
            c.validate_series(s.iloc[1:], 1440)
        with self.assertRaises(ValueError):
            c.validate_series(s.drop(s.index[3]), 1440)

    def test_missing_slots_allowed_only_when_explicit(self):
        import pandas as pd
        c = Context(data('forecast.dss'))
        s = pd.Series(1.0, index=pd.date_range(c.lookback, c.end, freq='D'))
        s.iloc[3] = float('nan')
        with self.assertRaises(ValueError):
            c.validate_series(s, 1440)
        c.validate_series(s, 1440, allow_missing=True)

    def run_runner(self, execute=False, fail=False):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            live = root / 'forecast.dss'
            live.write_bytes(b'original')
            context = root / 'context.json'
            context.write_text(json.dumps(data(live)))
            names = ['RFC_Downloader_Module.py', 'CWMS_Downloader_Module.py',
                     'Dummy_0_and_WY_Abundant_Module.py', 'OSI_Ensemble_Year.py']
            for i, name in enumerate(names):
                script = "import json,os\nfrom pathlib import Path\np=Path(json.load(open(os.environ['RESSIM_EXTRACTION_CONTEXT']))['dss_path'])\np.write_bytes(p.read_bytes()+b'%d')\n" % i
                if fail and i == 1:
                    script += 'raise SystemExit(7)\n'
                (root / name).write_text(script)
            argv = ['runner', '--context', str(context)] + (['--execute'] if execute else [])
            with patch.object(run_extraction, '__file__', str(root / 'run_extraction.py')), patch.object(sys, 'argv', argv):
                if fail:
                    with self.assertRaises(RuntimeError):
                        run_extraction.main()
                else:
                    run_extraction.main()
            self.assertEqual(live.read_bytes(), b'original')
            stages = list(root.glob('extraction-test-*'))
            if execute:
                self.assertEqual(len(stages), 1)
                self.assertEqual((stages[0] / 'forecast.dss').read_bytes(), b'original01' if fail else b'original0123')
            else:
                self.assertEqual(stages, [])

    def test_plan_does_not_execute_or_copy(self):
        self.run_runner()

    def test_plan_accepts_missing_forecast_dss(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            context = root / 'context.json'
            context.write_text(json.dumps(data(root / 'forecast.dss')))
            with patch.object(sys, 'argv', ['runner', '--context', str(context)]):
                run_extraction.main()
            self.assertFalse((root / 'forecast.dss').exists())
            self.assertEqual(list(root.glob('extraction-test-*')), [])

    def test_execution_is_ordered_and_live_unchanged(self):
        self.run_runner(execute=True)

    def test_failure_stops_later_steps(self):
        self.run_runner(execute=True, fail=True)


if __name__ == '__main__':
    unittest.main()
