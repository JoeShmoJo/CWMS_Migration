import os
from pathlib import Path
import ssl
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'migration-review' / 'ExternalPython'))
import windows_ca


class TrustTests(unittest.TestCase):
    def test_explicit_bundle_preserved(self):
        with tempfile.NamedTemporaryFile() as file, patch.dict(os.environ, {'REQUESTS_CA_BUNDLE': file.name}, clear=True):
            self.assertEqual(windows_ca.configure_ca_bundle(), file.name)

    def test_missing_explicit_bundle_fails(self):
        with patch.dict(os.environ, {'REQUESTS_CA_BUNDLE': '/nonexistent/test-ca.pem'}, clear=True):
            with self.assertRaises(FileNotFoundError):
                windows_ca.configure_ca_bundle()

    def test_windows_roots_filtered_and_validated(self):
        import certifi
        der = ssl.create_default_context(cafile=certifi.where()).get_ca_certs(binary_form=True)[0]
        entries = [(der, 'x509_asn', True), (der, 'x509_asn', {windows_ca.SERVER_AUTH}),
                   (der, 'x509_asn', {'1.3.6.1.5.5.7.3.3'}), (der, 'pkcs_7_asn', True)]
        with patch.dict(os.environ, {}, clear=True), patch.object(ssl, 'enum_certificates', return_value=entries, create=True), patch.object(windows_ca.atexit, 'register') as register:
            path = windows_ca.configure_ca_bundle()
            try:
                base = Path(certifi.where()).read_bytes()
                combined = Path(path).read_bytes()
                self.assertTrue(combined.startswith(base))
                self.assertEqual(combined[len(base):].count(b'BEGIN CERTIFICATE'), 2)
                self.assertEqual(os.environ['REQUESTS_CA_BUNDLE'], path)
                ssl.create_default_context(cafile=path)
            finally:
                register.call_args[0][0]()
            self.assertFalse(Path(path).exists())
