"""Create a separate, experimental ResSim 4.1.0 installation. Never patch source."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import shutil
import struct
import zipfile

EXPECTED_APP_SHA256 = '6b18183e72d236940bf780655c816eca4ccc6939766b4e676446431db8359c3d'
HELPER = 'cwms/diagnostics/IsolatedCompilerInterpreter'
TARGET = 'hec/rss/model/z.class'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def patch_class(data):
    """Append constant-pool entries; change one NEW and its constructor only.

    Code length, branch offsets, exception ranges and stack maps stay unchanged.
    Exact source JAR is independently pinned by the installation builder.
    """
    def u2(pos): return struct.unpack_from('>H', data, pos)[0]
    def u4(pos): return struct.unpack_from('>I', data, pos)[0]
    if data[:4] != b'\xca\xfe\xba\xbe':
        raise ValueError('Not a Java class')
    count = u2(8)
    cp = [None] * count
    pos = 10
    i = 1
    while i < count:
        tag = data[pos]; pos += 1
        if tag == 1:
            size = u2(pos); pos += 2
            cp[i] = (tag, data[pos:pos+size].decode('utf-8')); pos += size
        elif tag in (7, 8, 16, 19, 20):
            cp[i] = (tag, u2(pos)); pos += 2
        elif tag in (9, 10, 11, 12, 17, 18):
            cp[i] = (tag, u2(pos), u2(pos+2)); pos += 4
        elif tag in (3, 4): pos += 4
        elif tag in (5, 6): pos += 8; i += 1
        elif tag == 15: pos += 3
        else: raise ValueError('Unsupported constant-pool tag: '+str(tag))
        i += 1
    cp_end = pos
    text = lambda idx: cp[idx][1]
    classes = [i for i, item in enumerate(cp) if item and item[0] == 7
               and text(item[1]) == 'org/python/util/PythonInterpreter']
    if len(classes) != 1: raise ValueError('Interpreter class is ambiguous')
    cls = classes[0]
    constructors = [i for i, item in enumerate(cp) if item and item[0] == 10
                    and item[1] == cls and text(cp[item[2]][1]) == '<init>'
                    and text(cp[item[2]][2]) == '()V']
    if len(constructors) != 1: raise ValueError('Constructor is ambiguous')
    ctor = constructors[0]
    nat = cp[ctor][2]
    # superclass, interfaces, then fields.
    pos += 6
    interfaces = u2(pos); pos += 2 + interfaces*2
    def skip_member(pos):
        attrs = u2(pos+6); pos += 8
        for _ in range(attrs): pos += 6 + u4(pos+2)
        return pos
    fields = u2(pos); pos += 2
    for _ in range(fields): pos = skip_member(pos)
    methods = u2(pos); pos += 2
    candidate = None
    descriptor = '(Ljava/lang/String;Ljava/lang/String;)Lorg/python/core/PyCode;'
    for _ in range(methods):
        name, desc, attrs = u2(pos+2), u2(pos+4), u2(pos+6)
        pos += 8
        for _ in range(attrs):
            attr_name, size = u2(pos), u4(pos+2)
            start = pos+6
            if text(name) == 'a' and text(desc) == descriptor and text(attr_name) == 'Code':
                if candidate: raise ValueError('Multiple compiler Code attributes')
                candidate = (start+8, u4(start+4))
            pos = start+size
    if candidate is None: raise ValueError('Compiler method not found')
    start, size = candidate
    old = b'\xbb'+struct.pack('>H', cls)+b'\x59\xb7'+struct.pack('>H', ctor)
    code = data[start:start+size]
    if code.count(old) != 1: raise ValueError('Expected exactly one compiler allocation')
    # Append UTF8, Class and Methodref entries; reuse the original <init>()V NAT.
    name = HELPER.encode('ascii')
    extra = b'\x01'+struct.pack('>H',len(name))+name
    extra += b'\x07'+struct.pack('>H',count)
    extra += b'\x0a'+struct.pack('>HH',count+1,nat)
    new = b'\xbb'+struct.pack('>H',count+1)+b'\x59\xb7'+struct.pack('>H',count+2)
    body = bytearray(data[cp_end:])
    offset = start-cp_end+code.index(old)
    body[offset:offset+len(old)] = new
    return data[:8]+struct.pack('>H',count+3)+data[10:cp_end]+extra+body


def build_patched_jar(source, destination, helper):
    original = source.read_bytes()
    if sha(original) != EXPECTED_APP_SHA256:
        raise ValueError('Unsupported application JAR; SHA-256 differs from inspected 4.1.0')
    with zipfile.ZipFile(source) as z, zipfile.ZipFile(helper) as h:
        if any(n.upper().startswith('META-INF/') and n.upper().endswith(('.SF','.RSA','.DSA','.EC')) for n in z.namelist()):
            raise ValueError('Signed JAR; refusing to invalidate signature')
        name = HELPER+'.class'
        if name in z.namelist(): raise ValueError('Helper already present')
        helper_names = h.namelist()
        if name not in helper_names or not all(n == name or (n.startswith(HELPER+'$') and n.endswith('.class')) for n in helper_names):
            raise ValueError('Unexpected helper bundle contents')
        if any(n in z.namelist() for n in helper_names): raise ValueError('Helper already present')
        helper_bytes = {n: h.read(n) for n in helper_names}
        changed = patch_class(z.read(TARGET))
        with zipfile.ZipFile(destination, 'w') as out:
            for entry in z.infolist():
                out.writestr(entry, changed if entry.filename == TARGET else z.read(entry.filename))
            for helper_name, contents in helper_bytes.items():
                out.writestr(helper_name, contents)
    return sha(original), sha(destination.read_bytes())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installation', required=True, type=Path)
    parser.add_argument('--destination', required=True, type=Path)
    parser.add_argument('--threads', type=int, help='Set the copied standalone launcher worker limit')
    args = parser.parse_args()
    source = args.installation.resolve()
    dest = args.destination.resolve()
    app = source/'jar/ResSimApp-4.1.0.jar'
    if dest.exists() or dest == source or source in dest.parents:
        raise ValueError('Destination must be a new directory outside the source installation')
    if sha(app.read_bytes()) != EXPECTED_APP_SHA256:
        raise ValueError('Source JAR differs from inspected standalone 4.1.0; nothing copied')
    launcher = None
    launcher_text = None
    if args.threads is not None:
        if not 1 <= args.threads <= 32: raise ValueError('Threads must be between 1 and 32')
        candidates = []
        for config in source.glob('*.config'):
            content = config.read_bytes().decode('latin-1')
            if re.search(r'^\s*mainclass\s+hec\.rss\.client\.RSS\s*$', content, re.M):
                candidates.append((config, content))
        if len(candidates) != 1: raise ValueError('Cannot uniquely identify standalone launcher .config; nothing copied')
        launcher, launcher_text = candidates[0]
    helper = Path(__file__).with_name('isolated-compiler-helper.jar')
    if not helper.is_file(): raise ValueError('Helper JAR missing')
    shutil.copytree(source, dest)
    target = dest/'jar/ResSimApp-4.1.0.jar'
    backup = target.with_suffix('.jar.original')
    shutil.copy2(target, backup)
    temporary = target.with_suffix('.jar.pending')
    hashes = build_patched_jar(backup, temporary, helper)
    temporary.replace(target)
    if launcher is not None:
        copied_config = dest/launcher.relative_to(source)
        setting = 'vmparam -DResSim.ComputeThreadCount='+str(args.threads)
        content = re.sub(r'^\s*vmparam\s+-DResSim\.ComputeThreadCount=[^\r\n]*', '', launcher_text, flags=re.M)
        content = content.rstrip()+'\r\n\r\n# Experimental V2 worker limit\r\n'+setting+'\r\n'
        copied_config.write_bytes(content.encode('latin-1'))
    marker = {'experimental': True, 'compiler_isolation_version': 2, 'source': str(source), 'destination': str(dest),
              'original_sha256': hashes[0], 'patched_sha256': hashes[1],
              'change': 'Temporary script compiler only: per-worker private cached Jython state; fresh compiler flags and caller restoration',
              'threads': args.threads, 'compute_started': False, 'model_files_changed': False}
    (dest/'compiler-isolation-test.json').write_text(json.dumps(marker, indent=2))
    if sha(app.read_bytes()) != EXPECTED_APP_SHA256: raise RuntimeError('Source integrity check failed')
    print('PREPARED ONLY (compiler isolation V2):', dest)
    if args.threads is not None: print('Copied launcher thread limit:', args.threads)
    print('Original installation unchanged. No compute started or model files changed.')
    print('Use the copied ResSim executable directly, with a separate test watershed.')
    print('If preparation fails, discard the incomplete destination; do not launch it.')


if __name__ == '__main__':
    main()
