"""Resolve, validate and stage forecast-scoped baseline settings; serve editor."""
import argparse
import copy
import csv
from datetime import date
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import tempfile
import uuid

from baseline_versions import atomic_json, digest_file, disable, event, registry

TABLE_KEYS = {'DeepDrawdownConfigCSV': ('deep_drawdown','configuration'),
    'SpringSpillConfigCSV': ('spring_spill','configuration'),
    'NoDraftConfigCSV': ('no_draft','configuration'),
    'secondaryDraftConfigCSV': ('secondary_flood_draft','configuration'),
    'firoSpaceConfigCSV': ('firo_space','schedule'),
    'minFlowConfigCSV': ('minimum_flow_withdrawal','minimum_flows'),
    'withdrawalConfigCSV': ('minimum_flow_withdrawal','withdrawals'),
    'diversionConfigCSV': ('diversions','schedule')}
MODULE_KEYS = {'DeepDrawdown':'deep_drawdown','SpringSpill':'spring_spill',
    'NoDraft':'no_draft','SecondaryFloodDraftLimit':'secondary_flood_draft',
    'FIRO_SPACE':'firo_space','MinFlowPlusWithdrawal':'minimum_flow_withdrawal',
    'DiversionFromCSV':'diversions','IRRM':'irrm','DraftToRC':'draft_to_rc',
    'FillLOPfirst':'fill_lop_first','HCR_LOP_Balance':'hcr_lop_balance'}
RESERVOIRS = {'Big Cliff','Blue River','Cottage Grove','Cougar','Detroit','Dexter',
             'Dorena','Fall Creek','Fern Ridge','Foster','Green Peter','Hills Creek','Lookout Point'}


def read_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as handle:
        rows = [row for row in csv.reader(handle) if row and any(cell.strip() for cell in row)
                and not row[0].lstrip().startswith('#')]
    if len(rows) < 2:
        raise ValueError('CSV needs a header and data: ' + str(path))
    return rows[0], [[None if not cell.strip() else cell for cell in row] for row in rows[1:]]


def validate_table(rule, name, table, template):
    columns, rows = table['columns'], table['rows']
    if not columns or len(set(columns)) != len(columns) or any(not isinstance(c, str) or not c.strip() for c in columns):
        raise ValueError('Empty or duplicate columns: ' + rule)
    if not rows or any(not isinstance(row, list) or len(row) != len(columns) for row in rows):
        raise ValueError('Missing rows or inconsistent widths: ' + rule)
    for row in rows:
        if any(value is not None and not isinstance(value, (str, int, float, bool)) for value in row):
            raise ValueError('Table cells must be scalar values: ' + rule)
    daily = columns[:2] == ['Month','Day']
    if daily:
        expected = template['columns']
        if any(c not in expected for c in columns):
            raise ValueError('Unrecognized reservoir or element column: ' + rule)
        days = set()
        for row in rows:
            month, day = int(str(row[0])), int(str(row[1]))
            date(2001, month, day)  # Existing readers use a non-leap generic year.
            if (month, day) in days:
                raise ValueError('Duplicate schedule day: ' + rule)
            days.add((month, day))
            for col, value in zip(columns[2:],row[2:]):
                if col.upper() != 'NOTES' and value is not None:
                    number = float(value)
                    if not math.isfinite(number):
                        raise ValueError('Invalid schedule value: ' + rule)
        if len(days) != 365:
            raise ValueError('Daily schedule must contain every day of the generic year: ' + rule)
    elif rule == 'secondary_flood_draft':
        if columns != template['columns']:
            raise ValueError('Secondary flood columns must match the current model')
        by_key = {row[0]: row for row in rows}
        if len(by_key) != len(rows) or not {'LimitDrafts','SecondaryFloodElev','MinDraftRate','PhCap'} <= set(by_key):
            raise ValueError('Invalid secondary flood variables')
        for index, reservoir in enumerate(columns[1:],1):
            if reservoir == 'Notes': continue
            enabled = str(by_key['LimitDrafts'][index]).upper()
            if enabled not in ('TRUE','FALSE'): raise ValueError('Invalid LimitDrafts flag')
            for key in ('SecondaryFloodElev','MinDraftRate','PhCap'):
                value = by_key[key][index]
                if value is None and enabled == 'FALSE': continue
                if value is None or not math.isfinite(float(value)):
                    raise ValueError('Missing/invalid secondary flood setting: ' + reservoir)
                if key != 'SecondaryFloodElev' and float(value) < 0:
                    raise ValueError('Negative secondary draft/capacity')
    else:
        required = set(template['columns']) - {'Notes','NOTES'}
        if not required <= set(columns): raise ValueError('Missing event table columns: ' + rule)
        for row in rows:
            values = dict(zip(columns,row))
            reservoir = values.get('RESERVOIR',values.get('Project'))
            if reservoir not in RESERVOIRS: raise ValueError('Unknown reservoir: ' + str(reservoir))
            for key, value in values.items():
                if key in ('Notes','NOTES','RESERVOIR','Project'): continue
                if key == 'ACTIVE':
                    if str(value).upper() not in ('TRUE','FALSE'): raise ValueError('Invalid ACTIVE flag')
                elif value is None or not math.isfinite(float(value)):
                    raise ValueError('Invalid event setting: ' + key)
            for prefix in ('START_','TARGET_','END_',''):
                month_key, day_key = prefix+'MONTH',prefix+'DAY'
                if not prefix: month_key, day_key='Month','Day'
                if month_key in values and day_key in values:
                    date(2001,int(str(values[month_key])),int(str(values[day_key])))
            if 'DURATION_DAYS' in values and (float(values['DURATION_DAYS']) < 0 or float(values['DURATION_DAYS']) != int(float(values['DURATION_DAYS']))):
                raise ValueError('Duration must be a nonnegative whole number')


