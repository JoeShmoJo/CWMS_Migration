"""Read two CWMS series and print timestamp diagnostics; never open or write DSS."""
from datetime import datetime, timedelta, timezone
import argparse
import pandas as pd
from windows_ca import configure_ca_bundle


def summarize(label, frame):
    print('\n=== {} ==='.format(label), flush=True)
    if frame is None or frame.empty:
        print('No rows returned', flush=True)
        return
    print('Rows:', len(frame), 'Columns:', list(frame.columns), flush=True)
    times = pd.to_datetime(frame['date-time'], errors='coerce', utc=True)
    values = pd.to_numeric(frame['value'], errors='coerce')
    print('Unparseable timestamps:', int(times.isna().sum()), flush=True)
    print('Missing/nonnumeric values:', int(values.isna().sum()), flush=True)
    times = times.dropna().sort_values()
    print('Duplicate timestamps:', int(times.duplicated().sum()), flush=True)
    print('First UTC timestamps:', [str(t) for t in times.head(5)], flush=True)
    print('Last UTC timestamps:', [str(t) for t in times.tail(5)], flush=True)
    print('Raw interval counts:', {str(k): int(v) for k, v in times.diff().dropna().value_counts().items()}, flush=True)
    if 'RFC-FCST' not in label:
        civil = pd.DatetimeIndex(times).tz_convert('America/Los_Angeles').tz_localize(None)
        print('Pacific civil interval counts:', {str(k): int(v) for k, v in civil.to_series().diff().dropna().value_counts().items()}, flush=True)
    clean = pd.DataFrame({'time': pd.to_datetime(frame['date-time'], errors='coerce', utc=True), 'value': values})
    clean = clean.dropna().sort_values('time')
    diffs = clean['time'].diff()
    print('Intervals after dropping missing values:', {str(k): int(v) for k, v in diffs.dropna().value_counts().items()}, flush=True)
    expected = pd.Timedelta(hours=6 if 'RFC-FCST' in label else 24)
    positions = [i for i in range(1, len(clean)) if diffs.iloc[i] != expected]
    for i in positions[:10]:
        print('Unexpected gap: {} -> {} ({})'.format(clean['time'].iloc[i-1], clean['time'].iloc[i], diffs.iloc[i]), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tsid', help='Inspect one daily CWMS series, from January 1 through now')
    args = parser.parse_args()
    configure_ca_bundle()
    import cwms
    cwms.api.init_session(api_root='https://wm.nws.ds.usace.army.mil:8243/nwdp-data/')
    now = datetime.now(timezone.utc)
    cases = [
        ('DET.Elev-Forebay.Ave.~1Day.1Day.CBT-REV', now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0), now),
        ('DET.Elev-Forebay.Inst.~6Hours.0.RFC-FCST', now, now + timedelta(days=3))
    ]
    if args.tsid:
        cases = [(args.tsid, now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0), now)]
    for name, begin, end in cases:
        result = cwms.get_timeseries(name, office_id='NWDP', begin=begin, end=end)
        summarize(name, getattr(result, 'df', None))
    print('\nDiagnosis complete. No DSS files were opened or changed.', flush=True)


if __name__ == '__main__':
    main()
