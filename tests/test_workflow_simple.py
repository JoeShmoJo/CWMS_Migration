import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'migration-review/ExternalPython'))
import workflow_simple as workflow
import baseline_versions as versions
from plot_rts_runs import plot_saved_runs


def configuration(name='portable'):
    return {'schema': 1, 'name': name, 'columns': ['Variable', 'Lookout Point', 'Hills Creek'],
        'rows': [['Abbreviation', 'LOP', 'HCR'], ['SupportsSalem', 'TRUE', 'FALSE'],
                 ['SupportsAlbany', 'TRUE', 'FALSE'], ['MinConStor', '118800', '155400'],
                 ['MaxRelease', '2700', '1800'], ['TravelTimeDays', '2', '2']],
        'calculation': {'forecast_days': 10, 'wy_type_mode': 'fixed-abundant'}}


def fake_fingerprint(path, code):
    value = path.read_bytes().decode()
    return {'sha256': value, 'records': {'elevation': value, 'outflow': value}}


class SimpleWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.live = self.root / 'forecast.dss'
        self.live.write_bytes(b'100')
        self.context = {'forecast_name': 'test', 'run_name': 'ConSeason', 'timezone': 'GMT-08:00',
            'lookback': ['08Oct2026', '2400'], 'start': ['09Oct2026', '2400'],
            'end': ['30Sep2027', '2400'], 'dss_path': str(self.live)}
        self.scripts = self.root / 'scripts/ExternalPython'
        self.scripts.mkdir(parents=True)
        (self.scripts.parent / 'externalSVs').mkdir()
        workflow.write_configuration_csv(configuration(), self.scripts.parent / 'externalSVs' / workflow.CONFIG_NAME)
        self.dates = pd.date_range('2026-10-10', '2027-09-30')
        root = self.root
        dates = self.dates
        class FakeDSS:
            def __init__(self, filename): self.filename = Path(filename)
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def getPathnameList(self, pattern):
                return ['//Lookout Point-Pool/Elev/01Jan2027/1Day/C:001987|C0/',
                        '//Lookout Point-Pool/Flow-OUT/01Jan2027/1Day/C:001987|C0/',
                        '//Lookout Point-Pool/Elev/01Jan2027/1Day/C:003001|C0/',
                        '//Lookout Point-Pool/Flow-OUT/01Jan2027/1Day/C:003001|C0/']
            def read_ts(self, path, **kwargs):
                value = float(self.filename.read_text())
                units = 'FT' if path.split('/')[3].upper() == 'ELEV' else 'CFS'
                return SimpleNamespace(values=np.full(len(dates), value), pytimes=dates, units=units, type='INST-VAL')
        self.fake_module = SimpleNamespace(HecDss=SimpleNamespace(Open=FakeDSS))

    def baseline(self):
        versions.save_baseline(self.root, self.context, 'C0', fake_fingerprint)

    def augmented(self, value=150, name='alpha'):
        archive = self.root / 'augmentation-archives'
        scheme = archive / name
        scheme.mkdir()
        (scheme / 'augmentation.dss').write_bytes(b'prepared')
        csv_path = scheme / workflow.CONFIG_NAME
        workflow.write_configuration_csv(configuration(name), csv_path)
        version = versions.registry(self.root)['versions']['baseline-0001']
        manifest = {'status': 'prepared-not-computed', 'scheme': name, 'configuration_name': name,
            'forecast_root': str(self.root), 'run_code': 'C0', 'members': [1987, 3001],
            'baseline_id': 'baseline-0001', 'baseline_sha256': version['sha256'],
            'augmentation_sha256': versions.digest_file(scheme / 'augmentation.dss'),
            'configuration_sha256': {csv_path.name: versions.digest_file(csv_path)}}
        (scheme / 'manifest.json').write_text(json.dumps(manifest))
        for member in manifest['members']:
            pd.DataFrame({'LOP_min_flow_with_aug': np.full(len(self.dates), 125)}, index=self.dates).to_csv(scheme / ('member-{}.csv'.format(member)))
        result = scheme / 'results-test'
        result.mkdir()
        (result / 'forecast.dss').write_text(str(value))
        (result / 'capture.json').write_text(json.dumps({'scheme': name, 'baseline_id': 'baseline-0001',
            'baseline_sha256': version['sha256'], 'sha256': versions.digest_file(result / 'forecast.dss'),
            'captured_utc': '2026-10-08T00:00:00+00:00'}))
        return result, manifest

    def test_configuration_round_trip_is_portable_and_leaves_original_csv(self):
        original = self.scripts.parent / 'externalSVs' / workflow.CONFIG_NAME
        before = original.read_bytes()
        config = workflow.read_configuration(original)
        config['name'] = 'scheme shared across forecasts'
        config['forecast_name'] = 'must not leak into reusable config'
        target = self.root / 'library.json'
        workflow.save_configuration(config, target)
        saved = json.loads(target.read_text())
        self.assertNotIn('forecast_name', saved)
        self.assertNotIn('members', saved)
        self.assertEqual(saved['rows'], configuration()['rows'])
        self.assertEqual(original.read_bytes(), before)
        config['rows'][2][1] = 'FALSE'
        with self.assertRaisesRegex(ValueError, 'identical Salem/Albany'):
            workflow.save_configuration(config, self.root / 'invalid.json')
        self.assertFalse((self.root / 'invalid.json').exists())

    def test_unused_elevation_parameters_still_reject_nonfinite_values(self):
        config = configuration()
        config['rows'].append(['SummerBufferElev', 'NaN', '1470'])
        with self.assertRaisesRegex(ValueError, 'Nonfinite numeric'):
            workflow.save_configuration(config, self.root / 'invalid.json')
        self.assertFalse((self.root / 'invalid.json').exists())

    def test_member_ranges_and_season_are_inferred_from_actual_outputs(self):
        with patch.dict(sys.modules, {'pydsstools.heclib.dss': self.fake_module}):
            details = workflow.inspect_run(self.live)
        self.assertEqual(details['members'], [1987])
        self.assertEqual(details['synthetic_members'], [3001])
        self.assertEqual(details['seasons'], [{'year': 2027, 'end': '2027-09-30'}])
        self.assertEqual(details['run_code'], 'C0')

    def test_reset_disables_only_and_does_not_mark_previous_until_compute_accepted(self):
        with patch.dict(sys.modules, {'pydsstools.heclib.dss': self.fake_module}):
            versions.save_baseline(self.root, self.context, 'C0')
        result, manifest = self.augmented()
        self.live.write_bytes(b'150')
        (self.root / 'rts-augmentation-active.json').write_text(json.dumps(manifest))
        workflow.reset_baseline(self.root, self.context)
        self.assertEqual(self.live.read_bytes(), b'150')
        self.assertFalse((self.root / 'rts-augmentation-active.json').exists())
        self.assertEqual(versions.registry(self.root)['current'], 'baseline-0001')
        self.assertEqual(versions.write_archive_index(self.root)[0]['baseline_status'], 'Current baseline')
        self.live.write_bytes(b'200')  # Operator has now completed an unaugmented compute.
        with patch.dict(sys.modules, {'pydsstools.heclib.dss': self.fake_module}):
            workflow.accept_completed(self.root, self.context)
        self.assertEqual(versions.registry(self.root)['current'], 'baseline-0002')
        self.assertEqual(versions.write_archive_index(self.root)[0]['baseline_status'], 'Previous baseline')
        self.assertTrue(result.is_dir())

    def test_pending_reset_cannot_process_without_completed_baseline(self):
        self.baseline()
        workflow.reset_baseline(self.root, self.context)
        with self.assertRaisesRegex(ValueError, 'baseline compute is pending'):
            workflow.process_configuration(self.root, self.context, {'confirm_completed': False}, self.scripts)
        self.assertEqual(self.live.read_bytes(), b'100')

    def test_initial_extract_cannot_fall_back_to_an_older_archive(self):
        archive = self.root / 'extraction-test-old'
        archive.mkdir()
        (archive / 'extraction-complete.json').write_text(json.dumps({'context': self.context, 'status': 'complete'}))
        data = dict(self.context, menu_settings={})
        with patch.object(workflow.subprocess, 'run'), self.assertRaisesRegex(ValueError, 'one newly completed'):
            workflow.execute_simple('initial-extract', SimpleNamespace(context='dummy.json'), data, self.scripts)
        self.assertEqual(self.live.read_bytes(), b'100')

    def test_initial_extract_archives_and_loads_only_this_new_success(self):
        old = self.root / 'extraction-test-old'
        old.mkdir()
        (old / 'extraction-complete.json').write_text(json.dumps({'context': self.context, 'status': 'complete'}))
        def successful(command, **kwargs):
            new = self.root / 'extraction-test-new'
            new.mkdir()
            (new / 'forecast.dss').write_bytes(b'new-inputs')
            (new / 'extraction-complete.json').write_text(json.dumps({'context': self.context, 'status': 'complete',
                'dss_sha256': versions.digest_file(new / 'forecast.dss')}))
        with patch.object(workflow.subprocess, 'run', side_effect=successful):
            workflow.execute_simple('initial-extract', SimpleNamespace(context='dummy.json'), dict(self.context, menu_settings={}), self.scripts)
        self.assertEqual(self.live.read_bytes(), b'new-inputs')
        self.assertTrue((self.root / 'extraction-test-new/forecast.dss').exists())
        self.assertEqual(next(self.root.glob('forecast.before-menu-extract-*.dss')).read_bytes(), b'100')
        self.assertEqual(json.loads((self.root / 'augmentation-archives/workflow-pending.json').read_text())['mode'], 'baseline')

    def test_failed_extraction_never_loads_partial_data(self):
        data = dict(self.context, menu_settings={})
        with patch.object(workflow.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'extract')):
            with self.assertRaises(subprocess.CalledProcessError):
                workflow.execute_simple('initial-extract', SimpleNamespace(context='dummy.json'), data, self.scripts)
        self.assertEqual(self.live.read_bytes(), b'100')

    def test_single_or_two_saved_runs_plot_without_live_dss_with_release_overlay(self):
        self.baseline()
        result, _ = self.augmented()
        runs = workflow.catalog(self.root)
        self.live.unlink()
        with patch.dict(sys.modules, {'pydsstools.heclib.dss': self.fake_module}):
            single = plot_saved_runs(self.root, [runs[1]])
            pair = plot_saved_runs(self.root, runs)
        # Both sources are cached now: a different comparison must work with
        # all DSS opens forbidden and must never request an absent rule curve.
        no_dss = SimpleNamespace(HecDss=SimpleNamespace(Open=lambda *args: self.fail('Plot reopened DSS')) )
        with patch.dict(sys.modules, {'pydsstools.heclib.dss': no_dss}):
            reused = plot_saved_runs(self.root, runs)
        self.assertEqual(json.loads((reused / 'selection.json').read_text())['rule_curve_source'], 'CSV')
        self.assertTrue((reused / 'CON_SEASON_RULE_CURVES.csv').is_file())
        self.assertTrue(list(reused.glob('plot-*-rule-curve.csv')))
        self.assertIn('alpha', (single / 'index.html').read_text())
        self.assertTrue(any('Prepared augmentation minimum release' in page.read_text() for page in single.glob('plot-*.html')))
        for difference in pair.glob('plot-*-paired-difference.csv'):
            self.assertTrue((pd.read_csv(difference)['1987'] == 50).all())
        self.assertTrue(result.is_dir())
        self.assertFalse(self.live.exists())

    def test_two_augmentation_results_can_be_compared(self):
        self.baseline()
        self.augmented(150, 'alpha')
        self.augmented(175, 'beta')
        runs = [row for row in workflow.catalog(self.root) if row['kind'] == 'augmented']
        with patch.dict(sys.modules, {'pydsstools.heclib.dss': self.fake_module}):
            destination = plot_saved_runs(self.root, runs)
        for difference in destination.glob('plot-*-paired-difference.csv'):
            self.assertTrue((pd.read_csv(difference)['1987'] == 25).all())

    def test_varying_release_requirements_have_a_visible_range_and_exact_member_traces(self):
        from plot_rts_runs import add_requirements
        import plotly.graph_objects as go
        dates = pd.date_range('2027-04-01', periods=2)
        frame = pd.DataFrame({1981: [100, 200], 1982: [150, 300]}, index=dates)
        fig = go.Figure()
        add_requirements(fig, frame, 'Prepared minimum release')
        visible = next(trace for trace in fig.data if trace.name and 'range across members' in trace.name)
        self.assertEqual(list(visible.y), [150, 300])
        self.assertEqual(visible.fill, 'tonexty')
        individual = [trace for trace in fig.data if trace.visible == 'legendonly']
        self.assertEqual(len(individual), 2)
        self.assertEqual(list(individual[0].y), [100, 200])

    def test_delete_result_removes_associated_plot_archives_only(self):
        self.baseline()
        result, _ = self.augmented()
        runs = workflow.catalog(self.root)
        with patch.dict(sys.modules, {'pydsstools.heclib.dss': self.fake_module}):
            keep = plot_saved_runs(self.root, [runs[0]])
            remove = plot_saved_runs(self.root, runs)
        versions.delete_result(self.root, result, include_plots=True)
        self.assertTrue(keep.is_dir())
        self.assertFalse(remove.exists())
        self.assertFalse(result.exists())
        self.assertTrue(versions.baseline_directory(self.root).is_dir())
        history = (self.root / 'augmentation-archives/action-history.jsonl').read_text()
        self.assertIn(str(remove), history)

    def test_process_snapshots_config_then_loads_releases_for_inferred_members(self):
        from load_rts_augmentation import validate_manifest
        import shutil
        self.baseline()
        details = {'run_code': 'C0', 'members': [1987], 'synthetic_members': [3001],
                   'seasons': [{'year': 2027, 'end': '2027-09-30'}]}
        config = configuration('reusable')
        config['rows'][4][1] = '2200'
        calls = []
        def successful(command, **kwargs):
            calls.append(command)
            scheme = self.root / 'augmentation-archives' / command[command.index('--scheme') + 1]
            if command[2].endswith('prepare_rts_augmentation.py'):
                self.assertEqual(command[command.index('--members') + 1], '1987,3001')
                self.assertEqual(command[command.index('--season-end') + 1], '2027-09-30')
                source = Path(command[command.index('--config-csv') + 1])
                scheme.mkdir()
                shutil.copy2(source, scheme / source.name)
                (scheme / 'augmentation.dss').write_bytes(b'prepared releases')
                manifest = {'status': 'prepared-not-computed', 'scheme': scheme.name,
                    'forecast_root': str(self.root), 'run_code': 'C0', 'members': [1987, 3001],
                    'baseline_id': 'baseline-0001',
                    'baseline_sha256': versions.registry(self.root)['versions']['baseline-0001']['sha256'],
                    'augmentation_sha256': versions.digest_file(scheme / 'augmentation.dss'),
                    'configuration_sha256': {source.name: versions.digest_file(scheme / source.name)}}
                (scheme / 'manifest.json').write_text(json.dumps(manifest))
            else:
                self.assertTrue(command[2].endswith('load_rts_augmentation.py'))
                manifest = json.loads((scheme / 'manifest.json').read_text())
                validate_manifest(self.root, scheme, manifest)
                self.assertEqual(manifest['configuration_name'], 'reusable')
                self.assertIn('2200', (scheme / workflow.CONFIG_NAME).read_text())
                self.assertEqual(json.loads((scheme / 'configuration.json').read_text()), config)
        with patch.object(workflow, 'inspect_run', return_value=details), patch.object(workflow.subprocess, 'run', side_effect=successful):
            workflow.process_configuration(self.root, self.context, {'configuration': config, 'season_year': '2027'}, self.scripts)
        self.assertEqual(len(calls), 2)
        pending = json.loads((self.root / 'augmentation-archives/workflow-pending.json').read_text())
        self.assertEqual(pending['mode'], 'augmentation')
        self.assertEqual(pending['baseline_id'], 'baseline-0001')
        self.assertIn('2700', (self.scripts.parent / 'externalSVs' / workflow.CONFIG_NAME).read_text())

    def test_new_config_preparation_failure_does_not_load_releases(self):
        self.baseline()
        details = {'run_code': 'C0', 'members': [1987], 'synthetic_members': [3001],
                   'seasons': [{'year': 2027, 'end': '2027-09-30'}]}
        settings = {'configuration': configuration(), 'season_year': '2027'}
        calls = []
        def failed(command, **kwargs):
            calls.append(command)
            config_csv = Path(command[command.index('--config-csv') + 1])
            self.assertTrue(config_csv.is_file())
            self.assertIn('2700', config_csv.read_text())
            raise subprocess.CalledProcessError(1, command)
        with patch.object(workflow, 'inspect_run', return_value=details), patch.object(workflow.subprocess, 'run', side_effect=failed):
            with self.assertRaises(subprocess.CalledProcessError):
                workflow.process_configuration(self.root, self.context, settings, self.scripts)
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.live.read_bytes(), b'100')
        self.assertFalse((self.root / 'rts-augmentation-active.json').exists())


if __name__ == '__main__':
    unittest.main()
