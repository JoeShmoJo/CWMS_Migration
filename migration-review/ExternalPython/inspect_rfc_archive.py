"""Read-only RFC Parquet inventory and bounded sample inspection. No DSS access."""
import argparse
import json
from pathlib import Path
import re


def scalar(value):
    import pandas as pd
    if pd.isna(value): return None
    if hasattr(value,'isoformat'): return value.isoformat()
    if hasattr(value,'item'): return value.item()
    return str(value)


def sample_info(path):
    import pandas as pd
    import pyarrow.parquet as pq
    # ParquetFile reads this file directly, without inferring Hive partitions.
    parquet=pq.ParquetFile(path)
    frame=parquet.read().to_pandas()
    required={'valid_datetime','trace_year','value','issued_datetime'}
    missing=required-set(frame.columns)
    if missing: raise ValueError('Missing archive columns: '+str(sorted(missing)))
    times=pd.to_datetime(frame['valid_datetime'],errors='coerce')
    years=sorted(int(year) for year in frame['trace_year'].dropna().unique())
    unique_times=pd.DatetimeIndex(times.dropna().unique()).sort_values()
    intervals=unique_times.to_series().diff().dropna().value_counts()
    result={'path':str(path),'schema':str(parquet.schema_arrow),'rows':len(frame),
        'valid_time_timezone':str(times.dt.tz),'valid_first':scalar(times.min()),'valid_last':scalar(times.max()),
        'bad_timestamps':int(times.isna().sum()),'trace_years':years,
        'interval_counts':{str(key):int(count) for key,count in intervals.items()},
        'duplicate_time_member_rows':int(frame.duplicated(['valid_datetime','trace_year']).sum()),
        'missing_values':int(pd.to_numeric(frame['value'],errors='coerce').isna().sum()),
        'rows_per_member_min':int(frame.groupby('trace_year',observed=True).size().min()),
        'rows_per_member_max':int(frame.groupby('trace_year',observed=True).size().max())}
    for column in ('issued_datetime','issued_time_is_estimated','units','years_type','configuration','qpfdays'):
        result[column]=[scalar(value) for value in frame[column].unique()] if column in frame else 'COLUMN ABSENT'
    return result


def inventory(root):
    root=Path(root)
    if not root.is_dir(): raise ValueError('Archive directory missing: '+str(root))
    stations=[];samples=[]
    for folder in sorted(root.glob('station=*')):
        paths=sorted(folder.glob('issued_year=*/*.parquet'),key=lambda path:path.name)
        if not paths: continue
        dates=[match.group(1) for path in paths if (match:=re.search(r'_(\d{8})\.parquet$',path.name))]
        stations.append({'station':folder.name.split('=',1)[1],'files':len(paths),
            'filename_issue_date_first':min(dates) if dates else None,'filename_issue_date_last':max(dates) if dates else None,
            'issued_year_partitions':sorted(item.name for item in folder.glob('issued_year=*') if item.is_dir())})
        samples.append((folder.name,paths[0],paths[-1]))
    if not stations: raise ValueError('No station=*/issued_year=*/*.parquet files found')
    return stations,samples


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',required=True)
    args=parser.parse_args();root=Path(args.root)
    stations,samples=inventory(root)
    print('READ ONLY: no downloads, conversions, or DSS files opened.')
    for name in ('README.txt','_date_coverage_report.txt','_failed_files.txt'):
        path=root/name
        if path.exists():
            lines=path.read_text(encoding='utf-8-sig',errors='replace').splitlines()
            print('\n'+name+' ('+str(len(lines))+' lines; first 12):')
            print('\n'.join(lines[:12]))
    print('\nSTATION INVENTORY:')
    print(json.dumps(stations,indent=2))
    preferred={'station=BLUO3I','station=ALBO3XE','station=TRSO3'}
    chosen=[item for item in samples if item[0] in preferred]
    chosen += [item for item in samples if item not in chosen][:max(0,3-len(chosen))]
    print('\nPARQUET SAMPLES (first and last issue at up to three stations):')
    for _,first,last in chosen:
        for path in dict.fromkeys((first,last)):
            try: print(json.dumps(sample_info(path),indent=2))
            except ImportError as exc: raise SystemExit('Inspector requires pandas and pyarrow in this Python environment: '+str(exc))
            except Exception as exc: print(json.dumps({'path':str(path),'inspection_error':str(exc)}))
    print('\nInspection complete. No files changed.')


if __name__=='__main__': main()
