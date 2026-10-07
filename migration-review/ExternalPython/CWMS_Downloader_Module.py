"""
CWMS Download -> write to DSS (forecast.dss)

- OBS_ELEV_DICT and OBS_OUTFLOW_DICT: first-of-year through now
- LOOKBACK_ELEV_DICT: now through +10 days
- RC_ELEV_DICT: first-of-year through now, shifted from daily 8am to daily end-of-day

Dicts are:
  { CWMS_TSID : DSS_PATHNAME }
"""

import os
import urllib3
import requests
import numpy as np
import pandas as pd
from datetime import timezone

import cwms
from pydsstools.heclib.dss import HecDss
from pydsstools.core import TimeSeriesContainer

import CONFIG as cfg

from pathlib import Path
from typing import Dict, Tuple, List
import importlib

# reload CONFIG to pick up changes without restarting kernel (optional, for interactive dev)
importlib.reload(cfg)

# =====================================================================
# CONFIG / PATHS
# =====================================================================

SIM_NAME = cfg.SIM_NAME

sim_dir = SIM_NAME.replace(" ", "_")



# ============================================================
# SCRIPT LOCATION
# ============================================================

SCRIPT_PATH = Path(__file__).resolve()
SCRIPT_DIR = SCRIPT_PATH.parent

# ============================================================
# BUILD RELATIVE PATH FROM SCRIPT LOCATION
# Go up one directory from script, then:
#    rss/<simulation_name>/simulation.dss
# ============================================================

DSS_PATH = (
    SCRIPT_DIR.parent.parent
    / "rss"
    / sim_dir
    / "simulation.dss"
).resolve()

from extraction_context import load_context
CONTEXT = load_context()
if CONTEXT is not None:
    DSS_PATH = CONTEXT.dss_path

DSS_FILE_OUT = str(DSS_PATH)

print("DSS_FILE_OUT:", DSS_FILE_OUT)

# =====================================================================
# YOUR DICTS (CWMS TSID -> DSS PATH)
# =====================================================================

OBS_ELEV_DICT = {
    "DET.Elev-Forebay.Ave.~1Day.1Day.CBT-REV": "//DET/Elev-Forebay//1DAY/CBT-REV/",
    "GPR.Elev-Forebay.Ave.~1Day.1Day.CBT-REV": "//GPR/Elev-Forebay//1DAY/CBT-REV/",
    "FOS.Elev-Forebay.Ave.~1Day.1Day.CBT-REV": "//FOS/Elev-Forebay//1DAY/CBT-REV/",
    "CGR.Elev-Forebay.Ave.~1Day.1Day.CBT-REV": "//CGR/Elev-Forebay//1DAY/CBT-REV/",
    "BLU.Elev-Forebay.Inst.~1Day.0.MIXED-REV": "//BLU/Elev-Forebay//1DAY/MIXED-REV/",
    "FAL.Elev-Forebay.Inst.~1Day.0.MIXED-REV": "//FAL/Elev-Forebay//1DAY/MIXED-REV/",
    "HCR.Elev-Forebay.Ave.~1Day.1Day.CBT-REV": "//HCR/Elev-Forebay//1DAY/CBT-REV/",
    "LOP.Elev-Forebay.Ave.~1Day.1Day.CBT-REV": "//LOP/Elev-Forebay//1DAY/CBT-REV/",
    "COT.Elev-Forebay.Inst.~1Day.0.MIXED-REV": "//COT/Elev-Forebay//1DAY/MIXED-REV/",
    "DOR.Elev-Forebay.Inst.~1Day.0.MIXED-REV": "//DOR/Elev-Forebay//1DAY/MIXED-REV/",
    "FRN.Elev-Forebay.Inst.~1Day.0.MIXED-REV": "//FRN/Elev-Forebay//1DAY/MIXED-REV/",
}

OBS_OUTFLOW_DICT = {
    "DET.Flow-Out.Ave.~1Day.1Day.CBT-REV": "//DET/Flow-Out//1DAY/CBT-REV/",
    "GPR.Flow-Out.Ave.~1Day.1Day.CBT-REV": "//GPR/Flow-Out//1DAY/CBT-REV/",
    "FOS.Flow-Out.Ave.~1Day.1Day.CBT-REV": "//FOS/Flow-Out//1DAY/CBT-REV/",
    "CGR.Flow-Out.Ave.~1Day.1Day.CBT-REV": "//CGR/Flow-Out//1DAY/CBT-REV/",
    "HCR.Flow-Out.Ave.~1Day.1Day.CBT-REV": "//HCR/Flow-Out//1DAY/CBT-REV/",
    "LOP.Flow-Out.Ave.~1Day.1Day.CBT-REV": "//LOP/Flow-Out//1DAY/CBT-REV/",
    "BLU.Flow-Out.Ave.~1Day.1Day.MIXED-COMPUTED-REV": "//BLU/Flow-Out//1DAY/MIXED-COMPUTED-REV/",
    "FAL.Flow-Out.Ave.~1Day.1Day.MIXED-COMPUTED-REV": "//FAL/Flow-Out//1DAY/MIXED-COMPUTED-REV/",
    "COT.Flow-Out.Ave.~1Day.1Day.MIXED-COMPUTED-REV": "//COT/Flow-Out//1DAY/MIXED-COMPUTED-REV/",
    "DOR.Flow-Out.Ave.~1Day.1Day.MIXED-COMPUTED-REV": "//DOR/Flow-Out//1DAY/MIXED-COMPUTED-REV/",
    "FRN.Flow-Out.Ave.~1Day.1Day.MIXED-COMPUTED-REV": "//FRN/Flow-Out//1DAY/MIXED-COMPUTED-REV/",
}

