import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import install_rts_compiler as installer
import prepare_compiler_test as builder

HERE = Path(__file__).resolve().parent
APP = HERE.parents[2]/'Jars/ResSimApp-4.1.2.jar'


class RtsInstallTests(unittest.TestCase):
    def make_install(self, root):
        target = root/installer.APP_RELATIVE
        target.parent.mkdir(parents=True)
        target.write_bytes(APP.read_bytes())
        (root/'keep.config').write_text('launcher unchanged')
        (root/'forecast.dss').write_bytes(b'unchanged DSS')
        return target

    def test_install_exact_entry_scope_backup_restore(self):
        with tempfile.TemporaryDirectory() as temp, contextlib.redirect_stdout(io.StringIO()):
            root = Path(temp)
            target = self.make_install(root)
            with patch.object(installer, 'ensure_closed'):
                backup = installer.install(root)
                receipt = json.loads((backup/'receipt.json').read_text())
                self.assertEqual(receipt['status'], 'installed')
                self.assertEqual((backup/target.name).read_bytes(), APP.read_bytes())
                self.assertEqual(builder.sha(target.read_bytes()), receipt['patched_sha256'])
                with zipfile.ZipFile(APP) as before, zipfile.ZipFile(target) as after:
                    self.assertEqual([n for n in before.namelist() if before.read(n) != after.read(n)], [builder.TARGET])
                    self.assertEqual(set(after.namelist())-set(before.namelist()),
                                     {builder.HELPER+'.class', builder.HELPER+'$1.class'})
                with self.assertRaises(ValueError): installer.install(root)
                installer.restore(root, backup)
                self.assertEqual(target.read_bytes(), APP.read_bytes())
                installer.restore(root, backup)  # Safe repeated restore.
            self.assertEqual((root/'keep.config').read_text(), 'launcher unchanged')
            self.assertEqual((root/'forecast.dss').read_bytes(), b'unchanged DSS')

    def test_unknown_binary_and_running_process_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = self.make_install(root)
            with patch.object(installer, 'ensure_closed', side_effect=RuntimeError('running')):
                with self.assertRaises(RuntimeError): installer.install(root)
            self.assertEqual(target.read_bytes(), APP.read_bytes())
            self.assertFalse((root/installer.BACKUPS_RELATIVE).exists())
            target.write_bytes(b'unknown application version')
            with self.assertRaises(ValueError): installer.install(root)
            self.assertEqual(target.read_bytes(), b'unknown application version')

    def test_restore_refuses_tampered_backup_and_target(self):
        with tempfile.TemporaryDirectory() as temp, contextlib.redirect_stdout(io.StringIO()):
            root = Path(temp)
            target = self.make_install(root)
            with patch.object(installer, 'ensure_closed'):
                backup = installer.install(root)
                patched_bytes = target.read_bytes()
                original = backup/target.name
                original.write_bytes(b'bad backup')
                with self.assertRaises(ValueError): installer.restore(root, backup)
                self.assertEqual(target.read_bytes(), patched_bytes)
                original.write_bytes(APP.read_bytes())
                target.write_bytes(b'new vendor update')
                with self.assertRaises(ValueError): installer.restore(root, backup)
                self.assertEqual(target.read_bytes(), b'new vendor update')

    def test_failed_atomic_replace_leaves_original_and_backup(self):
        with tempfile.TemporaryDirectory() as temp, contextlib.redirect_stdout(io.StringIO()):
            root = Path(temp)
            target = self.make_install(root)
            real_replace = Path.replace
            def replace(path, destination):
                if Path(destination) == target:
                    raise PermissionError('application locked')
                return real_replace(path, destination)
            with patch.object(installer, 'ensure_closed'), patch.object(Path, 'replace', replace):
                with self.assertRaises(PermissionError): installer.install(root)
            self.assertEqual(target.read_bytes(), APP.read_bytes())
            backups = list((root/installer.BACKUPS_RELATIVE).iterdir())
            self.assertEqual(len(backups), 1)
            self.assertEqual((backups[0]/target.name).read_bytes(), APP.read_bytes())
            self.assertEqual(list(target.parent.glob('*.pending')), [])


if __name__ == '__main__': unittest.main()