def template(scripts):
    return json.loads((Path(scripts) / 'baseline-configuration.example.json').read_text(encoding='utf-8'))


def validate_settings(settings, defaults, prefix=''):
    if set(settings) != set(defaults):
        raise ValueError('Unknown or missing rule settings: ' + prefix)
    for key, expected in defaults.items():
        value = settings[key]
        if key == 'active' and isinstance(expected,bool) and isinstance(value,dict):
            if any(name not in RESERVOIRS or not isinstance(flag,bool) for name,flag in value.items()):
                raise ValueError('Invalid reservoir activation map')
        elif isinstance(expected,dict):
            if key == 'mode_by_reservoir':
                if any(name not in RESERVOIRS or mode not in ('FILL_ONLY','DRAFT_ONLY','BOTH') for name,mode in value.items()):
                    raise ValueError('Invalid FIRO reservoir mode')
            else:
                if not isinstance(value,dict): raise ValueError('Expected reservoir settings: ' + key)
                validate_settings(value,expected,prefix+key+'.')
        elif isinstance(expected,bool):
            if not isinstance(value,bool): raise ValueError('Expected Boolean: ' + key)
        elif isinstance(expected,(int,float)):
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
                raise ValueError('Expected finite number: ' + key)
            if isinstance(expected,int) and int(value)!=value: raise ValueError('Expected whole number: ' + key)
            if key.endswith('month') and not 1 <= value <= 12: raise ValueError('Invalid month: ' + key)
            if key.endswith('day') and not 1 <= value <= 31: raise ValueError('Invalid day: ' + key)
            if key == 'glide_days' and value <= 0: raise ValueError('Glide days must be positive')
            if (key.endswith('_cfs') or key.endswith('_ac_ft') or key.endswith('_days')) and value < 0:
                raise ValueError('Negative setting: ' + key)
        elif not isinstance(value,str) or not value.strip(): raise ValueError('Expected text: ' + key)
        if key == 'mode' and value not in ('FILL_ONLY','DRAFT_ONLY','BOTH'): raise ValueError('Invalid FIRO mode')
    if 'start_month' in settings and 'start_day' in settings:
        date(2001,int(settings['start_month']),int(settings['start_day']))
        date(2001,int(settings['end_month']),int(settings['end_day']))
    if settings.get('interpolate_gaps_up_to_days',0) > 365: raise ValueError('Interpolation gap exceeds one year')
    if 'high_flow_cfs' in settings and settings['low_flow_cfs'] > settings['high_flow_cfs']:
        raise ValueError('Low flow exceeds high flow')
    for name, low in settings.get('minimum_conservation_elevation_ft',{}).items():
        if low >= settings['maximum_conservation_elevation_ft'][name]: raise ValueError('Invalid conservation elevation range')


