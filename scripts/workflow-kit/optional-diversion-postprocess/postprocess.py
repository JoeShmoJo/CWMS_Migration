"""Optional diversion bookkeeping, read-only DSS input and separate CSV outputs."""
import argparse
from collections import defaultdict
import csv
from datetime import date
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import sys

import numpy as np
import pandas as pd


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def network_map(filename):
    data=json.loads(Path(filename).read_text())['network']['elements']
    mapping={}
    for key,element in data.items():
        if element['type']!='diversion':continue
        current='junction:'+element['junction'];visited=set();locations=[];barrier=None
        while current:
            if current in visited:raise ValueError('Network cycle: '+current)
            visited.add(current)
            if current.startswith('pool:') and current not in data:current='reservoir:'+current.split(':',1)[1]
            if current not in data:raise ValueError('Missing network element: '+current)
            node=data[current]
            if node['type']=='reservoir':barrier=node['name'];break
            if node['type']=='junction':locations.append(node['name'])
            current=node.get('downstream')
        mapping[element['name']]={'junction':element['junction'],'locations':locations,'reservoir_barrier':barrier}
    if not mapping:raise ValueError('No diversions in network')
    return mapping


def schedule(filename,mapping):
    with Path(filename).open(encoding='utf-8-sig',newline='') as handle:
        reader=csv.DictReader(line for line in handle if not line.lstrip().startswith('#'))
        names=[name for name in reader.fieldnames if name not in ('Month','Day','Notes','NOTES','')]
        if len(names)!=len(set(names)) or set(names)!=set(mapping):
            raise ValueError('CSV/network diversion names differ: '+str(set(names)^set(mapping)))
        table={}
        for row in reader:
            key=(int(row['Month']),int(row['Day']));date(2001,*key)
            if key in table:raise ValueError('Duplicate schedule date: '+str(key))
            values={name:float(row[name]) if row[name].strip() else 0. for name in names}
            if not all(math.isfinite(v) for v in values.values()):raise ValueError('Nonfinite schedule')
            table[key]=values
    if len(table)!=365:raise ValueError('Schedule must cover all 365 generic-year days')
    return table


def validate(config,mapping):
    if config.get('source_diversions') not in ('none','scheduled'):
        raise ValueError('Declare source_diversions: none or scheduled (avoids double subtraction)')
    if config.get('method')!='instantaneous-bookkeeping-stop-at-reservoir':
        raise ValueError('Explicitly select instantaneous-bookkeeping-stop-at-reservoir')
    if config.get('schedule_day') not in ('timestamp','period_start'):
        raise ValueError('Declare schedule_day: timestamp or period_start')
    if not isinstance(config.get('timestep_hours'),(int,float)) or isinstance(config['timestep_hours'],bool) or not math.isfinite(config['timestep_hours']) or not 0<config['timestep_hours']<=24:
        raise ValueError('Explicit timestep_hours required (0..24)')
    if not config.get('run_code') or not config.get('members') or not config.get('locations'):
        raise ValueError('Explicit run_code, members and junction locations required')
    if len(set(config['members']))!=len(config['members']) or len(set(config['locations']))!=len(config['locations']):
        raise ValueError('Duplicate members or locations')
    if any(isinstance(member,bool) or not isinstance(member,int) or member<0 for member in config['members']):
        raise ValueError('Members must be nonnegative integers')
    filenames=[re.sub(r'[^A-Za-z0-9_-]','_',name) for name in config['locations']]
    if len(filenames)!=len(set(filenames)):raise ValueError('Location filenames collide after normalization')
    known={location for item in mapping.values() for location in item['locations']}
    if not set(config['locations'])<=known:raise ValueError('Location is not downstream of a mapped diversion')
    for rule in config.get('conditions',[]):
        if not rule.get('enabled',False):continue
        if rule.get('operator') not in ('below','at_or_below','above','at_or_above'):
            raise ValueError('Invalid elevation operator')
        threshold=rule.get('threshold_ft')
        if not rule.get('reservoir') or isinstance(threshold,bool) or not isinstance(threshold,(int,float)) or not math.isfinite(threshold):raise ValueError('Reservoir/finite numeric threshold required')
        factor=rule['withdrawal_multiplier']
        if isinstance(factor,bool) or not isinstance(factor,(int,float)) or not 0<=factor<=1:
            raise ValueError('withdrawal_multiplier must be 0..1')
        selected=rule['elements']
        if not selected or len(set(selected))!=len(selected) or not set(selected)<=set(mapping):raise ValueError('Unknown/duplicate condition elements')


