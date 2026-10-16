"""Named standalone archives and offline plotting; no CONFIG.py or trial plot controls."""
import argparse
from datetime import datetime,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import re
import secrets
import shutil
import threading
import uuid
import webbrowser

from baseline_versions import atomic_json,digest_file
from run_archive import capture_run,metadata,open_archive,signature


def catalog(root):
    runs=[]
    for path in sorted((Path(root)/'standalone-results').glob('run-*/capture.json')):
        data=json.loads(path.read_text());data['id']=path.parent.name;runs.append(data)
    return sorted(runs,key=lambda row:row['created_utc'],reverse=True)


def outputs(root,run_type="ensemble"):
    from pydsstools.heclib.dss import HecDss
    from run_data_cache import needed_record
    codes=set()
    with HecDss.Open(str(Path(root)/'simulation.dss')) as dss:
        paths=dss.getPathnameList('/*/*/*/*/*/*/')
        if not paths:paths=dss.getPathnameList('*')
        for path in paths:
            parts=str(path).split('/')
            if len(parts)!=8 or not needed_record(parts):continue
            match=re.fullmatch((r'C:\d{6}\|' if run_type=='ensemble' else '')+r'([A-Za-z][A-Za-z0-9_-]*)',parts[6])
            if match:codes.add(match[1])
    return sorted(codes)


def capture(root,alternative,label,code,kind,baseline_id=None,confirmed=False,run_type="ensemble"):
    root=Path(root)
    if run_type not in ('ensemble','por'):raise ValueError('Invalid run type')
    if not confirmed:raise ValueError('Confirm successful compute before capturing results')
    if kind not in ('baseline','result') or not isinstance(label,str) or not label.strip():raise ValueError('Choose baseline/result and a name')
    saved={row['id']:row for row in catalog(root)}
    if kind=='result' and (baseline_id not in saved or saved[baseline_id]['kind']!='baseline'):
        raise ValueError('Select an archived baseline for this result')
    if kind=='result' and saved[baseline_id]['alternative']!=alternative:
        raise ValueError('Baseline belongs to a different native alternative')
    # Exact alternative/run spelling comes from the catalog; case is ignored only
    # for comparison. This admits native padding/hyphen naming plus trial digits.
    prefix=alternative.replace(' ','-').ljust(10,'-')
    if not re.fullmatch(re.escape(prefix)+r'\d+',code,re.I):raise ValueError('Output suffix does not match the selected alternative')
    if kind=='result' and saved[baseline_id].get('run_type','ensemble')!=run_type:raise ValueError('Baseline run type differs')
    if code not in outputs(root,run_type):raise ValueError('Selected output is absent from this simulation')
    archive=root/'standalone-results';archive.mkdir(exist_ok=True)
    pending=archive/('pending-'+uuid.uuid4().hex);pending.mkdir()
    source=root/'simulation.dss';before=signature(source)
    try:
        capture_run(source,pending,code,standalone=True,run_type=run_type)
        info=metadata(pending/'forecast.dss')
        records=info['records']
        members=sorted({int(re.search(r'C:(\d+)\|',item['pathname'])[1]) for item in records.values()}) if run_type=='ensemble' else []
        for member in members if run_type=='ensemble' else [None]:
            pools={}
            for item in records.values():
                parts=item['pathname'].split('/')
                if (member is None or re.search(r'C:(\d+)\|',item['pathname'])[1]==str(member).zfill(6)) and parts[2].upper().endswith('-POOL'):
                    pools.setdefault(parts[2].upper(),set()).add(parts[3].upper())
            if not pools or any('FLOW-OUT' not in params or not {'ELEV','ELEVATION'}&params for params in pools.values()):
                raise ValueError('Member lacks paired pool elevation/outflow: '+str(member))
        if kind=='result' and members!=saved[baseline_id]['members']:
            raise ValueError('Result member selection differs from its baseline')
        pointer=root/'standalone-baseline-config-active.json'
        applied=None
        if pointer.exists():
            applied=json.loads(pointer.read_text());source_config=root/applied['directory']
            if applied.get('model_alternative')!=alternative:raise ValueError('Applied configuration alternative differs')
            if digest_file(source_config/'resolved.json')!=applied['resolved_sha256']:raise ValueError('Applied configuration checksum mismatch')
            shutil.copytree(source_config,pending/'configuration-provenance')
        identity='run-'+uuid.uuid4().hex
        data={'format':'standalone-saved-result','label':label.strip(),'kind':kind,
              'baseline_id':identity if kind=='baseline' else baseline_id,'run_code':code.upper(),
              'alternative':alternative,'simulation':root.name,'members':members,'run_type':run_type,
              'synthetic_members':[m for m in members if m in (3000,3001,3002,3003)],
              'created_utc':datetime.now(timezone.utc).isoformat(),
              'archive_sha256':digest_file(pending/'run-archive.json'),
              'configuration_id':applied['id'] if applied else None,
              'compute_status':'user-confirmed-success-not-independently-verified',
              'scope':'Configuration provenance is the applied snapshot at capture, not independent proof that it produced every output. Catalog-selected members for this output suffix. Presence does not prove freshness; capture only after checking full native completion.'}
        if signature(source)!=before:raise ValueError('Simulation DSS changed during capture')
        atomic_json(pending/'capture.json',data);pending.rename(archive/identity)
        return dict(data,id=identity)
    except BaseException:
        # Partial captures are not published in the run-* catalog.
        raise


