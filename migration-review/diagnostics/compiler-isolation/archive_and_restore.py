"""Archive existing compiler-patched JARs, then restore verified vendor originals.

Does not inspect bytecode, build patches, or alter model/configuration files.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import uuid
import zipfile

from install_rts_compiler import (APP_RELATIVE, BACKUPS_RELATIVE, ensure_closed,
                                 restore as restore_rts, write_receipt)
from prepare_compiler_test import EXPECTED_APP_SHA256, RTS_APP_SHA256


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def standalone_plan(installation):
    installation = installation.resolve()
    marker = installation/'compiler-isolation-test.json'
    info = json.loads(marker.read_text(encoding='utf-8'))
    target = installation/'jar/ResSimApp-4.1.0.jar'
    current = digest(target)
    if current == EXPECTED_APP_SHA256:
        print('Already original (standalone):', installation)
        return None
    if info.get('original_sha256') != EXPECTED_APP_SHA256 or current != info.get('patched_sha256'):
        raise ValueError('Unrecognized standalone JAR; nothing restored: '+str(target))
    original = target.with_suffix('.jar.original')
    if digest(original) != EXPECTED_APP_SHA256:
        raise ValueError('Standalone original backup checksum mismatch: '+str(original))
    return {'kind':'standalone', 'installation':str(installation), 'target':str(target),
            'original':str(original), 'marker':str(marker), 'patched_sha256':current,
            'original_sha256':EXPECTED_APP_SHA256}


def rts_plan(installation):
    installation = installation.resolve()
    target = installation/APP_RELATIVE
    current = digest(target)
    if current == RTS_APP_SHA256:
        print('Already original (RTS):', installation)
        return None
    for backup in sorted((installation/BACKUPS_RELATIVE).glob('*'), reverse=True):
        receipt_path = backup/'receipt.json'
        if not receipt_path.is_file():
            continue
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
        if (receipt.get('original_sha256') == RTS_APP_SHA256 and
                receipt.get('patched_sha256') == current and
                receipt.get('installation') == str(installation) and
                receipt.get('application') == str(APP_RELATIVE)):
            original = backup/target.name
            if digest(original) != RTS_APP_SHA256:
                raise ValueError('RTS original backup checksum mismatch: '+str(original))
            return {'kind':'rts', 'installation':str(installation), 'target':str(target),
                    'original':str(original), 'marker':str(receipt_path),
                    'backup':str(backup), 'patched_sha256':current, 'original_sha256':RTS_APP_SHA256}
    raise ValueError('No verified RTS backup matches the current JAR: '+str(target))


def archive_all(plans, archive_root):
    archive_root = archive_root.resolve()
    for plan in plans:
        installation = Path(plan['installation'])
        if archive_root == installation or installation in archive_root.parents:
            raise ValueError('Archive destination must be outside all application installations')
    archive_root.mkdir(parents=True, exist_ok=True)
    archive = archive_root/('compiler-patches-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]+'.zip')
    pending = archive.with_suffix('.zip.pending')
    try:
        with zipfile.ZipFile(pending, 'x', compression=zipfile.ZIP_DEFLATED) as output:
            for number, plan in enumerate(plans, 1):
                target = Path(plan['target'])
                if digest(target) != plan['patched_sha256']:
                    raise ValueError('JAR changed before archival: '+str(target))
                entry = plan['kind']+'-'+str(number).zfill(3)+'/'+target.name
                plan['zip_entry'] = entry
                output.write(target, entry)
                output.write(plan['marker'], str(Path(entry).parent/'installation-receipt.json'))
            output.writestr('ARCHIVE_MANIFEST.json', json.dumps({
                'purpose':'Private preservation of previously modified JARs before restoring originals',
                'created_utc':datetime.now(timezone.utc).isoformat(), 'installations':plans,
                'scope':'Application JARs and receipts only; no watersheds or full installation copies'}, indent=2))
        with zipfile.ZipFile(pending) as check:
            if check.testzip() is not None:
                raise ValueError('ZIP integrity verification failed; originals not restored')
            for plan in plans:
                if hashlib.sha256(check.read(plan['zip_entry'])).hexdigest() != plan['patched_sha256']:
                    raise ValueError('Archived JAR checksum mismatch; originals not restored')
        pending.replace(archive)
    finally:
        pending.unlink(missing_ok=True)
    return archive


def restore_standalone(plan):
    target, original = Path(plan['target']), Path(plan['original'])
    ensure_closed()
    if digest(target) != plan['patched_sha256'] or digest(original) != plan['original_sha256']:
        raise ValueError('JAR or backup changed after archive verification; refusing restore')
    descriptor, filename = tempfile.mkstemp(prefix='restore-original-', suffix='.pending', dir=target.parent)
    os.close(descriptor)
    pending = Path(filename)
    try:
        shutil.copy2(original, pending)
        if digest(pending) != plan['original_sha256']:
            raise ValueError('Staged original checksum mismatch')
        ensure_closed()
        if digest(target) != plan['patched_sha256']:
            raise ValueError('Standalone application changed during restoration')
        pending.replace(target)
    finally:
        pending.unlink(missing_ok=True)
    if digest(target) != plan['original_sha256']:
        raise ValueError('Restored standalone checksum mismatch')
    info = json.loads(Path(plan['marker']).read_text(encoding='utf-8'))
    info.update(status='restored-original', restored_utc=datetime.now(timezone.utc).isoformat())
    write_receipt(Path(plan['marker']), info)
    print('RESTORED standalone:', target)


def execute(plans, archive_root):
    if not plans:
        print('No modified application JARs found in the inspected installations.')
        return None
    ensure_closed()
    archive = archive_all(plans, archive_root)
    print('VERIFIED ZIP:', archive, flush=True)
    status_path = archive.with_suffix('.restoration.json')
    status = {'archive':str(archive), 'archive_sha256':digest(archive), 'restored':[],
              'status':'archive-verified-restoration-starting'}
    write_receipt(status_path,status)
    try:
        for plan in plans:
            if plan['kind'] == 'rts':
                restore_rts(Path(plan['installation']),Path(plan['backup']))
            else:
                restore_standalone(plan)
            if digest(plan['target']) != plan['original_sha256']:
                raise ValueError('Post-restore verification failed')
            status['restored'].append(plan['target'])
            write_receipt(status_path,status)
        status['status']='complete'
        write_receipt(status_path,status)
    except BaseException as error:
        status.update(status='incomplete', error=str(error))
        write_receipt(status_path,status)
        raise
    print('COMPLETE:', len(plans), 'original application JARs restored.')
    print('Models, operating scripts, launcher settings, and existing original backups unchanged.')
    print('Private modified-JAR archive:', archive)
    return archive


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--standalone-search-root',type=Path,required=True,
                        help='Search recursively for marked standalone test installations')
    parser.add_argument('--rts-installation',type=Path,required=True)
    parser.add_argument('--archive-root',type=Path,required=True)
    args=parser.parse_args()
    if not args.standalone_search_root.is_dir():
        raise ValueError('Standalone search directory does not exist')
    markers=sorted(args.standalone_search_root.rglob('compiler-isolation-test.json'))
    if not markers:
        raise ValueError('No marked standalone installations found; confirm search root before restoring either application')
    plans=[]
    for marker in markers:
        plan=standalone_plan(marker.parent)
        if plan: plans.append(plan)
    plan=rts_plan(args.rts_installation)
    if plan: plans.append(plan)
    for plan in plans:
        print('Will archive and restore:',plan['target'],flush=True)
    execute(plans,args.archive_root)


if __name__=='__main__': main()
