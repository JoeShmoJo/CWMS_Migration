import json
import ast
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'migration-review/ExternalPython'))
from rts_workflow import same_forecast, script_arguments, promote_extract, workflow_lock
from prepare_rts_augmentation import sha256


def context(root):
    return {'forecast_name': 'test', 'run_name': 'ConSeason', 'timezone': 'GMT-08:00',
            'lookback': ['08Oct2026', '2400'], 'start': ['09Oct2026', '2400'],
            'end': ['01Oct2027', '2400'], 'dss_path': str(root / 'forecast.dss')}


class WorkflowTests(unittest.TestCase):
    def test_menu_reads_selected_forecast_api_on_ui_thread(self):
        from types import SimpleNamespace
        source = Path(__file__).resolve().parents[1] / 'migration-review/RTS_WORKFLOW_MENU.py'
        tree = ast.parse(source.read_text())
        nodes = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'NoForecastError'
                 or isinstance(node, ast.FunctionDef) and node.name == 'forecast_context']
        window = SimpleNamespace(getLookbackDateString=lambda: '08Oct2026', getLookbackHrMinString=lambda: '2400',
            getStartDateString=lambda: '09Oct2026', getStartHrMinString=lambda: '2400',
            getEndDateString=lambda: '01Oct2027', getEndHrMinString=lambda: '2400')
        tab = SimpleNamespace(getForecast=lambda: SimpleNamespace(getName=lambda: 'test'),
            getSelectedForecastRun=lambda: SimpleNamespace(getName=lambda: 'ConSeason',
                getForecastDssFilename=lambda: '/tmp/forecast/forecast.dss', getRunTimeWindow=lambda: window),
            getTimeZone=lambda: SimpleNamespace(getID=lambda: 'GMT-08:00'))
        namespace = {'CAVI': SimpleNamespace(getCaviFrame=lambda: SimpleNamespace(getForecastTab=lambda: tab))}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), namespace)
        result = namespace['forecast_context']()
        self.assertEqual(result['end'], ['01Oct2027', '2400'])
        self.assertEqual(result['run_name'], 'ConSeason')
        tab.getForecast = lambda: None
        with self.assertRaises(namespace['NoForecastError']):
            namespace['forecast_context']()

    def test_argument_routes_preserve_historical_synthetic_separation(self):
        settings = {'scheme': 'scheme_02', 'members': '1981-1991', 'synthetic_members': '3000-3002',
                    'run_code': 'C0', 'season_year': '2027', 'season_end': '2027-09-30',
                    'wy_type_mode': 'fixed-abundant', 'forecast_days': '10'}
        script, args = script_arguments('prepare', Path('/tmp/forecast'), settings)
        self.assertEqual(script, 'prepare_rts_augmentation.py')
        self.assertEqual(args[args.index('--members') + 1], '1981-1991,3000-3002')
        script, args = script_arguments('compare', Path('/tmp/forecast'), settings)
        self.assertEqual(args[args.index('--members') + 1], '1981-1991')
        self.assertEqual(args[args.index('--synthetic-members') + 1], '3000-3002')

    def test_context_changes_detected(self):
        first = context(Path('/tmp/forecast'))
        second = dict(first, end=['31Oct2027', '2400'])
        self.assertFalse(same_forecast(first, second))

    def test_failed_or_mismatched_extract_never_replaces_live(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = context(root)
            live = root / 'forecast.dss'
            live.write_bytes(b'live')
            folder = root / 'extraction-test-unit'
            folder.mkdir()
            (folder / 'forecast.dss').write_bytes(b'new')
            with self.assertRaises(FileNotFoundError):
                promote_extract(data, folder)
            completed = {'status': 'complete', 'context': dict(data, end=['31Oct2027', '2400']),
                         'dss_sha256': sha256(folder / 'forecast.dss')}
            (folder / 'extraction-complete.json').write_text(json.dumps(completed))
            with self.assertRaisesRegex(ValueError, 'does not match'):
                promote_extract(data, folder)
            self.assertEqual(live.read_bytes(), b'live')
            completed['context'] = data
            (folder / 'extraction-complete.json').write_text(json.dumps(completed))
            promote_extract(data, folder)
            self.assertEqual(live.read_bytes(), b'new')
            self.assertEqual(len(list(root.glob('forecast.before-menu-extract-*.dss'))), 1)
            (root / 'augmentation-archives/baseline').mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, 'archived baseline'):
                promote_extract(data, folder)

    def test_second_task_cannot_acquire_lock_and_failure_releases_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, 'task failure'):
                with workflow_lock(root, 'prepare'):
                    with self.assertRaisesRegex(RuntimeError, 'Another menu task'):
                        with workflow_lock(root, 'extract'):
                            pass
                    raise ValueError('task failure')
            self.assertFalse((root / '.rts-workflow-task.json').exists())


if __name__ == '__main__':
    unittest.main()
