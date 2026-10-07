"""Qualify all shared compute inputs with the member prefix RTS requests."""
import argparse
from pathlib import Path
import shutil
import uuid

from extraction_context import load_context
from write_ensemble_dummies import copy_records
from write_rule_curves import RESERVOIRS

SITES = ('DET', 'FOS', 'GPR', 'FRN', 'BLU', 'CGR', 'COT', 'DOR', 'FAL', 'LOP', 'HCR')


def shared_inputs():
    records = [('/ZERO/ZERO/FLOW//1DAY/DUMMY/', 'CFS', 1440, 'INST-VAL'),
               ('/ALL_ABUNDANT//STOR//1DAY/WY_TYPE/', 'UNSPEC', 1440, 'INST-VAL')]
    records += [('//{}/ELEV-FOREBAY//6HOUR/RFC-FCST/'.format(site), 'FT', 360, 'INST-VAL') for site in SITES]
    records += [('//{}/ELEV//1DAY/RULE CURVE/'.format(name), 'FT', 1440, 'INST-VAL') for name in RESERVOIRS]
    return records


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dss', help='Repair an existing DSS; creates a backup before writing')
    args = parser.parse_args()
    if args.dss:
        filename = Path(args.dss)
        backup = filename.with_name(filename.name + '.before-shared-input-repair-' + uuid.uuid4().hex + '.dss')
        shutil.copy2(filename, backup)
        print('Backup:', backup)
    else:
        context = load_context()
        if context is None:
            raise ValueError('Supply --dss or explicit extraction context')
        filename = context.dss_path
    copy_records(filename, shared_inputs())
