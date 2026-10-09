import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'migration-review/ExternalPython'))
import baseline_versions as versions


def fake_fingerprint(path, code):
    # A changed DSS housekeeping byte does not change the logical values.
    value = path.read_bytes().split(b'|')[0].decode()
    records = {'//Test-Pool/ELEV//1DAY/C:001981|C0/': value,
               '//Test-Pool/FLOW-OUT//1DAY/C:001981|C0/': value}
    return {'sha256': hashlib.sha256(json.dumps(records).encode()).hexdigest(), 'records': records}


class BaselineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.live = self.root / 'forecast.dss'
        self.live.write_bytes(b'100|layout-1')
        self.context = {'forecast_name': 'test', 'run_name': 'ConSeason', 'end': ['01Oct2027', '2400']}

    def save(self):
        return versions.save_baseline(self.root, self.context, 'C0', fake_fingerprint)

    def archive(self):
        archive = self.root / 'augmentation-archives'
        scheme = archive / 'scheme_02'
        scheme.mkdir()
        manifest = {'scheme': 'scheme_02', 'baseline_sha256': versions.registry(self.root)['versions']['baseline-0001']['sha256']}
        (scheme / 'manifest.json').write_text(json.dumps(manifest))
        result = scheme / 'results-test'
        result.mkdir()
        (result / 'capture.json').write_text(json.dumps(dict(manifest, captured_utc='2026-10-08T00:00:00+00:00')))
        (result / 'forecast.dss').write_bytes(b'augmented')
        return result, manifest

    def test_identical_data_keeps_version_and_original_file(self):
        self.assertEqual(self.save(), ('baseline-0001', True))
        versions.load_baseline(self.root, self.context, 'C0')
        self.live.write_bytes(b'100|different-housekeeping')
        self.assertEqual(self.save(), ('baseline-0001', False))
        self.assertEqual(versions.baseline_directory(self.root).joinpath('forecast.dss').read_bytes(), b'100|layout-1')
        actions = [json.loads(line)['action'] for line in (self.root / 'augmentation-archives/action-history.jsonl').read_text().splitlines()]
        self.assertEqual(actions, ['baseline-saved', 'baseline-loaded', 'baseline-save-unchanged'])

    def test_changed_results_keep_original_pair_and_label_previous(self):
        self.save()
        result, legacy_manifest = self.archive()
        versions.load_baseline(self.root, self.context, 'C0')
        self.live.write_bytes(b'200|layout-1')
        self.assertEqual(self.save(), ('baseline-0002', True))
        self.assertEqual(versions.baseline_directory(self.root, legacy_manifest).name, 'baseline')
        self.assertEqual(versions.baseline_directory(self.root).name, 'baseline-0002')
        row = versions.write_archive_index(self.root)[0]
        self.assertEqual(row['baseline_status'], 'Previous baseline')
        self.assertEqual(row['baseline_id'], 'baseline-0001')
        self.assertTrue(result.is_dir())
        self.assertEqual((self.root / 'augmentation-archives/baseline/forecast.dss').read_bytes(), b'100|layout-1')

    def test_active_augmentation_and_missing_load_session_cannot_save(self):
        self.save()
        session = self.root / 'augmentation-archives/baseline-edit-session.json'
        session.unlink()
        with self.assertRaisesRegex(ValueError, 'Load baseline first'):
            self.save()
        (self.root / 'rts-augmentation-active.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'Augmentation is active'):
            self.save()
        self.assertEqual(versions.registry(self.root)['current'], 'baseline-0001')

    def test_load_baseline_restores_copy_disables_augmentation_and_backs_up_live(self):
        self.save()
        self.live.write_bytes(b'augmented-data')
        (self.root / 'rts-augmentation-active.json').write_text('{"scheme":"test"}')
        versions.load_baseline(self.root, self.context, 'C0')
        self.assertEqual(self.live.read_bytes(), b'100|layout-1')
        self.assertFalse((self.root / 'rts-augmentation-active.json').exists())
        self.assertEqual(next(self.root.glob('forecast.before-baseline-*.dss')).read_bytes(), b'augmented-data')

    def test_delete_only_result_retains_baseline_scheme_and_audit(self):
        self.save()
        result, _ = self.archive()
        versions.delete_result(self.root, result)
        self.assertFalse(result.exists())
        self.assertTrue(result.parent.joinpath('manifest.json').exists())
        self.assertTrue(versions.baseline_directory(self.root).joinpath('forecast.dss').exists())
        self.assertEqual(versions.write_archive_index(self.root), [])
        history = (self.root / 'augmentation-archives/action-history.jsonl').read_text()
        self.assertIn('result-deleted', history)
        with self.assertRaisesRegex(ValueError, 'Choose an archived'):
            versions.delete_result(self.root, versions.baseline_directory(self.root))
        with self.assertRaisesRegex(ValueError, 'Choose an archived'):
            versions.delete_result(self.root, result.parent)

    def test_legacy_baseline_registration_preserves_sha_and_old_scheme_resolution(self):
        archive = self.root / 'augmentation-archives/baseline'
        archive.mkdir(parents=True)
        archive.joinpath('forecast.dss').write_bytes(b'legacy')
        digest = versions.digest_file(archive / 'forecast.dss')
        archive.joinpath('manifest.json').write_text(json.dumps({'sha256': digest, 'run_code': 'C0'}))
        self.assertEqual(versions.baseline_directory(self.root, {'baseline_sha256': digest}), archive)
        self.assertEqual(versions.registry(self.root)['current'], 'baseline-0001')
        self.assertEqual(archive.joinpath('forecast.dss').read_bytes(), b'legacy')

    def test_missing_series_rejected_without_changing_baseline(self):
        self.save()
        versions.load_baseline(self.root, self.context, 'C0')
        def missing(path, code):
            return {'sha256': 'changed', 'records': {}}
        with self.assertRaisesRegex(ValueError, 'lost 2'):
            versions.save_baseline(self.root, self.context, 'C0', missing)
        self.assertEqual(versions.registry(self.root)['current'], 'baseline-0001')
        self.assertFalse(list((self.root / 'augmentation-archives').glob('baseline-pending-*')))

    def complete_scheme(self, scheme, manifest):
        scheme.joinpath('augmentation.dss').write_bytes(b'releases')
        manifest.update(status='prepared-not-computed', forecast_root=str(self.root),
                        run_code='C0', members=[1981], configuration_sha256={},
                        augmentation_sha256=versions.digest_file(scheme / 'augmentation.dss'))
        scheme.joinpath('manifest.json').write_text(json.dumps(manifest))

    def test_previous_scheme_cannot_be_loaded_for_compute(self):
        import load_rts_augmentation as loader
        self.save()
        result, manifest = self.archive()
        self.complete_scheme(result.parent, manifest)
        versions.load_baseline(self.root, self.context, 'C0')
        self.live.write_bytes(b'200|new')
        self.save()
        args = ['load', '--forecast-root', str(self.root), '--scheme', 'scheme_02']
        with patch.object(sys, 'argv', args), self.assertRaisesRegex(ValueError, 'Previous baseline'):
            loader.main()
        self.assertEqual(self.live.read_bytes(), b'200|new')
        self.assertFalse((self.root / 'rts-augmentation-active.json').exists())

    def test_previous_pair_plots_without_live_forecast_and_preserves_earlier_plots(self):
        import plot_rts_augmentation as plotting
        self.save()
        result, manifest = self.archive()
        self.complete_scheme(result.parent, manifest)
        capture_path = result / 'capture.json'
        metadata = json.loads(capture_path.read_text())
        metadata['sha256'] = versions.digest_file(result / 'forecast.dss')
        capture_path.write_text(json.dumps(metadata))
        dates = pd.date_range('2027-05-15', periods=2)
        pd.DataFrame({'LOP_min_flow_with_aug': [125, 125]}, index=dates).to_csv(result.parent / 'member-1981.csv')
        versions.load_baseline(self.root, self.context, 'C0')
        self.live.write_bytes(b'200|new')
        self.save()
        self.live.unlink()  # Archived plotting must never require the live DSS.
        opened = []
        class FakeDSS:
            def __init__(self, filename):
                self.filename = Path(filename)
                opened.append(self.filename)
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def getPathnameList(self, pattern):
                return ['//Lookout Point-Pool/Flow-OUT/01Jan2027/1Day/C:001981|C0/']
            def read_ts(self, path, **kwargs):
                value = 100 if self.filename.parent.name == 'baseline' else 150
                return SimpleNamespace(values=[value, value], pytimes=dates, units='CFS')
        fake = SimpleNamespace(HecDss=SimpleNamespace(Open=FakeDSS))
        args = ['plot', '--forecast-root', str(self.root), '--scheme', 'scheme_02',
                '--result-dir', str(result), '--members', '1981', '--synthetic-members', '']
        with patch.object(sys, 'argv', args), patch.dict(sys.modules, {'pydsstools.heclib.dss': fake}), \
                patch.object(plotting, 'read_config', return_value=({'Lookout Point': 'LOP'},)):
            plotting.main()
            plotting.main()
        self.assertEqual(len(list(result.glob('plots-*'))), 2)
        self.assertNotIn(versions.baseline_directory(self.root) / 'forecast.dss', opened)
        for page in result.glob('plots-*/index.html'):
            self.assertIn('Previous baseline (baseline-0001)', page.read_text())
        for difference in result.glob('plots-*/comparison-*-paired-difference.csv'):
            self.assertEqual(pd.read_csv(difference)['1981'].tolist(), [50, 50])

    def test_fingerprint_reads_cataloged_blocks_and_merges_overlap(self):
        calls=[]
        class FakeDSS:
            def read_ts(self,path,trim_missing=True):
                calls.append(path)
                if '/01Jan2026/' in path:
                    dates=['2026-12-31','2027-01-01'];values=[1,2]
                else: dates=['2027-01-01','2027-01-02'];values=[2,3]
                return SimpleNamespace(pytimes=pd.to_datetime(dates),values=values,units='Feet',type='INST-VAL')
        logical='//Test-Pool/ELEV//1Day/C:001981|C0/'
        paths=['//Test-Pool/ELEV/01Jan2026/1Day/C:001981|C0/','//Test-Pool/ELEV/01Jan2027/1Day/C:001981|C0/']
        times,values,units,kind=versions.read_fingerprint_series(FakeDSS(),logical,paths)
        self.assertEqual(values.tolist(),[1,2,3]);self.assertEqual(calls,paths)
        empty=SimpleNamespace(read_ts=lambda *args,**kwargs:SimpleNamespace(pytimes=None,values=None))
        with self.assertRaisesRegex(ValueError,'01Jan2026'):
            versions.read_fingerprint_series(empty,logical,paths)

    def test_unrelated_outputs_are_not_read_but_empty_pool_elevation_fails(self):
        names=['//Test-Pool/ELEV/01Jan2026/1Day/C:001981|C0/',
               '//Test-Pool/FLOW-OUT/01Jan2026/1Day/C:001981|C0/',
               '//Big Cliff-Inactive-ZBOp Rule/FLOW-SPEC/01Jan2026/1Day/C:001981|C0/',
               '//MainstemFlowAugSV/Flow/01Jan2027/1Day/C:001981|C0/',
               '//Test-Powerhouse/FLOW-OUT/01Jan2027/1Day/C:001981|C0/',
               '//Test-Tailwater/ELEV/01Jan2027/1Day/C:001981|C0/']
        empty_elevation=False
        rule_values=None
        class FakeDSS:
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def getPathnameList(self,pattern): return names
            def read_ts(self,path,trim_missing=True):
                if not '/Test-Pool/' in path: raise AssertionError('Read unrelated output: '+path)
                empty=('/FLOW-SPEC/' in path and rule_values is None) or ('/ELEV/' in path and empty_elevation)
                return SimpleNamespace(pytimes=None if empty else pd.date_range('2026-10-10',periods=2),
                    values=None if empty else (rule_values if '/FLOW-SPEC/' in path else [1,2]),units='Feet',type='INST-VAL')
        fake=SimpleNamespace(HecDss=SimpleNamespace(Open=lambda name:FakeDSS()))
        with patch.dict(sys.modules,{'pydsstools.heclib.dss':fake}):
            first=versions.semantic_fingerprint(self.live,'C0')
            self.assertEqual(len(first['records']),2)
            rule_values=[0,0]
            self.assertEqual(first['sha256'],versions.semantic_fingerprint(self.live,'C0')['sha256'])
            empty_elevation=True
            with self.assertRaisesRegex(ValueError,'Test-Pool/ELEV'):
                versions.semantic_fingerprint(self.live,'C0')

    def test_logical_series_ignore_calendar_blocks_case_missing_payloads_and_other_runs(self):
        names = ['//Test-Pool/ELEV/01Jan2026/1Day/C:001981|C0/',
                 '//Test-Pool/ELEV/01Jan2027/1Day/C:001981|C0/',
                 '//Test-Pool/FLOW-OUT/01Jan2026/1Day/C:001981|C0/',
                 '//SALEM/FLOW-MIN-EXTERNALFLOWAUG//1Day/C:001981|C0/',
                 '//Test-Pool/ELEV//1Day/C:001981|C1/']
        values = [1.0, -3.402823466e38]
        class FakeDSS:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def getPathnameList(self, pattern): return names
            def read_ts(self, path, trim_missing=True):
                return SimpleNamespace(pytimes=pd.date_range('2026-10-10', periods=2), values=np.array(values), units='Feet', type='INST-VAL')
        fake = SimpleNamespace(HecDss=SimpleNamespace(Open=lambda name: FakeDSS()))
        with patch.dict(sys.modules, {'pydsstools.heclib.dss': fake}):
            first = versions.semantic_fingerprint(self.live, 'C0')
            values[1] = np.nan
            names[:] = [name.lower() for name in names[:3]]
            second = versions.semantic_fingerprint(self.live, 'C0')
            self.assertEqual(first, second)
            self.assertEqual(len(first['records']), 2)
            values[0] = 2.0
            self.assertNotEqual(first['sha256'], versions.semantic_fingerprint(self.live, 'C0')['sha256'])


if __name__ == '__main__':
    unittest.main()
