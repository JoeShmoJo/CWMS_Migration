"""Optional explicit context; existing standalone launchers need no changes."""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path


def parse_hec(date, clock):
    months = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
    date = date.strip()
    clock = clock.strip().replace(':', '')
    value = datetime(int(date[-4:]), months.index(date[-7:-4].lower()) + 1, int(date[:-7]))
    hour, minute = int(clock[:-2]), int(clock[-2:])
    if hour == 24 and minute != 0:
        raise ValueError('Only 2400 is a valid end-of-day time')
    if hour > 24 or minute > 59:
        raise ValueError('Invalid HEC clock time')
    return value + timedelta(hours=hour, minutes=minute)


class Context:
    def __init__(self, data):
        self.data = data
        zone = data['timezone']
        if not zone.startswith('GMT') or len(zone) != 9 or zone[3] not in '+-' or zone[6] != ':':
            raise ValueError('Use an explicit fixed timezone such as GMT-08:00')
        offset = (int(zone[4:6]) * 60 + int(zone[7:9])) * (1 if zone[3] == '+' else -1)
        self.timezone = timezone(timedelta(minutes=offset))
        self.lookback = parse_hec(*data['lookback'])
        self.start = parse_hec(*data['start'])
        self.end = parse_hec(*data['end'])
        if not self.lookback < self.start < self.end:
            raise ValueError('Require lookback < forecast time < end')
        self.dss_path = Path(data['dss_path']).resolve()

    def utc(self, value):
        return value.replace(tzinfo=self.timezone).astimezone(timezone.utc)

    def validate_series(self, series, interval_minutes, begin=None, end=None, allow_missing=False):
        """Reject gaps before packing regular DSS values (which would shift times)."""
        import numpy as np
        import pandas as pd
        begin = pd.Timestamp(self.lookback if begin is None else begin)
        end = pd.Timestamp(self.end if end is None else end)
        series = series.sort_index()
        values = series.to_numpy(dtype=float)
        invalid = np.isinf(values).any() or (not allow_missing and np.isnan(values).any())
        if series.empty or series.index.has_duplicates or invalid:
            raise ValueError('Empty, duplicate, or nonfinite time-series values')
        delta = pd.Timedelta(minutes=interval_minutes)
        if not (series.index.to_series().diff().iloc[1:] == delta).all():
            raise ValueError('Missing or irregular intervals; cannot pack into regular DSS')
        if series.index[0] > begin or series.index[-1] < end:
            raise ValueError('Coverage {} to {} does not cover {} to {}'.format(series.index[0], series.index[-1], begin, end))


def load_context():
    filename = os.environ.get('RESSIM_EXTRACTION_CONTEXT')
    if not filename:
        return None
    with open(filename, encoding='utf-8-sig') as handle:
        return Context(json.load(handle))
