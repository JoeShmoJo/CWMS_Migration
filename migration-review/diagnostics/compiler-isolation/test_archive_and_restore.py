import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import archive_and_restore as rollback
import install_rts_compiler as rts
from prepare_compiler_test import EXPECTED_APP_SHA256, RTS_APP_SHA256

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]


class ArchiveRestoreTests(unittest.TestCase):
    def standalone(self, root):
        target=root/'standalone/jar/ResSimApp-4.1.0.jar';target.parent.mkdir(parents=True)
        target.write_bytes(b'previously modified standalone fixture')
        original=target.with_suffix('.jar.original')
        original.write_bytes((REPO/'Jars/standalone-4.1.0/ResSimApp-4.1.0.jar').read_bytes())
        (target.parent.parent/'compiler-isolation-test.json').write_text(json.dumps({
            'original_sha256':EXPECTED_APP_SHA256,'patched_sha256':rollback.digest(target)}))
        return target

    def rts(self, root):
        installation=root/'rts'
        target=installation/rts.APP_RELATIVE;target.parent.mkdir(parents=True)
        target.write_bytes(b'previously modified RTS fixture')
        backup=installation/rts.BACKUPS_RELATIVE/'20261015-test';backup.mkdir(parents=True)
        (backup/target.name).write_bytes((REPO/'Jars/ResSimApp-4.1.2.jar').read_bytes())
        (backup/'receipt.json').write_text(json.dumps({'installation':str(installation),
            'application':str(rts.APP_RELATIVE), 'original_sha256':RTS_APP_SHA256,
            'patched_sha256':rollback.digest(target)}))
        return installation,target

    def test_both_versions_archived_before_restore_and_repeat_is_safe(self):
        with tempfile.TemporaryDirectory() as temp,contextlib.redirect_stdout(io.StringIO()):
            root=Path(temp);target=self.standalone(root);installation,rts_target=self.rts(root)
            before={str(target):target.read_bytes(),str(rts_target):rts_target.read_bytes()}
            plans=[rollback.standalone_plan(target.parent.parent),rollback.rts_plan(installation)]
            archive=rollback.execute(plans,root/'private-archives')
            with zipfile.ZipFile(archive) as saved:
                for plan in plans:
                    self.assertEqual(saved.read(plan['zip_entry']),before[plan['target']])
                self.assertIn('ARCHIVE_MANIFEST.json',saved.namelist())
            self.assertEqual(rollback.digest(target),EXPECTED_APP_SHA256)
            self.assertEqual(rollback.digest(rts_target),RTS_APP_SHA256)
            self.assertIsNone(rollback.standalone_plan(target.parent.parent))
            self.assertIsNone(rollback.rts_plan(installation))
            self.assertEqual(json.loads(archive.with_suffix('.restoration.json').read_text())['status'],'complete')

    def test_corrupt_original_and_unknown_modified_jar_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            target=self.standalone(Path(temp))
            target.with_suffix('.jar.original').write_bytes(b'bad original')
            with self.assertRaisesRegex(ValueError,'backup checksum'):
                rollback.standalone_plan(target.parent.parent)
            target.write_bytes(b'unknown later modification')
            with self.assertRaisesRegex(ValueError,'Unrecognized'):
                rollback.standalone_plan(target.parent.parent)
            self.assertEqual(target.read_bytes(),b'unknown later modification')

    def test_failed_zip_verification_never_restores(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);target=self.standalone(root);before=target.read_bytes()
            plan=rollback.standalone_plan(target.parent.parent)
            with patch.object(zipfile.ZipFile,'testzip',return_value='bad-entry'):
                with self.assertRaisesRegex(ValueError,'ZIP integrity'):
                    rollback.execute([plan],root/'archive')
            self.assertEqual(target.read_bytes(),before)
            self.assertFalse(list((root/'archive').glob('*.pending')))

    def test_restore_failure_keeps_verified_zip_and_current_jar(self):
        with tempfile.TemporaryDirectory() as temp,contextlib.redirect_stdout(io.StringIO()):
            root=Path(temp);target=self.standalone(root);before=target.read_bytes()
            plan=rollback.standalone_plan(target.parent.parent)
            replace=Path.replace
            def fail(path,destination):
                if Path(destination)==target: raise PermissionError('locked')
                return replace(path,destination)
            with patch.object(Path,'replace',fail):
                with self.assertRaises(PermissionError): rollback.execute([plan],root/'archive')
            self.assertEqual(target.read_bytes(),before)
            archives=list((root/'archive').glob('*.zip'));self.assertEqual(len(archives),1)
            with zipfile.ZipFile(archives[0]) as saved:
                self.assertEqual(saved.read(plan['zip_entry']),before)
            self.assertEqual(json.loads(archives[0].with_suffix('.restoration.json').read_text())['status'],'incomplete')

    def test_running_application_refuses_before_archiving(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);target=self.standalone(root)
            plan=rollback.standalone_plan(target.parent.parent)
            with patch.object(rollback,'ensure_closed',side_effect=RuntimeError('running')):
                with self.assertRaises(RuntimeError):rollback.execute([plan],root/'archive')
            self.assertFalse((root/'archive').exists())


if __name__=='__main__':unittest.main()
