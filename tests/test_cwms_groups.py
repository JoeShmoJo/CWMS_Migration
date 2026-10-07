"""Test orchestration without importing the Windows DSS extension."""
import ast
from pathlib import Path
import unittest

source = Path(__file__).resolve().parents[1] / 'migration-review' / 'ExternalPython' / 'CWMS_Downloader_Module.py'
node = next(n for n in ast.parse(source.read_text()).body
            if isinstance(n, ast.FunctionDef) and n.name == 'prepare_cwms_groups')
namespace = {}
exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), 'exec'), namespace)
prepare = namespace['prepare_cwms_groups']


class GroupTests(unittest.TestCase):
    def test_optional_failure_does_not_block_remaining_groups(self):
        calls = []
        def download(mapping, begin, end, **options):
            calls.append(mapping)
            if mapping == 'plot1':
                raise ValueError('missing historical data')
            return 11
        required = ('lookback', 'required', 0, 1, {})
        optional = [('history', 'plot1', 0, 1, {}), ('outflows', 'plot2', 0, 1, {})]
        count, warnings = prepare(required, optional, download)
        self.assertEqual(calls, ['required', 'plot1', 'plot2'])
        self.assertEqual(count, 11)
        self.assertEqual(len(warnings), 1)

    def test_required_failure_stops_before_plotting(self):
        calls = []
        def download(mapping, begin, end, **options):
            calls.append(mapping)
            raise ValueError('lookback does not cover requested window')
        with self.assertRaises(ValueError):
            prepare(('lookback', 'required', 0, 1, {}), [('history', 'plot1', 0, 1, {})], download)
        self.assertEqual(calls, ['required'])