def plot(root,identities):
    from plot_rts_forecast import output_groups,clean_series,make_figure
    import pandas as pd
    from plotly.offline import get_plotlyjs
    import plotly.graph_objects as go
    from html import escape
    root=Path(root);saved={row['id']:row for row in catalog(root)}
    if len(identities) not in (1,2) or len(set(identities))!=len(identities):raise ValueError('Choose one or two distinct saved runs')
    selected=[saved[identity] for identity in identities]
    frames={};units={}
    for row in selected:
        directory=root/'standalone-results'/row['id']
        if digest_file(directory/'run-archive.json')!=row['archive_sha256']:raise ValueError('Archive manifest changed')
        with open_archive(directory/'forecast.dss',row['run_code'],row['archive_sha256']) as handle:
            paths=handle.getPathnameList('/*/*/*/*/*/*/')
            if row.get('run_type','ensemble')=='por':
                from plot_rts_forecast import target_record
                groups={}
                for path in paths:
                    parts=path.split('/')
                    if target_record(parts) and parts[6].upper()==row['run_code'].upper():
                        groups.setdefault((parts[1],parts[2],parts[3],parts[5]),{})['POR']=path
            else:
                groups=output_groups(paths,row['run_code'],set(row['members']))
            for key,members in groups.items():
                data={};unit=None
                for member,path in members.items():
                    record=handle.read_ts(path);data[member]=clean_series(record)
                    if unit is not None and unit!=record.units:raise ValueError('Mixed plot units')
                    unit=record.units
                if key in units and units[key]!=unit:raise ValueError('Compared run units differ')
                units[key]=unit;frames[row['id'],key]=pd.DataFrame(data)
    keys=sorted({key for _,key in frames})
    if not keys:raise ValueError('No plot series in saved runs')
    destination=root/'output_plots'/('archived-'+uuid.uuid4().hex);destination.mkdir(parents=True)
    (destination/'plotly.min.js').write_text(get_plotlyjs(),encoding='utf-8')
    links=[]
    for number,key in enumerate(keys):
        _,location,parameter,_=key;figure=go.Figure()
        for row in selected:
            frame=frames.get((row['id'],key))
            if frame is None:continue
            if row.get('run_type','ensemble')=='por':
                figure.add_trace(go.Scatter(x=frame.index,y=frame['POR'],name=row['label']+' / POR',connectgaps=False))
                frame.to_csv(destination/('plot-'+str(number)+'-'+row['id']+'.csv'),index_label='timestamp')
                continue
            # Keep standalone synthetic members out of historical bands.
            synthetic_ids=set(row.get('synthetic_members',[2026,2027,2028,2029]))
            synthetic=frame[[m for m in frame if m in synthetic_ids]]
            historical=frame[[m for m in frame if m not in synthetic_ids]]
            figure_part=make_figure(historical,location+' '+parameter,units[key]) if len(historical.columns) else go.Figure()
            for trace in figure_part.data:
                trace.name=row['label']+' / '+str(trace.name);figure.add_trace(trace)
            for member in synthetic:
                label={3000:'Daily 25% inflow trace',3001:'Daily 50% inflow trace',3002:'Daily 75% inflow trace',3003:'OSI',2026:'Legacy daily 25% trace',2027:'Legacy daily 50% trace',2028:'Legacy daily 75% trace',2029:'Legacy OSI'}.get(member,'Synthetic '+str(member))
                figure.add_trace(go.Scatter(x=synthetic.index,y=synthetic[member],name=row['label']+' / '+label,connectgaps=False))
            frame.to_csv(destination/('plot-'+str(number)+'-'+row['id']+'.csv'),index_label='timestamp')
        figure.update_layout(title=location+' '+parameter,yaxis_title=str(units[key]))
        filename='plot-'+str(number)+'.html';figure.write_html(destination/filename,include_plotlyjs='plotly.min.js')
        links.append('<li><a href="'+filename+'">'+escape(location+' '+parameter)+'</a></li>')
    paired=len(selected)==2 and selected[0]['baseline_id']==selected[1]['baseline_id']
    (destination/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Saved standalone results</title><h1>Saved standalone results</h1><p>'+escape(' / '.join(row['label'] for row in selected))+'</p><p>'+('Same baseline pairing' if paired else 'One run, or different baseline pairings: differences may include baseline changes')+'</p><ul>'+''.join(links)+'</ul>',encoding='utf-8')
    atomic_json(destination/'selection.json',{'runs':selected,'same_baseline':paired})
    return destination/'index.html'


PAGE='''<!doctype html><meta charset="utf-8"><title>Standalone saved results</title><style>body{font:16px system-ui;max-width:1000px;margin:30px auto}input,select,button{font:inherit;padding:8px;margin:6px}label{display:block}pre{white-space:pre-wrap}</style><h1>Standalone saved results</h1><p id="target"></p><p>Capture only after checking successful native compute. Saved archives are independent of future changes to simulation.dss.</p><pre id="status" role="status"></pre><button onclick="refresh()">Refresh completed outputs and saved runs</button><label>Completed output <select id="output"></select></label><label>Name <input id="name" placeholder="Descriptive result name"></label><label>Archive purpose <select id="kind"><option value="baseline">New baseline</option><option value="result">Result paired with baseline</option></select></label><label>Baseline for result <select id="baseline"></select></label><button onclick="capture()">Archive completed results</button><hr><h2>Plot archived results</h2><p>Select one or two runs (Ctrl-click for two).</p><select multiple size="10" id="runs" style="width:95%"></select><br><button onclick="plot()">Plot selected saved runs</button><button onclick="closeEditor()">Close</button><script>
const TOKEN=__TOKEN__,TARGET=__TARGET__,RUN_TYPE=__RUN_TYPE__;document.getElementById('target').textContent=TARGET;
const el=id=>document.getElementById(id);async function call(path,data){el('status').textContent='Working…';const response=await fetch(path,{method:'POST',headers:{'X-Editor-Token':TOKEN},body:JSON.stringify(data)});const result=await response.json();if(!response.ok)throw Error(result.error);return result}
async function refresh(){try{const data=await call('/list',{});el('output').replaceChildren();for(const code of data.outputs)el('output').add(new Option(code,code));el('runs').replaceChildren();el('baseline').replaceChildren();for(const row of data.runs){let label=row.label+' ['+row.kind+'] '+row.created_utc;el('runs').add(new Option(label,row.id));if(row.kind==='baseline')el('baseline').add(new Option(label,row.id))}el('status').textContent=data.outputs.length?'Ready':'No compatible outputs found in simulation.dss for this mode. Verify the selected simulation and native run type.'}catch(e){el('status').textContent=e.message}}
async function capture(){if(!confirm('Has the selected native compute finished successfully for every intended member and date? Archive these results?'))return;try{await call('/capture',{label:el('name').value,code:el('output').value,kind:el('kind').value,baseline_id:el('baseline').value,confirmed:true});await refresh()}catch(e){el('status').textContent=e.message}}
async function plot(){try{const result=await call('/plot',{ids:[...el('runs').selectedOptions].map(o=>o.value)});el('status').textContent='Plots: '+result.path}catch(e){el('status').textContent=e.message}}
async function closeEditor(){await call('/close',{});document.body.textContent='Closed'}refresh();</script>'''


CHECK_PAGE='''<!doctype html><meta charset="utf-8"><title>Model Check</title>
<style>body{font:16px system-ui;max-width:850px;margin:30px auto}input,button{font:inherit;padding:8px;margin:8px}label{display:block}pre{white-space:pre-wrap}</style>
<h1>Model Check</h1><p id="target"></p><p>Uses the simulation and alternative selected in the workflow menu. Finish native compute before checking.</p>
<label>Report name (optional) <input id="name"></label>__MEMBER__
<button onclick="check()">Run Model Check</button><button onclick="closeEditor()">Close</button><pre id="status" role="status"></pre>
<script>const TOKEN=__TOKEN__,TARGET=__TARGET__,RUN_TYPE=__RUN_TYPE__;
document.getElementById('target').textContent=TARGET;
async function call(path,data){const response=await fetch(path,{method:'POST',headers:{'X-Editor-Token':TOKEN},body:JSON.stringify(data)});const result=await response.json();if(!response.ok)throw Error(result.error);return result}
async function check(){let status=document.getElementById('status');try{let data={label:document.getElementById('name').value};if(RUN_TYPE==='ensemble'){let value=document.getElementById('member').value;if(!value.trim())throw Error('Enter one ensemble member ID');data.member=Number(value)}if(!confirm('Confirm the selected simulation/alternative has finished computing and its current settings match these results.'))return;status.textContent='Checking…';let result=await call('/model_check',data);status.textContent='Report: '+result.path}catch(e){status.textContent=e.message}}
async function closeEditor(){await call('/close',{});document.body.textContent='Closed'}</script>'''


def serve(root,alternative,run_type="ensemble",check_only=False):
    root=Path(root);token=secrets.token_urlsafe(32)
    template=CHECK_PAGE if check_only else PAGE
    template=template.replace('__MEMBER__','<label>Ensemble member <input id="member" type="number" min="0" step="1"></label>' if run_type=='ensemble' else '')
    page=template.replace('__RUN_TYPE__',json.dumps(run_type)).replace('__TOKEN__',json.dumps(token)).replace('__TARGET__',json.dumps(str(root)+' / '+alternative+' / '+('Single POR' if run_type=='por' else 'Ensemble')).replace('</','<\\/'))
    task_lock=threading.Lock()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            if self.path!='/'+token:self.send_error(404);return
            self.send_response(200);self.end_headers();self.wfile.write(page.encode('utf-8'))
        def do_POST(self):
            if self.headers.get('X-Editor-Token')!=token:self.send_error(403);return
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<1024*1024:raise ValueError('Invalid request size')
                data=json.loads(self.rfile.read(length))
                if self.path=='/list':result={'outputs':outputs(root,run_type) if (root/'simulation.dss').is_file() else [],'runs':[row for row in catalog(root) if row.get('run_type','ensemble')==run_type]}
                elif self.path=='/capture':
                    if not task_lock.acquire(False):raise ValueError('Another archive task is running')
                    try:result=capture(root,alternative,run_type=run_type,**data)
                    finally:task_lock.release()
                elif self.path=='/model_check':
                    from standalone_model_check import run
                    if not task_lock.acquire(False):raise ValueError('Another result task is running')
                    try:path=run(root,alternative,None,run_type,data.get('member'),data.get('label'))
                    finally:task_lock.release()
                    webbrowser.open(path.resolve().as_uri());result={'path':str(path)}
                elif self.path=='/plot':
                    path=plot(root,data['ids']);webbrowser.open(path.resolve().as_uri());result={'path':str(path)}
                elif self.path=='/close':
                    result={};threading.Thread(target=server.shutdown,daemon=True).start()
                else:raise ValueError('Unknown action')
                code=200
            except Exception as error:result={'error':str(error)};code=400
            self.send_response(code);self.end_headers();self.wfile.write(json.dumps(result).encode())
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    webbrowser.open('http://127.0.0.1:'+str(server.server_port)+'/'+token)
    try:server.serve_forever()
    finally:server.server_close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--watershed',required=True,type=Path);parser.add_argument('--simulation',required=True);parser.add_argument('--alternative',required=True)
    parser.add_argument('--model-check',action='store_true')
    parser.add_argument('--run-type',choices=('ensemble','por'),default='ensemble')
    args=parser.parse_args();from standalone_configuration import context
    ctx=context(args.watershed,args.alternative,args.simulation);serve(Path(ctx['dss_path']).parent,args.alternative,args.run_type,args.model_check)
