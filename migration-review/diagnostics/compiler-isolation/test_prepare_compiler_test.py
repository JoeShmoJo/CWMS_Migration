import importlib.util
import pathlib
import subprocess
import sys
import tempfile
import unittest
import zipfile

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[2]
spec = importlib.util.spec_from_file_location('patcher', HERE/'prepare_compiler_test.py')
patcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patcher)
APP = REPO/'Jars/standalone-4.1.0/ResSimApp-4.1.0.jar'


class PatchTests(unittest.TestCase):
    def test_patch_changes_only_compiler_class_and_adds_helper(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = pathlib.Path(tmp)/'patched.jar'
            patcher.build_patched_jar(APP, output, HERE/'isolated-compiler-helper.jar')
            with zipfile.ZipFile(APP) as before, zipfile.ZipFile(output) as after:
                self.assertEqual(set(after.namelist())-set(before.namelist()), {patcher.HELPER+'.class'})
                changed = [n for n in before.namelist() if before.read(n) != after.read(n)]
                self.assertEqual(changed, [patcher.TARGET])
                # Repatching must fail rather than alter a second allocation.
                with self.assertRaises(ValueError): patcher.patch_class(after.read(patcher.TARGET))

    def test_unknown_binary_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = pathlib.Path(tmp)/'unknown.jar'; source.write_bytes(b'unknown')
            output = pathlib.Path(tmp)/'output.jar'
            with self.assertRaises(ValueError):
                patcher.build_patched_jar(source, output, HERE/'isolated-compiler-helper.jar')
            self.assertFalse(output.exists())

    def test_copy_only_installer_and_existing_destination_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = pathlib.Path(tmp)/'original'
            (source/'jar').mkdir(parents=True)
            (source/'jar/ResSimApp-4.1.0.jar').write_bytes(APP.read_bytes())
            (source/'untouched.txt').write_text('source sentinel')
            dest = pathlib.Path(tmp)/'test-copy'
            command = [sys.executable, str(HERE/'prepare_compiler_test.py'), '--installation',str(source),'--destination',str(dest)]
            first = subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(first.returncode,0,first.stderr)
            self.assertTrue((dest/'compiler-isolation-test.json').exists())
            self.assertEqual((source/'jar/ResSimApp-4.1.0.jar').read_bytes(),APP.read_bytes())
            self.assertEqual((dest/'untouched.txt').read_text(),'source sentinel')
            patched = (dest/'jar/ResSimApp-4.1.0.jar').read_bytes()
            second = subprocess.run(command,capture_output=True,text=True)
            self.assertNotEqual(second.returncode,0)
            self.assertEqual((dest/'jar/ResSimApp-4.1.0.jar').read_bytes(),patched)


if __name__ == '__main__': unittest.main()
