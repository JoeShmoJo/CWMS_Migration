"""Offline HTML rendering for the headings/lists/tables/code used in this kit.

Standard library only; no browser scripts, CDN, server or Markdown dependency.
Markdown files remain the editable source of truth.
"""
import html
from pathlib import Path
import re

NAV=(('PROJECT_START_HERE','Start here'),('WORKFLOW_SOP','Operator SOP'),
     ('STANDALONE_WORKFLOW_REFERENCE','Standalone reference'),
     ('RTS_WORKFLOW_REFERENCE','RTS reference'),('STANDALONE_SAVED_RESULTS','Standalone saved runs'),('STANDALONE_POR_MODEL_CHECK','POR / Model Check'),('WORKFLOW_PACKAGE','Import / packaging'),('RTS_IMPORT_VALIDATION','Next: RTS validation'),
     ('RTS_DATA_IO','Data / archives'),('DIVERSION_POSTPROCESS','Diversions (optional)'))
STYLE='''body{font:17px/1.6 system-ui,sans-serif;color:#213346;margin:0;background:#f3f6fa}nav{background:#173d56;padding:14px;position:sticky;top:0}nav a{color:white;display:inline-block;margin:4px 12px}main{max-width:1100px;margin:auto;padding:28px;background:white}a{color:#0063a5}h1,h2,h3{line-height:1.25;scroll-margin-top:90px}h2{margin-top:2em;border-bottom:1px solid #cbd5df;padding-bottom:8px}pre{overflow:auto;padding:16px;background:#eef2f6;white-space:pre-wrap;overflow-wrap:anywhere}code{font-family:Consolas,monospace;font-size:.9em;background:#eef2f6}table{border-collapse:collapse;width:100%;font-size:.92em}th,td{border:1px solid #cad3dc;padding:9px;text-align:left;vertical-align:top;overflow-wrap:anywhere}th{background:#e5edf3}.table{overflow:auto}footer{margin-top:3em;color:#546579}@media print{nav{display:none}main{max-width:none;padding:0}body{background:white}pre{white-space:pre-wrap}a{color:inherit}}'''


def inline(value, sources):
    tokens=[]
    def save(markup):
        tokens.append(markup)
        return '\x00'+str(len(tokens)-1)+'\x00'
    value=re.sub(r'`([^`]+)`',lambda m:save('<code>'+html.escape(m[1])+'</code>'),value)
    def link(match):
        label,target=match[1],match[2]
        path,sep,anchor=target.partition('#')
        if path in sources:target=sources[path]+(sep+anchor if sep else '')
        elif path and not re.match(r'[a-zA-Z]+:',path) and not path.startswith('#'):
            target='../'+target
        if re.match(r'(?i)(javascript|data):',target):return label
        return save('<a href="'+html.escape(target,quote=True)+'">'+html.escape(label)+'</a>')
    value=re.sub(r'\[([^\]]+)\]\(([^)]+)\)',link,value)
    value=html.escape(value)
    value=re.sub(r'\*\*([^*]+)\*\*',r'<strong>\1</strong>',value)
    return re.sub('\x00(\\d+)\x00',lambda m:tokens[int(m[1])],value)


def render(text,sources):
    lines=text.splitlines();out=[];paragraph=[];list_kind=None;i=0;ids={}
    def flush():
        if paragraph:out.append('<p>'+inline(' '.join(paragraph),sources)+'</p>');paragraph[:]=[]
    def close_list():
        nonlocal list_kind
        if list_kind:out.append('</'+list_kind+'>');list_kind=None
    def cells(line):
        return re.split(r'\|(?=(?:[^`]*`[^`]*`)*[^`]*$)',line.strip().strip('|'))
    while i<len(lines):
        line=lines[i];i+=1
        if line.startswith('```'):
            flush();close_list();code=[]
            while i<len(lines) and not lines[i].startswith('```'):code.append(lines[i]);i+=1
            i+=1;out.append('<pre><code>'+html.escape('\n'.join(code))+'</code></pre>');continue
        if not line.strip():flush();close_list();continue
        heading=re.match(r'^(#{1,6})\s+(.+)',line)
        if heading:
            flush();close_list();level=len(heading[1]);slug=re.sub(r'[^\w -]','',heading[2].lower()).replace(' ','-');count=ids.get(slug,0);ids[slug]=count+1
            if count:slug+='-'+str(count)
            out.append('<h{0} id="{1}">{2}</h{0}>'.format(level,html.escape(slug),inline(heading[2],sources)));continue
        if i<len(lines) and '|' in line and re.match(r'^\s*\|?\s*:?-{3,}',lines[i]):
            flush();close_list();out.append('<div class="table"><table><thead><tr>'+''.join('<th>'+inline(c.strip(),sources)+'</th>' for c in cells(line))+'</tr></thead><tbody>');i+=1
            while i<len(lines) and lines[i].strip().startswith('|'):
                out.append('<tr>'+''.join('<td>'+inline(c.strip(),sources)+'</td>' for c in cells(lines[i]))+'</tr>');i+=1
            out.append('</tbody></table></div>');continue
        item=re.match(r'^\s*(?:([-*])|\d+\.)\s+(.+)',line)
        if item:
            flush();kind='ul' if item[1] else 'ol'
            if kind!=list_kind:
                close_list()
                start=' start="'+re.search(r'\d+',line)[0]+'"' if kind=='ol' else ''
                out.append('<'+kind+start+'>');list_kind=kind
            continuation=[item[2]]
            while i<len(lines) and lines[i].startswith('   ') and not re.match(r'^\s*(?:[-*]|\d+\.)\s+',lines[i]):continuation.append(lines[i].strip());i+=1
            out.append('<li>'+inline(' '.join(continuation),sources)+'</li>');continue
        close_list();paragraph.append(line.strip())
    flush();close_list();return '\n'.join(out)


def build(directory):
    directory=Path(directory);output=directory/'documentation';output.mkdir(exist_ok=True)
    docs=sorted(directory.glob('*.md'))
    optional=directory/'optional-diversion-postprocess/README.md'
    if optional.is_file():docs.append(optional)
    sources={p.relative_to(directory).as_posix():p.relative_to(directory).with_suffix('.html').as_posix().replace('/','-') for p in docs}
    navigation='<nav>'+''.join('<a href="'+name+'.html">'+label+'</a>' for name,label in NAV)+'</nav>'
    for doc in docs:
        text=doc.read_text(encoding='utf-8');title=next((line.lstrip('# ') for line in text.splitlines() if line.startswith('# ')),doc.stem)
        page='<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(title)+'</title><style>'+STYLE+'</style><body>'+navigation+'<main>'+render(text,sources)+'<footer>Offline watershed documentation · <a href="../'+doc.relative_to(directory).as_posix()+'">Markdown source</a> · Use browser Print to save as PDF.</footer></main></body></html>'
        (output/sources[doc.relative_to(directory).as_posix()]).write_text(page,encoding='utf-8')
    return output