def resolve(config, scripts, watershed):
    defaults = template(scripts)
    if config.get('format') != defaults['format'] or config.get('schema_version') != 1 or not str(config.get('name','')).strip():
        raise ValueError('Invalid baseline configuration header')
    if set(config['rules']) != set(defaults['rules']):
        raise ValueError('The baseline configuration must contain all eleven rule groups')
    result, linked = copy.deepcopy(config), {}
    for key, rule in result['rules'].items():
        reference = defaults['rules'][key]
        validate_settings(rule['settings'],reference['settings'],key+'.')
        if set(rule['tables']) != set(reference['tables']): raise ValueError('Unknown or missing rule tables: ' + key)
        for name, table in rule['tables'].items():
            if table['mode'] not in ('inline','csv'): raise ValueError('Invalid table source')
            if table['mode'] == 'csv':
                path = Path(table['csv_path'])
                if not path.is_absolute(): path = Path(watershed) / path
                raw = path.read_bytes()
                columns, rows = read_csv(path)
                if digest_file(path) != hashlib.sha256(raw).hexdigest(): raise ValueError('Linked CSV changed while reading')
                table['columns'],table['rows'] = columns,rows
                linked[key+'-'+name+'.csv'] = raw
            validate_table(key,name,table,reference['tables'][name])
            table['mode'] = 'inline'
    return result, linked


def current_configuration(root, scripts):
    marker = Path(root)/'rts-baseline-config-active.json'
    if marker.exists():
        pointer=json.loads(marker.read_text());source=Path(root)/pointer['directory']/'resolved.json'
        if digest_file(source)!=pointer['resolved_sha256']: raise ValueError('Active configuration checksum mismatch')
        data=json.loads(source.read_text())
        saved=json.loads(source.with_name('configuration.json').read_text())
        for key, rule in saved['rules'].items():
            for name, table in rule['tables'].items():
                table['rows']=data['rules'][key]['tables'][name]['rows']
                table['columns']=data['rules'][key]['tables'][name]['columns']
        return saved
    # Read installed CSVs, not the example schedules. Current Con_Season defaults
    # have flat Hjson key/value lines; refuse more complex syntax rather than guess.
    result=template(scripts);watershed=Path(scripts).parent.parent
    values={}
    for filename in ('_default.txt','Con_Season.txt'):
        path=watershed/'scripts/alt_config'/filename
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            text=line.strip()
            if not text or text.startswith('#'): continue
            if ':' not in text: raise ValueError('Unsupported alt_config syntax; import a complete JSON configuration instead')
            key,value=text.split(':',1)
            values[key.strip()]=json.loads(value.strip())
    for alt_key,(rule,table_name) in TABLE_KEYS.items():
        table=result['rules'][rule]['tables'][table_name]
        path=Path(values.get(alt_key,table['csv_path']))
        if not path.is_absolute(): path=watershed/path
        table['columns'],table['rows']=read_csv(path)
        table['csv_path']=str(values.get(alt_key,table['csv_path']))
    result['rules']['draft_to_rc']['settings']['active']=values.get('draftToRCActive',True)
    for key,setting in [('irrmActive','active'),('irrmTargetElevs','target_elevation_ft')]:
        if key in values: result['rules']['irrm']['settings'][setting]=values[key]
    # Constants are sourced from the installed legacy implementations.
    import ast
    import sys
    sys.path.insert(0,str(Path(scripts).parent))
    from rts_baseline_runtime import CONSTANTS
    for module,key in MODULE_KEYS.items():
        path=watershed/'scripts/_rts_baseline_originals/externalRules'/(module+'.py')
        text=path.read_text()
        for setting,constant in CONSTANTS.items():
            if setting not in result['rules'][key]['settings']: continue
            match=re.search(r'^'+re.escape(constant)+r'\s*=\s*(.+)$',text,re.M)
            if match: result['rules'][key]['settings'][setting]=ast.literal_eval(match[1].split('#',1)[0].strip())
    return result