LOOKBACK_ELEV_DICT = {
    "DET.Elev-Forebay.Inst.~6Hours.0.RFC-FCST": "//DET/Elev-Forebay//6HOUR/RFC-FCST/",
    "GPR.Elev-Forebay.Inst.~6Hours.0.RFC-FCST": "//GPR/Elev-Forebay//6HOUR/RFC-FCST/",
    "FOS.Elev-Forebay.Inst.~6Hours.0.RFC-FCST": "//FOS/Elev-Forebay//6HOUR/RFC-FCST/",
    "CGR.Elev-Forebay.Inst.~6Hours.0.RFC-FCST": "//CGR/Elev-Forebay//6HOUR/RFC-FCST/",
    "BLU.Elev-Forebay.Inst.~6Hours.0.RFC-FCST": "//BLU/Elev-Forebay//6HOUR/RFC-FCST/",
    "FAL.Elev-Forebay.Inst.~6Hours.0.RFC-FCST": "//FAL/Elev-Forebay//6HOUR/RFC-FCST/",
    "HCR.Elev-Forebay.Inst.~6Hours.0.RFC-FCST": "//HCR/Elev-Forebay//6HOUR/RFC-FCST/",
    "LOP.Elev-Forebay.Inst.~6Hours.0.RFC-FCST": "//LOP/Elev-Forebay//6HOUR/RFC-FCST/",
    "FRN.Elev-Forebay.Inst.~6Hours.0.RFC-FCST": "//FRN/Elev-Forebay//6HOUR/RFC-FCST/",
    "DOR.Elev-Forebay.Inst.~6Hours.0.RFC-FCST": "//DOR/Elev-Forebay//6HOUR/RFC-FCST/",
    "COT.Elev-Forebay.Inst.~6Hours.0.RFC-FCST": "//COT/Elev-Forebay//6HOUR/RFC-FCST/",
}

RC_ELEV_DICT = {
    "DET.Elev-RuleCurve.Inst.~1Day.0.CENWP-CALC": "//DET/Elev-RuleCurve//1DAY/CENWP-CALC/",
    "GPR.Elev-RuleCurve.Inst.~1Day.0.CENWP-CALC": "//GPR/Elev-RuleCurve//1DAY/CENWP-CALC/",
    "FOS.Elev-RuleCurve.Inst.~1Day.0.CENWP-CALC": "//FOS/Elev-RuleCurve//1DAY/CENWP-CALC/",
    "CGR.Elev-RuleCurve.Inst.~1Day.0.CENWP-CALC": "//CGR/Elev-RuleCurve//1DAY/CENWP-CALC/",
    "BLU.Elev-RuleCurve.Inst.~1Day.0.CENWP-CALC": "//BLU/Elev-RuleCurve//1DAY/CENWP-CALC/",
    "FAL.Elev-RuleCurve.Inst.~1Day.0.CENWP-CALC": "//FAL/Elev-RuleCurve//1DAY/CENWP-CALC/",
    "HCR.Elev-RuleCurve.Inst.~1Day.0.CENWP-CALC": "//HCR/Elev-RuleCurve//1DAY/CENWP-CALC/",
    "LOP.Elev-RuleCurve.Inst.~1Day.0.CENWP-CALC": "//LOP/Elev-RuleCurve//1DAY/CENWP-CALC/",
    "DOR.Elev-RuleCurve.Inst.~1Day.0.CENWP-CALC": "//DOR/Elev-RuleCurve//1DAY/CENWP-CALC/",
    "FRN.Elev-RuleCurve.Inst.~1Day.0.CENWP-CALC": "//FRN/Elev-RuleCurve//1DAY/CENWP-CALC/",
    "COT.Elev-RuleCurve.Inst.~1Day.0.CENWP-CALC": "//COT/Elev-RuleCurve//1DAY/CENWP-CALC/",
}

# =====================================================================
# TLS verification is required; use an approved REQUESTS_CA_BUNDLE if needed.

