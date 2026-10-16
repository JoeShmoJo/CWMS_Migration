"""POR input adapter for the existing daily augmentation calculations.

Read actual native blocks, retaining the source F-part. Subdaily PER-AVER flows
become complete-day means; instantaneous storage is taken at day end. No native
results are overwritten by this reader. The calculator writes its usual daily
augmentation requirement records, which must be mapped in ResSim as before.
"""
import re
import numpy as np
import pandas as pd
from standalone_model_check import select_output


def por_fparts(filename,alternative):
    from pydsstools.heclib.dss import HecDss
    with HecDss.Open(str(filename)) as dss:
        paths=dss.getPathnameList('/*/*/*/*/*/*/')
        if not paths:paths=dss.getPathnameList('*')
    return [select_output(paths,alternative,'por')]


def daily_series(series,interval,parameter,kind):
    """Timestamp is the interval end, matching native daily DSS output."""
    match=re.fullmatch(r'(\d+)(MIN|MINUTE|HOUR|DAY)',interval.upper())
    if not match:raise ValueError('Unsupported POR input interval: '+interval)
    minutes=int(match[1])*{'MIN':1,'MINUTE':1,'HOUR':60,'DAY':1440}[match[2]]
    if minutes>1440 or 1440%minutes:raise ValueError('POR interval must divide a day: '+interval)
    series=series.sort_index()
    if series.index.has_duplicates:raise ValueError('Conflicting duplicate POR timestamps')
    if series.empty or not np.isfinite(series.to_numpy(dtype=float)).all() or (series<=-3e38).any():raise ValueError('Missing/undefined POR inputs')
    if len(series)>1 and not ((series.index[1:]-series.index[:-1])==pd.Timedelta(minutes=minutes)).all():raise ValueError('Gap in POR input time coverage')
    if minutes==1440:return series
    groups=series.resample('D',closed='right',label='right')
    counts=groups.count();complete=counts==1440//minutes
    # A lookback may begin/end part way through a day. Only boundary partial
    # days may be omitted; missing interior data must never be filled.
    if len(counts)>2 and not complete.iloc[1:-1].all():raise ValueError('Incomplete interior POR day')
    if parameter.upper().startswith('FLOW'):
        if kind.upper() not in ('PER-AVER','PER-AVG'):raise ValueError('Subdaily POR flows must be period averages')
        result=groups.mean()
    else:result=groups.last()
    result=result[complete]
    if result.empty:raise ValueError('No complete days in POR inputs')
    return result


def read_daily_por(dss_file,base_path_dict,dparts=None,fid=None):
    from pydsstools.heclib.dss import HecDss
    owned=fid is None
    if owned:fid=HecDss.Open(str(dss_file))
    try:
        paths=fid.getPathnameList('/*/*/*/*/*/*/')
        if not paths:paths=fid.getPathnameList('*')
        columns={}
        for alias,requested in base_path_dict.items():
            wanted=requested.upper().split('/')
            matches=[]
            for path in paths:
                parts=str(path).split('/')
                if len(parts)==8 and all(parts[i].upper()==wanted[i] for i in (1,2,3,6)):matches.append(str(path))
            if not matches:raise ValueError('Required POR augmentation input absent: '+requested)
            intervals={path.split('/')[5].upper() for path in matches}
            if len(intervals)!=1:raise ValueError('Ambiguous POR input intervals: '+requested)
            pieces=[];kinds=set()
            for path in sorted(matches):
                ts=fid.read_ts(path,trim_missing=True)
                kinds.add(str(getattr(ts,'type','')))
                values=np.asarray(ts.values,dtype=float).copy()
                missing=getattr(ts,'nodata',None)
                if missing is not None and np.asarray(missing).shape==values.shape:values[np.asarray(missing,dtype=bool)]=np.nan
                pieces.append(pd.Series(values,index=pd.to_datetime(ts.pytimes)))
            combined=pd.concat(pieces).sort_index()
            # Some readers return the full logical series for each physical
            # block. Collapse equal repeats, reject conflicting repeats.
            if combined.index.has_duplicates:
                if (combined.groupby(level=0).nunique(dropna=False)>1).any():raise ValueError('Conflicting POR input blocks')
                combined=combined[~combined.index.duplicated()]
            if len(kinds)!=1:raise ValueError('Inconsistent POR input data types')
            columns[alias]=daily_series(combined,intervals.pop(),wanted[3],kinds.pop())
        result=pd.DataFrame(columns)
        if result.empty or result.isna().any().any():raise ValueError('POR augmentation inputs have different daily coverage')
        return result
    finally:
        if owned:fid.close()