def apply_configuration(root, context, config, scripts):
    root=Path(root).resolve();scripts=Path(scripts).resolve();watershed=scripts.parent.parent
    resolved,linked=resolve(config,scripts,watershed)
    identity=uuid.uuid4().hex
    sets=root/'baseline-configurations/sets';sets.mkdir(parents=True,exist_ok=True)
    directory=sets/identity;directory.mkdir()
    (directory/'tables').mkdir();(directory/'linked-sources').mkdir()
    table_paths={};hashes={}
    for alt_key,(rule,name) in TABLE_KEYS.items():
        relative='tables/'+rule+'-'+name+'.csv';path=directory/relative
        table=resolved['rules'][rule]['tables'][name]
        with path.open('w',newline='',encoding='utf-8') as handle:
            writer=csv.writer(handle);writer.writerow(table['columns'])
            writer.writerows([['' if v is None else ('TRUE' if v else 'FALSE') if isinstance(v,bool) else v for v in row] for row in table['rows']])
        table_paths[alt_key]=relative;hashes[relative]=digest_file(path)
    for name,raw in linked.items(): (directory/'linked-sources'/name).write_bytes(raw)
    (directory/'scripts').mkdir()
    script_hashes={}
    for module in MODULE_KEYS:
        original=watershed/'scripts/_rts_baseline_originals/externalRules'/(module+'.py')
        saved=directory/'scripts'/(module+'.py')
        shutil.copy2(original,saved)
        script_hashes[module]=digest_file(saved)
        if digest_file(original)!=script_hashes[module]: raise ValueError('Script changed during snapshot: '+module)
    shutil.copy2(watershed/'scripts/rts_baseline_runtime.py',directory/'scripts/rts_baseline_runtime.py')
    resolved.update(table_paths=table_paths,table_sha256=hashes,script_sha256=script_hashes)
    atomic_json(directory/'resolved.json',resolved);atomic_json(directory/'configuration.json',config)
    pointer={'id':identity,'directory':str(directory.relative_to(root)), 'resolved_sha256':digest_file(directory/'resolved.json'),
             'name':config['name'],'context':context,'status':'applied-awaiting-unaugmented-compute'}
    atomic_json(directory/'manifest.json',pointer)
    atomic_json(root/'augmentation-archives/workflow-pending.json',{'mode':'baseline','baseline_configuration_id':identity})
    disable(root,identity)
    atomic_json(root/'rts-baseline-config-active.json',pointer)
    event(root,'baseline-configuration-applied',configuration_id=identity,name=config['name'])
    print('Applied baseline configuration:', config['name'],identity,flush=True)
    print('Augmentation disabled. Reopen and compute in RTS; check RTS baseline init messages.',flush=True)
    return pointer


def check_initialization(root, details):
    marker=Path(root)/'rts-baseline-config-active.json'
    if not marker.exists(): return None
    pointer=json.loads(marker.read_text());directory=Path(root)/pointer['directory']
    receipts=[json.loads(path.read_text()) for path in (directory/'initialization-receipts').glob('*.json')]
    seen={item['member'] for item in receipts if item['configuration_id']==pointer['id'] and item.get('resolved_sha256')==pointer['resolved_sha256']}
    missing=set(details['members']+details['synthetic_members'])-seen
    if missing: raise ValueError('Applied baseline configuration has no initialization receipts for members: '+str(sorted(missing))+'. Restart RTS after installing adapters, then recompute.')
    return pointer


def archive_configuration(root, destination, pointer):
    if pointer is None: return
    source=Path(root)/pointer['directory']
    target=Path(destination)/'baseline-configuration'
    shutil.copytree(source,target,ignore=shutil.ignore_patterns('initialization-receipts'))
    atomic_json(Path(destination)/'baseline-configuration.json',pointer)


