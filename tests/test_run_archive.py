import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'migration-review/ExternalPython'))
import baseline_versions as versions
from run_archive import capture_run, archive_digest, metadata
from run_data_cache import open_cached_run
from workflow_simple import inspect_run


class CompactArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root/'forecast.dss'
        self.source.write_bytes(b'live data must never be copied wholesale')
        self.target = self.root/'augmentation-archives/baseline'
        self.target.mkdir(parents=True)
        self.calls = []
        self.value = 100.0
        self.mutate = False
        self.bad = False
        self.empty_optional = False
        self.extra_date_block = False
        self.required = ['//Lookout Point-Pool/ELEV/01Jan2027/1DAY/C:002000|C0/',
                         '//Lookout Point-Pool/FLOW-OUT/01Jan2027/1DAY/C:002000|C0/',
                         '//Lookout Point-Pool/STOR/01Jan2027/1DAY/C:002000|C0/',
                         '//Willamette_at Salem/FLOW/01Jan2027/1DAY/C:002000|C0/']
        self.optional = '//Lookout Point-Combined Min Trib/FLOW-SPEC/01Jan2027/1DAY/C:002000|C0/'
        self.unrelated = ['//Lookout Point-Powerhouse/FLOW-OUT/01Jan2027/1DAY/C:002000|C0/',
                          self.required[0].replace('C0', 'C1'), '//DETROIT/ELEV//1DAY/RULE CURVE/']
        outer = self
        class DSS:
            def __init__(self, filename):
                outer.calls.append(('open', filename))
                if str(filename) != str(outer.source):
                    raise AssertionError('DSS reopened for archived data: '+filename)
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def getPathnameList(self, pattern):
                paths = outer.required + outer.unrelated + [outer.optional]
                return paths + ([outer.required[0].replace('01Jan2027','01Jan2026')] if outer.extra_date_block else [])
            def read_ts(self, path, **kwargs):
                outer.calls.append(('read', path))
                if path in outer.unrelated: raise AssertionError('Unnecessary series read')
                if outer.mutate: outer.source.write_bytes(b'changed during compute')
                if (outer.bad and path == outer.required[0]) or (outer.empty_optional and path == outer.optional):
                    return SimpleNamespace(pytimes=None, values=None)
                parameter = path.split('/')[3]
                return SimpleNamespace(pytimes=pd.date_range('2027-04-01',periods=3),
                    values=[outer.value]*3, units='FT' if parameter=='ELEV' else 'AC-FT' if parameter=='STOR' else 'CFS', type='PER-AVER')
        self.fake = SimpleNamespace(HecDss=SimpleNamespace(Open=DSS))
        self.module_patch = patch.dict(sys.modules, {'pydsstools.heclib.dss': self.fake})
        self.module_patch.start(); self.addCleanup(self.module_patch.stop)

    def test_subset_archives_then_all_consumers_work_without_dss(self):
        digest = capture_run(self.source, self.target, 'C0')
        self.assertFalse((self.target/'forecast.dss').exists())
        self.assertEqual({p for action,p in self.calls if action=='read'}, set(self.required+[self.optional]))
        self.assertEqual(self.source.read_bytes(), b'live data must never be copied wholesale')
        with patch.object(self.fake.HecDss, 'Open', side_effect=AssertionError('DSS reopened')):
            with open_cached_run(self.target/'forecast.dss', 'C0', digest) as reader:
                np.testing.assert_array_equal(reader.read_ts(self.required[1]).values, [100]*3)
            fp = versions.semantic_fingerprint(self.target/'forecast.dss', 'C0')
            self.assertEqual(len(fp['records']), 2)
            self.assertEqual(inspect_run(self.target/'forecast.dss', 'C0')['members'], [2000])
            self.assertEqual(archive_digest(self.target/'forecast.dss'), digest)

    def test_saved_plots_use_compact_archive_after_live_dss_is_removed(self):
        from plot_rts_runs import plot_saved_runs
        self.target.rmdir()
        identity, _ = versions.save_baseline(self.root, {'forecast_name':'test'}, 'C0')
        descriptor = {'id':identity, 'kind':'baseline', 'baseline_id':identity,
                      'directory':str(self.target), 'label':'Unaugmented'}
        self.source.unlink()
        with patch.object(self.fake.HecDss, 'Open', side_effect=AssertionError('DSS reopened')):
            plots = plot_saved_runs(self.root, [descriptor])
        self.assertTrue((plots/'index.html').exists())
        self.assertTrue(list(plots.glob('plot-*-run-1.csv')))

    def test_corrupt_primary_arrays_fail_without_rebuild(self):
        capture_run(self.source,self.target,'C0')
        (self.target/'series.npz').write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            open_cached_run(self.target/'forecast.dss','C0')

    def test_date_blocks_are_merged_and_optional_empty_record_is_explicit(self):
        self.extra_date_block = self.empty_optional = True
        capture_run(self.source,self.target,'C0')
        with open_cached_run(self.target/'forecast.dss','C0') as reader:
            self.assertEqual(len(reader.read_ts(self.required[0]).values),3)
            with self.assertRaisesRegex(ValueError, 'could not be cached'):
                reader.read_ts(self.optional)

    def test_changed_live_or_failed_required_record_never_gets_manifest(self):
        self.mutate=True
        with self.assertRaisesRegex(ValueError,'changed during capture'):
            capture_run(self.source,self.target,'C0')
        self.assertFalse((self.target/'run-archive.json').exists())
        self.mutate=False;self.bad=True
        with self.assertRaisesRegex(ValueError,'required series'):
            capture_run(self.source,self.target,'C0')
        self.assertFalse((self.target/'run-archive.json').exists())

    def test_compact_baseline_keeps_live_inputs_and_semantic_identity(self):
        self.target.rmdir()
        context={'forecast_name':'test'}
        first, changed = versions.save_baseline(self.root,context,'C0')
        self.assertTrue(changed)
        version=versions.registry(self.root)['versions'][first]
        self.assertEqual(archive_digest(self.target/'forecast.dss'),version['sha256'])
        self.source.write_bytes(b'live inputs and augmented results')
        (self.root/'rts-augmentation-active.json').write_text('{}')
        versions.load_baseline(self.root,context,'C0')
        self.assertEqual(self.source.read_bytes(),b'live inputs and augmented results')
        self.assertFalse((self.root/'rts-augmentation-active.json').exists())
        self.assertEqual(versions.save_baseline(self.root,context,'C0'),(first,False))
        self.value=200
        second,changed=versions.save_baseline(self.root,context,'C0')
        self.assertTrue(changed);self.assertNotEqual(first,second)
        self.assertTrue(self.target.is_dir())
        self.assertFalse(list((self.root/'augmentation-archives').glob('*pending*')))

    def test_candidate_promotion_retains_rollback_without_copying_live(self):
        candidate, backup = self.root/'candidate.dss', self.root/'backup.dss'
        original = self.source.read_bytes()
        candidate.write_bytes(b'new inputs')
        real_replace = versions.os.replace
        def fail_candidate(source, destination):
            if Path(source) == candidate:
                raise PermissionError('locked destination')
            return real_replace(source,destination)
        with patch.object(versions.os,'replace', side_effect=fail_candidate):
            with self.assertRaises(PermissionError):
                versions.promote_live_candidate(self.source,candidate,backup,versions.digest_file(self.source))
        self.assertEqual(self.source.read_bytes(),original)
        self.assertTrue(candidate.exists())
        versions.promote_live_candidate(self.source,candidate,backup,versions.digest_file(self.source))
        self.assertEqual(self.source.read_bytes(),b'new inputs')
        self.assertEqual(backup.read_bytes(),original)

    def test_repeated_result_capture_reuses_content_not_entire_dss(self):
        from plot_rts_augmentation import capture
        manifest={'scheme':'trial','augmentation_sha256':'prepared','baseline_sha256':'baseline',
                  'baseline_id':'baseline-0001','run_code':'C0'}
        scheme=self.root/'augmentation-archives/trial';scheme.mkdir()
        (self.root/'rts-augmentation-active.json').write_text(json.dumps(manifest))
        with patch('plot_rts_augmentation.baseline_identity',return_value='baseline-0001'), patch('plot_rts_augmentation.write_archive_index'):
            first=capture(self.root,scheme,manifest)
            self.source.write_bytes(b'Unrelated DSS records changed; selected arrays unchanged')
            self.assertEqual(capture(self.root,scheme,manifest),first)
            self.value=101
            second=capture(self.root,scheme,manifest)
            self.assertNotEqual(first,second)
            self.assertEqual(len(list(scheme.glob('results-*'))),2)

if __name__=='__main__': unittest.main()