# =====================================================================
# HELPERS
# =====================================================================

def _to_py_datetime_utc(x) -> object:
    """Return python datetime in UTC (tz-aware) for CWMS calls."""
    ts = pd.to_datetime(x, utc=True)
    return ts.to_pydatetime()

def _df_to_series(df: pd.DataFrame, calendar_daily=False) -> pd.Series:
    """
    CWMS df shape you showed:
      columns: ['date-time','value','quality-code'], RangeIndex
    Convert to Series with tz-naive DatetimeIndex for DSS.
    """
    if df is None or df.empty:
        return pd.Series(dtype="float64")

    if "date-time" not in df.columns:
        raise ValueError(f"Expected 'date-time' column, got columns={list(df.columns)}")

    d = df.copy()
    d["date-time"] = pd.to_datetime(d["date-time"], errors="coerce", utc=True)
    d = d.dropna(subset=["date-time"]).set_index("date-time").sort_index()

    # DSS wants tz-naive
    if CONTEXT:
        from cwms_time import dss_index
        d.index = dss_index(d.index, CONTEXT.timezone, calendar_daily,
                           getattr(cfg, 'CWMS_DAILY_TIMEZONE', 'America/Los_Angeles'))
    else:
        d.index = d.index.tz_convert(None)

    s = pd.to_numeric(d["value"], errors="coerce").astype("float64")
    s = s.replace([np.inf, -np.inf], np.nan).dropna()
    return s

def _shift_series_index(series: pd.Series, time_shift) -> pd.Series:
    """Shift series timestamps by a pandas Timedelta-compatible value."""
    if series is None or series.empty or time_shift is None:
        return series
    s = series.copy()
    s.index = s.index + pd.to_timedelta(time_shift)
    return s

def _infer_dss_meta_from_path(pathname: str) -> Tuple[int, str]:
    """
    Infer interval + DSS type from the pathname.
    Assumptions based on your paths:
      /1DAY/  -> 1440, PER-AVER
      /6HOUR/ -> 360,  INST-VAL

    Rule curve paths are written as INST-VAL.
    """
    up = pathname.upper()
    if "RULECURVE" in up or "RULE CURVE" in up:
        return 1440, "INST-VAL"
    if "/1DAY/" in up or "/1D/" in up:
        return 1440, "PER-AVER"
    if "/6HOUR/" in up or "/6H/" in up:
        return 360, "INST-VAL"
    return 1440, "PER-AVER"

def _write_series_v6(fid, pathname: str, series: pd.Series, units: str, interval_min: int, dss_type: str, decimals: int = 2):
    if series is None or series.empty:
        return False

    series = series.sort_index()
    start_dt = series.index[0].strftime("%d%b%Y %H%M").upper()

    tsc = TimeSeriesContainer()
    tsc.pathname = pathname
    tsc.startDateTime = start_dt
    tsc.numberValues = len(series)
    tsc.units = units
    tsc.type = dss_type
    tsc.interval = interval_min
    values = np.round(series.to_numpy(dtype="float64"), decimals)
    if CONTEXT:
        from pydsstools.core import UNDEFINED
        values = np.where(np.isnan(values), UNDEFINED, values)
    tsc.values = values

    fid.put_ts(tsc)
    return True

# =====================================================================
# CORE: download + write
# =====================================================================