def serve_editor(scripts, context=None):
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    import secrets
    import threading
    import webbrowser
    scripts=Path(scripts);root=Path(context['dss_path']).parent if context else None
    token=secrets.token_urlsafe(32)
    config=current_configuration(root,scripts) if root else template(scripts)
    page=(scripts/'baseline-editor.html').read_text(encoding='utf-8')
    start=page.index('<script id="example" type="application/json">')+len('<script id="example" type="application/json">');end=page.index('</script>',start)
    page=page[:start]+json.dumps(config).replace('</','<\\/')+page[end:]
    page=page.replace('Design mockup · No connection to RTS or model files', 'RTS baseline editor · Save and Apply are separate actions')
    page=page.replace('The RTS adapter is not implemented in this design mockup', 'Apply is available when this editor is launched from RTS')
    page=page.replace('This mockup supports editing and export only.', 'Apply is available when launched from the RTS workflow menu.')
    page=page.replace('the RTS adapter is not installed.', 'Apply validates operational settings and snapshots linked files.')
    if context:
        bridge="""<script>
const applyButton=document.querySelector('button[disabled]');applyButton.disabled=false;applyButton.title='Validate, snapshot and apply to the selected forecast';
const metadata=document.createElement('p');metadata.textContent=CONTEXT;metadata.className='notice';document.querySelector('.toolbar').after(metadata);
applyButton.onclick=async()=>{if(!confirm('Finish all computes and close the forecast in RTS before applying. Apply this set, disable augmentation, and require a new unaugmented compute?'))return;applyButton.disabled=true;try{let response=await fetch('/apply',{method:'POST',headers:{'Content-Type':'application/json','X-Editor-Token':TOKEN},body:JSON.stringify(config)});let data=await response.json();if(!response.ok)throw Error(data.error);status('Applied '+data.name+'. Augmentation is off. Reopen the forecast and compute in RTS; check RTS baseline init messages.');alert('Settings are staged. Reopen the forecast and compute in RTS. Then accept completed baseline results. Do not re-extract.')}catch(e){status('Apply failed: '+e.message);alert(e.message)}finally{applyButton.disabled=false}};
</script>""".replace('CONTEXT',json.dumps('Apply target: '+context['forecast_name']+' / '+context['run_name']+' / '+str(root))).replace('TOKEN',json.dumps(token))
        page=page.replace('</html>',bridge+'</html>')
    close_bridge="""<script>const closeEditor=document.createElement('button');closeEditor.textContent='Close Editor';document.querySelector('.toolbar').append(closeEditor);closeEditor.onclick=async()=>{await fetch('/close',{method:'POST',headers:{'X-Editor-Token':TOKEN}});document.body.textContent='Editor closed. You can close this browser tab.'};</script>""".replace('TOKEN',json.dumps(token))
    page=page.replace('</html>',close_bridge+'</html>')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_GET(self):
            if self.path != '/'+token: self.send_error(404);return
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.end_headers();self.wfile.write(page.encode('utf-8'))
        def do_POST(self):
            if self.path=='/close' and self.headers.get('X-Editor-Token')==token:
                self.send_response(200);self.end_headers();self.wfile.write(b'closed')
                threading.Thread(target=server.shutdown,daemon=True).start();return
            if not root or self.path!='/apply' or self.headers.get('X-Editor-Token')!=token:
                self.send_error(403);return
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0 < length < 8*1024*1024: raise ValueError('Invalid configuration size')
                result=apply_configuration(root,context,json.loads(self.rfile.read(length)),scripts);code=200
            except Exception as exc: result={'error':str(exc)};code=400
            self.send_response(code);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(json.dumps(result).encode())
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    url='http://127.0.0.1:'+str(server.server_port)+'/'+token
    print('Baseline editor opened. Use Close Editor when finished.',flush=True)
    webbrowser.open(url)
    try: server.serve_forever()
    finally: server.server_close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--editor',action='store_true');parser.add_argument('--context');parser.add_argument('--configuration')
    args=parser.parse_args();scripts=Path(__file__).resolve().parent
    context=json.loads(Path(args.context).read_text()) if args.context else None
    if args.editor: serve_editor(scripts,context)
    elif args.configuration and context:
        apply_configuration(Path(context['dss_path']).parent,context,json.loads(Path(args.configuration).read_text()),scripts)
    else: parser.error('Use --editor, or --context and --configuration')


if __name__=='__main__': main()
