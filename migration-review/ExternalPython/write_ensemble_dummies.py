"""Copy shared dummy inputs into the collection paths requested by RTS."""
import argparse
from pathlib import Path
import re


def member_prefixes(paths):
    prefixes = set()
    for path in paths:
        parts = path.split('/')
        if len(parts) == 8 and parts[3].upper() in ('FLOW-LOC', 'FLOW-UNREG'):
            if re.fullmatch(r'C:\d{6}\|', parts[6]):
                prefixes.add(parts[6])
    return sorted(prefixes)


def copy_records(filename, specifications):
    import numpy as np
    import pandas as pd
    from pydsstools.heclib.dss import HecDss
    from pydsstools.core import TimeSeriesContainer
    if not Path(filename).is_file():
        raise FileNotFoundError(filename)
    with HecDss.Open(str(filename)) as dss:
        members = member_prefixes(dss.getPathnameList('/*/*/*/*/*/*/'))
        if not members:
            raise ValueError('No downloaded ensemble FLOW-LOC/FLOW-UNREG members found')
        # Validate both source records before writing any copies.
        sources = []
        for path, units, interval, data_type in specifications:
            series = dss.read_ts(path, trim_missing=True)
            dates = pd.DatetimeIndex(pd.to_datetime(series.pytimes))
            values = np.asarray(series.values, dtype=float)
            if len(dates) != len(values) or not len(values) or not np.isfinite(values).all():
                raise ValueError('Invalid source dummy record: ' + path)
            if not (dates.to_series().diff().iloc[1:] == pd.Timedelta(minutes=interval)).all():
                raise ValueError('Source input has irregular timestamps: ' + path)
            if path.startswith('/ZERO/') and not (values == 0).all():
                raise ValueError('ZERO source contains nonzero values')
            sources.append((path, units, interval, data_type, dates, values))
        written = 0
        for path, units, interval, data_type, dates, values in sources:
            for prefix in members:
                parts = path.split('/')
                parts[6] = prefix + parts[6]
                record = TimeSeriesContainer()
                record.pathname = '/'.join(parts)
                record.startDateTime = dates[0].strftime('%d%b%Y %H%M')
                record.numberValues = len(values)
                record.interval = interval
                record.units = units
                record.type = data_type
                record.values = values
                dss.put_ts(record)
                written += 1
        print('Ensemble members:', ', '.join(members))
        print('Member-specific shared input records written:', written)


def copy_dummies(filename):
    copy_records(filename, [('/ZERO/ZERO/FLOW//1DAY/DUMMY/', 'CFS', 1440, 'INST-VAL'),
                            ('/ALL_ABUNDANT//STOR//1DAY/WY_TYPE/', 'UNSPEC', 1440, 'INST-VAL')])


if __name__ == '__main__':
    import shutil
    import uuid
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dss', required=True)
    filename = Path(parser.parse_args().dss)
    backup = filename.with_name(filename.name + '.before-dummy-repair-' + uuid.uuid4().hex + '.dss')
    shutil.copy2(filename, backup)
    print('Backup:', backup)
    copy_dummies(filename)
