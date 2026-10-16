"""Keep civil daily schedules distinct from fixed-offset forecast timestamps."""
import pandas as pd


def dss_index(utc_times, forecast_timezone, calendar_daily=False,
              daily_timezone='America/Los_Angeles'):
    index = pd.DatetimeIndex(utc_times)
    if calendar_daily:
        # CWMS daily Pacific records have 23/25-hour UTC intervals at DST changes.
        # Preserve the source civil clock label; do not interpolate or drop rows.
        return index.tz_convert(daily_timezone).tz_localize(None)
    return index.tz_convert(forecast_timezone).tz_localize(None)


def preserve_gaps(series, interval_minutes):
    """Insert NaN slots for absent observations without interpolating values."""
    series = series.sort_index()
    if series.empty or series.index.has_duplicates:
        raise ValueError('Cannot regularize empty or duplicate observations')
    grid = pd.date_range(series.index[0], series.index[-1],
                         freq=pd.Timedelta(minutes=interval_minutes))
    if not series.index.isin(grid).all():
        raise ValueError('Observation timestamps do not align to the regular grid')
    return series.reindex(grid)
