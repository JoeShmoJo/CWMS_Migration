"""Install or restore the inspected RTS 3.6.0 / ResSim 4.1.2 compiler experiment.

Changes only the application JAR. Close RTS and ResSim before either action.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import uuid

from prepare_compiler_test import build_patched_jar, sha, RTS_APP_SHA256

APP_RELATIVE = Path('HEC-ResSim/4.1/jar/ResSimApp-4.1.2.jar')
BACKUPS_RELATIVE = Path('HEC-ResSim/4.1/compiler-isolation-backups')
HELPER_SHA256 = '1e6821997caa8a64b53f389ae3db0d6b715e3e4fec03573e6d09c43409605b8d'


def ensure_closed():
    """Read process metadata only; never stop an application automatically."""
    if os.name != 'nt':
        return
    command = r'''$ErrorActionPreference = 'Stop'; @(Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^(javaw?|HEC-RTS|HEC-ResSim|CWMS)\.exe$' -and ($_.Name -notmatch '^javaw?\.exe$' -or $_.CommandLine -match '(?i)ressim|hec\.rss|hec2?\.rts|cwms|HEC-RTS') } | Select-Object ProcessId,Name) | ConvertTo-Json -Compress'''
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
                            capture_output=True, text=True, check=True, timeout=30)
    active = json.loads(result.stdout.strip() or '[]')
    if active:
        raise RuntimeError('Close RTS/CWMS and ResSim first. Matching processes: '+json.dumps(active))


def write_receipt(path, receipt):
    temporary = path.with_suffix('.json.pending')
    temporary.write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
    temporary.replace(path)


def install(installation):
    installation = installation.resolve()
    target = installation/APP_RELATIVE
    if sha(target.read_bytes()) != RTS_APP_SHA256:
        raise ValueError('RTS application JAR is not the inspected original 4.1.2. Nothing changed.')
    helper = Path(__file__).with_name('isolated-compiler-helper.jar')
    if sha(helper.read_bytes()) != HELPER_SHA256:
        raise ValueError('Compiler helper checksum mismatch. Nothing changed.')
    ensure_closed()
    # Build and verify the complete replacement before touching the live JAR.
    with tempfile.TemporaryDirectory(prefix='rts-compiler-') as temp:
        candidate = Path(temp)/target.name
        original_hash, patched_hash = build_patched_jar(target, candidate, helper, RTS_APP_SHA256)
        backup = installation/BACKUPS_RELATIVE/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8])
        backup.mkdir(parents=True, exist_ok=False)
        original = backup/target.name
        shutil.copy2(target, original)
        if sha(original.read_bytes()) != original_hash:
            raise RuntimeError('Backup checksum mismatch; application JAR was not replaced')
        receipt = {'experimental': True, 'compiler_isolation_version': 2,
                   'installation': str(installation), 'application': str(APP_RELATIVE),
                   'original_sha256': original_hash, 'patched_sha256': patched_hash,
                   'helper_sha256': HELPER_SHA256, 'status': 'backed-up-not-installed',
                   'created_utc': datetime.now(timezone.utc).isoformat(),
                   'model_files_changed': False, 'launcher_settings_changed': False}
        receipt_path = backup/'receipt.json'
        write_receipt(receipt_path, receipt)
        # Stage on the target volume so replacement is atomic. A failed replace
        # leaves the original target intact and its verified backup available.
        descriptor, filename = tempfile.mkstemp(prefix='compiler-', suffix='.pending', dir=target.parent)
        os.close(descriptor)
        pending = Path(filename)
        try:
            shutil.copy2(candidate, pending)
            if sha(pending.read_bytes()) != patched_hash:
                raise RuntimeError('Staged replacement checksum mismatch')
            ensure_closed()
            if sha(target.read_bytes()) != original_hash:
                raise RuntimeError('Application changed during preparation; refusing replacement')
            pending.replace(target)
        finally:
            pending.unlink(missing_ok=True)
        if sha(target.read_bytes()) != patched_hash:
            raise RuntimeError('Installed checksum mismatch; restore from '+str(backup))
        receipt['status'] = 'installed'
        write_receipt(receipt_path, receipt)
    print('INSTALLED: experimental compiler isolation V2 for RTS ResSim 4.1.2')
    print('Application:', target)
    print('BACKUP:', backup)
    print('Only the application JAR changed; no JRE, launcher, script, or model settings changed.')
    print('Restart RTS and verify the V2 active marker identifies this application JAR.')
    return backup


def restore(installation, backup):
    installation, backup = installation.resolve(), backup.resolve()
    if backup.parent != installation/BACKUPS_RELATIVE:
        raise ValueError('Backup must be directly inside this installation compiler-isolation-backups folder')
    target = installation/APP_RELATIVE
    receipt_path = backup/'receipt.json'
    receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    if (receipt.get('installation') != str(installation) or
            receipt.get('application') != str(APP_RELATIVE) or
            receipt.get('original_sha256') != RTS_APP_SHA256):
        raise ValueError('Backup receipt does not describe this inspected RTS installation')
    original = backup/target.name
    if sha(original.read_bytes()) != RTS_APP_SHA256:
        raise ValueError('Archived original checksum mismatch; refusing restore')
    ensure_closed()
    current = sha(target.read_bytes())
    if current == RTS_APP_SHA256:
        print('Already restored: original 4.1.2 JAR is present.')
        return
    if current != receipt['patched_sha256']:
        raise ValueError('Application differs from both archived versions; refusing to overwrite it')
    descriptor, filename = tempfile.mkstemp(prefix='restore-', suffix='.pending', dir=target.parent)
    os.close(descriptor)
    pending = Path(filename)
    try:
        shutil.copy2(original, pending)
        if sha(pending.read_bytes()) != RTS_APP_SHA256:
            raise RuntimeError('Staged original checksum mismatch')
        ensure_closed()
        if sha(target.read_bytes()) != current:
            raise RuntimeError('Application changed during restore; refusing replacement')
        pending.replace(target)
    finally:
        pending.unlink(missing_ok=True)
    if sha(target.read_bytes()) != RTS_APP_SHA256:
        raise RuntimeError('Restored checksum mismatch')
    receipt['status'] = 'restored'
    receipt['restored_utc'] = datetime.now(timezone.utc).isoformat()
    write_receipt(receipt_path, receipt)
    print('RESTORED: original RTS ResSim 4.1.2 application JAR. Backup retained:', backup)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installation', type=Path, required=True, help='HEC-RTS-3.6.0 package directory')
    parser.add_argument('--restore', type=Path, metavar='BACKUP_DIRECTORY', help='Restore instead of install')
    args = parser.parse_args()
    if args.restore:
        restore(args.installation, args.restore)
    else:
        install(args.installation)