def demand(index,table,config,elevations):
    if not index.is_monotonic_increasing or index.has_duplicates or len(index)<2:raise ValueError('At least two ordered timestamps required')
    steps=np.diff(index.asi8)
    if not (steps==pd.Timedelta(hours=config['timestep_hours']).value).all() or steps[0]<=0:raise ValueError('Uniform timestep required')
    clock=index-pd.Timedelta(int(steps[0]),unit='ns') if config['schedule_day']=='period_start' else index
    rows=[table[(t.month,28 if t.month==2 and t.day==29 else t.day)] for t in clock]
    baseline=pd.DataFrame(rows,index=index,dtype=float);effective=baseline.copy()
    for rule in config.get('conditions',[]):
        if not rule.get('enabled',False):continue
        levels=elevations[rule['reservoir']].reindex(index)
        if levels.isna().any() or not np.isfinite(levels).all():raise ValueError('Missing elevation coverage: '+rule['reservoir'])
        threshold=rule['threshold_ft'];op=rule['operator']
        active={'below':levels<threshold,'at_or_below':levels<=threshold,'above':levels>threshold,'at_or_above':levels>=threshold}[op]
        for name in rule['elements']:
            # Multiple active rules choose the strongest reduction, never multiply twice.
            candidate=baseline[name]*rule['withdrawal_multiplier']
            mask=active & (baseline[name]>0)
            effective.loc[mask,name]=np.minimum(effective.loc[mask,name],candidate.loc[mask])
    return baseline,effective


def calculate(flows,baseline,effective,mapping,source_mode):
    result={}
    for location,raw in flows.items():
        names=[name for name,item in mapping.items() if location in item['locations']]
        included=baseline[names].sum(axis=1) if source_mode=='scheduled' else pd.Series(0.,index=raw.index)
        net=effective[names].sum(axis=1)
        adjusted=raw+included-net
        if adjusted.isna().any() or not np.isfinite(adjusted).all():raise ValueError('Invalid adjusted flows')
        if (adjusted<0).any():raise ValueError('Negative adjusted flow at '+location+'; no silent clipping')
        result[location]=pd.DataFrame({'raw_flow_cfs':raw,'source_scheduled_net_cfs':included,
                                     'effective_net_cfs':net,'adjusted_flow_cfs':adjusted})
    return result


def read_series(dss,paths):
    samples={};metadata=None
    for path in sorted(paths):
        record=dss.read_ts(path,trim_missing=True)
        times=pd.DatetimeIndex(record.pytimes)
        values=np.ma.asarray(record.values,dtype=float).filled(np.nan)
        current=(str(record.units).upper(),str(record.type).upper(),path.split('/')[5].upper())
        if metadata is not None and metadata!=current:raise ValueError('Mixed metadata for logical series')
        metadata=current
        if len(times)!=len(values) or times.has_duplicates or times.hasnans:raise ValueError('Invalid timestamps')
        for stamp,value in zip(times,values):
            if not np.isfinite(value) or value in (-901,-902,-903) or abs(value)>1e30:continue
            if stamp in samples and samples[stamp]!=value:raise ValueError('Conflicting DSS blocks')
            samples[stamp]=float(value)
    if metadata is None:raise ValueError('Required DSS series absent')
    return pd.Series(samples,dtype=float).sort_index(),metadata


