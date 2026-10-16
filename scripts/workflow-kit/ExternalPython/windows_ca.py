"""Add Windows ROOT certificates trusted for TLS; never disable verification."""
import atexit
import os
from pathlib import Path
import ssl
import tempfile

SERVER_AUTH = '1.3.6.1.5.5.7.3.1'


def configure_ca_bundle():
    # Respect the user's explicit trust configuration.
    existing = os.environ.get('REQUESTS_CA_BUNDLE') or os.environ.get('CURL_CA_BUNDLE')
    if existing:
        if not Path(existing).is_file():
            raise FileNotFoundError('Configured CA bundle does not exist: ' + existing)
        print('Using configured CA bundle:', existing, flush=True)
        return existing
    if not hasattr(ssl, 'enum_certificates'):
        print('Windows certificate store unavailable; using default verified TLS trust.', flush=True)
        return None

    import certifi
    certificates = ssl.enum_certificates('ROOT')
    descriptor, filename = tempfile.mkstemp(prefix='ressim-windows-ca-', suffix='.pem')
    count = 0
    try:
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write(Path(certifi.where()).read_bytes())
            handle.write(b'\n')
            for certificate, encoding, trust in certificates:
                if encoding != 'x509_asn':
                    continue
                if trust is not True and SERVER_AUTH not in trust:
                    continue
                handle.write(ssl.DER_cert_to_PEM_cert(certificate).encode('ascii'))
                count += 1
        # Validate the resulting PEM before using it for any request.
        ssl.create_default_context(cafile=filename)
    except BaseException:
        os.unlink(filename)
        raise
    os.environ['REQUESTS_CA_BUNDLE'] = filename
    def cleanup():
        try:
            os.unlink(filename)
        except FileNotFoundError:
            pass
    atexit.register(cleanup)
    print('Using certifi plus {} Windows TLS-trusted ROOT certificates: {}'.format(count, filename), flush=True)
    return filename
