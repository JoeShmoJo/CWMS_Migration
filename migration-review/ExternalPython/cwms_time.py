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