def run(args):
    config=json.loads(args.config.read_text());mapping=network_map(args.network);validate(config,mapping)
    table=schedule(args.schedule,mapping)
    for rule in config.get('conditions',[]):
        if rule.get('enabled',False) and any(any(row[name]<0 for row in table.values()) for name in rule['elements']):
            raise ValueError('Withdrawal reduction conditions cannot target negative return schedules')
    if args.output.exists():raise ValueError('Choose a new output directory; existing outputs are never overwritten')
    for path in (args.source,args.network,args.schedule,args.config):
        if args.output.resolve() in path.resolve().parents:raise ValueError('Output cannot contain an input')
    signature=(args.source.stat().st_size,args.source.stat().st_mtime_ns)
    from pydsstools.heclib.dss import HecDss
    args.output.mkdir(parents=True)
    manifest={'status':'incomplete','config':config,'inputs':{str(p.resolve()):sha(p) for p in (args.network,args.schedule,args.config)},
              'source_dss':str(args.source.resolve()),'source_signature':signature,'network_map':mapping,
              'assumptions':['Same-timestamp junction bookkeeping; no Muskingum routing or travel-time model.',
                             'Effects stop at the next reservoir. Reservoir outflows/elevations remain simulated values.',
                             'Negative returns remain fixed; no automatic return scaling.',
                             'No feedback to compute, augmentation, accepted archives or existing plots.']}
    try:
        with HecDss.Open(str(args.source.resolve())) as dss, gzip.open(args.output/'diversion-audit.csv.gz','wt',newline='') as audit:
            writer=csv.writer(audit);writer.writerow(['member','timestamp','element','scheduled_cfs','effective_cfs','source_included_cfs','delta_to_junction_cfs'])
            catalog=defaultdict(list)
            for pathname in dss.getPathnameList('/*/*/*/*/*/*/'):
                parts=str(pathname).split('/')
                if len(parts)!=8:continue
                match=re.fullmatch(r'C:(\d+)\|(.*)',parts[6],re.I)
                if match and match[2].upper()==config['run_code'].upper() and int(match[1]) in config['members']:
                    catalog[int(match[1]),parts[2].upper(),parts[3].upper()].append(str(pathname))
            for member in config['members']:
                flows={};elevations={};reference=None
                for location in config['locations']:
                    values,meta=read_series(dss,catalog[member,location.upper(),'FLOW'])
                    if meta[0] not in ('CFS','FT3/S','FT^3/S') or meta[1]!='PER-AVER':raise ValueError('Expected period-average flow in CFS')
                    start=pd.Timestamp(config['start']);end=pd.Timestamp(config['end'])
                    values=values.loc[start:end]
                    if reference is None:reference=values.index
                    if not values.index.equals(reference):raise ValueError('Junction flow coverage differs')
                    flows[location]=values
                for rule in config.get('conditions',[]):
                    if not rule.get('enabled',False):continue
                    name=rule['reservoir']
                    levels,meta=read_series(dss,catalog[member,(name+'-Pool').upper(),'ELEV'])
                    if meta[0] not in ('FT','FEET'):raise ValueError('Expected reservoir elevation in feet')
                    elevations[name]=levels
                baseline,effective=demand(reference,table,config,elevations)
                # Require the requested endpoints and full uniform coverage; do not accept old partial runs.
                if reference[0]!=pd.Timestamp(config['start']) or reference[-1]!=pd.Timestamp(config['end']):raise ValueError('Requested endpoints absent')
                for location,frame in calculate(flows,baseline,effective,mapping,config['source_diversions']).items():
                    name=re.sub(r'[^A-Za-z0-9_-]','_',location)
                    frame.to_csv(args.output/('member-'+str(member)+'-'+name+'.csv.gz'),index_label='timestamp')
                for timestamp in reference:
                    for name in baseline.columns:
                        before=baseline.at[timestamp,name] if config['source_diversions']=='scheduled' else 0.
                        after=effective.at[timestamp,name]
                        writer.writerow([member,timestamp,name,baseline.at[timestamp,name],after,before,before-after])
        if signature!=(args.source.stat().st_size,args.source.stat().st_mtime_ns):raise ValueError('Source changed during postprocessing')
        manifest['status']='complete'
    except BaseException as error:
        manifest['error']=str(error)
        raise
    finally:
        manifest['outputs']={p.name:sha(p) for p in args.output.glob('*.gz')}
        (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2))
    print('Postprocessing complete:',args.output)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source','network','schedule','config','output'):parser.add_argument('--'+name,required=True,type=Path)
    args=parser.parse_args();run(args)