def cwms_download_and_write(
    tsid_to_dss: Dict[str, str],
    begin,
    end,
    office="nws",
    office_id="NWDP",
    units="FT",
    decimals=2,
    time_shift=None,
    force_dss_type=None,
) -> int:
    begin_dt = _to_py_datetime_utc(begin)
    end_dt = _to_py_datetime_utc(end)

    api_root = f"https://wm.{office}.ds.usace.army.mil:8243/nwdp-data/"
    cwms.api.init_session(api_root=api_root)

    print(
        f"\n[CWMS] api_root={api_root} office_id={office_id} units={units} "
        f"begin={begin_dt} end={end_dt} n_tsid={len(tsid_to_dss)}"
    )

    written = 0
    empty = 0
    failed: List[Tuple[str, str]] = []

    out_dir = os.path.dirname(DSS_FILE_OUT)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    fid = HecDss.Open(DSS_FILE_OUT, version=7 if CONTEXT else 6)
    try:
        for i, (tsid, dss_path) in enumerate(tsid_to_dss.items(), start=1):
            print(f"[CWMS] ({i}/{len(tsid_to_dss)}) START  tsid={tsid} -> dss={dss_path}")

            try:
                ts = cwms.get_timeseries(tsid, office_id=office_id, begin=begin_dt, end=end_dt)
                df = getattr(ts, "df", None)

                if df is None or df.empty:
                    empty += 1
                    print(f"[CWMS] ({i}/{len(tsid_to_dss)}) EMPTY  tsid={tsid}")
                    continue

                interval_min, dss_type = _infer_dss_meta_from_path(dss_path)
                s = _df_to_series(df, calendar_daily=(interval_min == 1440))
                if s.empty:
                    empty += 1
                    print(f"[CWMS] ({i}/{len(tsid_to_dss)}) EMPTY(clean)  tsid={tsid}")
                    continue

                if time_shift is not None:
                    s = _shift_series_index(s, time_shift)

                historical_observations = tsid_to_dss is OBS_ELEV_DICT or tsid_to_dss is OBS_OUTFLOW_DICT
                if CONTEXT and historical_observations:
                    from cwms_time import preserve_gaps
                    s = preserve_gaps(s, interval_min)
                    if s.isna().any():
                        print('[CWMS] {}: preserving {} missing observation slots; no interpolation'.format(tsid, int(s.isna().sum())))

                if CONTEXT and tsid_to_dss is LOOKBACK_ELEV_DICT:
                    CONTEXT.validate_series(s, interval_min, end=CONTEXT.start)
                elif CONTEXT:
                    CONTEXT.validate_series(s, interval_min, begin=s.index[0], end=s.index[-1],
                                            allow_missing=historical_observations)
                if force_dss_type is not None:
                    dss_type = force_dss_type

                ok = _write_series_v6(
                    fid=fid,
                    pathname=dss_path,
                    series=s,
                    units=units,
                    interval_min=interval_min,
                    dss_type=dss_type,
                    decimals=decimals,
                )

                if ok:
                    written += 1
                    print(
                        f"[CWMS] ({i}/{len(tsid_to_dss)}) OK     tsid={tsid}  "
                        f"n={len(s)}  start={s.index[0]}  end={s.index[-1]}"
                    )
                    print(f"[DSS ] ({i}/{len(tsid_to_dss)}) WROTE  {dss_path}")
                else:
                    failed.append((tsid, "write returned False (empty?)"))
                    print(f"[CWMS] ({i}/{len(tsid_to_dss)}) FAIL   tsid={tsid}  reason=write returned False")

            except Exception as e:
                msg = f"{type(e).__name__}: {e}"
                failed.append((tsid, msg))
                print(f"[CWMS] ({i}/{len(tsid_to_dss)}) FAIL   tsid={tsid}  err={msg}")

    finally:
        fid.close()

    print(f"\n[CWMS] SUMMARY units={units} written={written} empty={empty} failed={len(failed)}")
    if failed:
        print("[CWMS] FAIL LIST:")
        for tsid, msg in failed:
            print(f"  - {tsid} -> {msg}")

    if CONTEXT and (failed or empty):
        raise RuntimeError("CWMS missing or failed series: %r; empty=%d" % (failed, empty))
    return written

# =====================================================================
# RUN AS SCRIPT
# =====================================================================

def prepare_cwms_groups(required_job, optional_jobs, download):
    """Required inputs fail fast; plotting failures are reported separately."""
    name, mapping, begin, end, options = required_job
    required_count = download(mapping, begin, end, **options)
    print("Required lookback elevations written:", required_count)
    warnings = []
    for name, mapping, begin, end, options in optional_jobs:
        try:
            count = download(mapping, begin, end, **options)
            print("Plotting group %s: %d series written" % (name, count))
        except Exception as exc:
            warnings.append((name, str(exc)))
            print("[PLOTTING WARNING] %s: %s" % (name, exc))
    print("Optional plotting groups with failures:", len(warnings))
    return required_count, warnings


if __name__ == "__main__":
    from windows_ca import configure_ca_bundle
    configure_ca_bundle()
    now_utc = pd.Timestamp.now(tz="UTC")
    first_of_year_utc = now_utc.normalize().replace(month=1, day=1)
    if CONTEXT:
        first_of_year_utc = min(first_of_year_utc, pd.Timestamp(CONTEXT.utc(CONTEXT.lookback)))
        begin, end = CONTEXT.lookback_request_bounds()
    else:
        begin, end = now_utc, now_utc + pd.Timedelta(days=10)

    required = ("lookback elevations", LOOKBACK_ELEV_DICT, begin, end,
                dict(units="FT", decimals=2))
    optional = [
        ("observed elevations", OBS_ELEV_DICT, first_of_year_utc, now_utc,
         dict(units="FT", decimals=2)),
        ("observed outflows", OBS_OUTFLOW_DICT, first_of_year_utc, now_utc,
         dict(units="CFS", decimals=1)),
        ("plotting rule curves", RC_ELEV_DICT, first_of_year_utc, now_utc,
         dict(units="FT", decimals=2, time_shift=pd.Timedelta(hours=-8),
              force_dss_type="INST-VAL"))
    ]
    n3, plotting_warnings = prepare_cwms_groups(required, optional, cwms_download_and_write)
    print("DSS out:", DSS_FILE_OUT)
