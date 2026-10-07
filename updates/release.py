"""Bounded signed release data. No imported or executed downloaded code."""
import hashlib
import gzip
import io
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tarfile
import tempfile
from datetime import datetime

PRODUCT = 'heartchy'
NAMESPACE = 'heartchy-release-v1'
CAPABILITIES = ['core-json-v1', 'core-toml-v1', 'core-lua-prefix-v1', 'core-journal-v1']
LIMIT = 16 * 1024 * 1024
MAX_FILES = 100
ENV = {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C.UTF-8', 'HOME': '/nonexistent'}

class Error(ValueError):
    pass

def need(ok, message):
    if not ok:
        raise Error(message)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)+'\n').encode()

def parse(data):
    def unique(pairs):
        out = {}
        for k,v in pairs:
            need(k not in out, 'duplicate JSON key')
            out[k] = v
        return out
    try:
        return json.loads(data, object_pairs_hook=unique, parse_constant=lambda v: need(False, 'invalid JSON number'))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise Error('invalid JSON: '+str(exc)) from exc

def safe_path(raw):
    p = Path(raw).absolute()
    need('..' not in Path(raw).parts and '\\' not in str(raw), 'path traversal')
    for parent in (*reversed(p.parents), p):
        need(not parent.is_symlink(), 'symlink in path: '+str(parent))
    return p

def read(path, limit=LIMIT):
    p = safe_path(path)
    fd = os.open(p, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as stream:
        info = os.fstat(stream.fileno())
        need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= limit, 'unsafe/oversized file')
        data = stream.read(limit+1)
    need(len(data)<=limit, 'file exceeds limit')
    return data

def write_new(path, data, mode=0o600):
    p=safe_path(path)
    p.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    safe_path(p.parent)
    fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    with os.fdopen(fd,'wb') as stream:
        stream.write(data);stream.flush();os.fsync(stream.fileno())

def text(value, limit=240):
    need(isinstance(value,str) and 0<len(value)<=limit and value.isprintable(), 'unsafe presentation text')
    need(not any(ord(c) in range(0x202a,0x202f) or ord(c) in range(0x2066,0x206a) for c in value), 'bidi controls forbidden')
    return value

def version(value):
    need(isinstance(value,str), 'invalid version')
    m=re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-test\.([1-9][0-9]*))?',value)
    need(m is not None, 'unsupported version')
    return tuple(int(x) for x in m.groups()[:3])+(int(m[4]) if m[4] else 10**9,)

def trust_file(path):
    obj=parse(read(path,10000))
    need(isinstance(obj,dict) and set(obj)=={'schema','kind','repository','public_key'},'invalid trust root')
    need(type(obj['schema']) is int and obj['schema']==1 and obj['kind'] in ('heartchy-trust','heartchy-lab-trust'),'unsupported trust root')
    need(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*/[A-Za-z0-9][A-Za-z0-9_.-]*',obj['repository']) is not None,'invalid repository')
    need(re.fullmatch(r'ssh-ed25519 [A-Za-z0-9+/]+={0,3}',obj['public_key']) is not None,'expected authorized Ed25519 public key only')
    return obj

def verify_signature(raw, signature, trust):
    need(len(raw)<=200000 and len(signature)<=4096,'signature/metadata too large')
    with tempfile.TemporaryDirectory(prefix='heartchy-verify-') as temp:
        base=Path(temp)
        write_new(base/'signers',('heartchy '+trust['public_key']+'\n').encode())
        write_new(base/'signature',signature)
        result=subprocess.run(['/usr/bin/ssh-keygen','-Y','verify','-f',str(base/'signers'),'-I','heartchy','-n',NAMESPACE,'-s',str(base/'signature')],input=raw,capture_output=True,env=ENV,timeout=10)
        need(result.returncode==0,'SIGNATURE_INVALID: unauthorized key or altered metadata')

RUNTIME_FILES = {
    'bin/heartchy-update','bin/heartchy-updates-mockup',
    'tools/heartchy-dev','tools/heartchy-plan.py','tools/heartchy-lua-plan.py','tools/heartchy-target.py','tools/heartchy-apply.py','tools/lua-contract.lua',
    'updates/release.py','updates/network.py','updates/engine.py','updates/tui.py','updates/cli.py',
    'mockups/updates.py','mockups/animation_preview.py','mockups/updates.json',
    'mockups/assets/omarchy.txt','mockups/assets/heartchy.txt','mockups/assets/provenance.json',
    'core/hypr/heartchy.lua','core/shell/cristal.toml','core/shell/settings-intent.json','core/manifest.json',
    'docs/provenance.json','docs/upstream-evidence.json','docs/architecture.md','docs/upstream.md','NOTICE.md',
    'test/fixtures/omarchy/LICENSE','inventory.json','client.json',
}

def metadata(raw, trust):
    m=parse(raw)
    need(isinstance(m,dict) and set(m)=={'schema','product','repository','version','channel','source_commit','prepared_at','client_contract','capabilities','compatibility','editorial','archive','files'},'unsupported release schema fields')
    need(type(m['schema']) is int and m['schema']==1 and type(m['client_contract']) is int and m['client_contract']==1,'INCOMPATIBLE client/schema')
    need(m['product']==PRODUCT and m['repository']==trust['repository'],'wrong product/repository')
    version(m['version'])
    need(m['channel'] in ('test','stable') and (('-test.' in m['version'])==(m['channel']=='test')),'version/channel mismatch')
    need(re.fullmatch(r'[0-9a-f]{40}',m['source_commit']) is not None,'full source commit required')
    need(isinstance(m['prepared_at'],str) and datetime.fromisoformat(m['prepared_at']).tzinfo is not None,'preparation time requires timezone')
    need(m['capabilities']==CAPABILITIES,'INCOMPATIBLE capabilities')
    c=m['compatibility']
    need(isinstance(c,dict) and set(c)=={'contracts','tested','dependencies','limits'},'compatibility required')
    need(c['contracts']=='omarchy-core-4.0.4-lua-v1','INCOMPATIBLE Core contract')
    for group in ('tested','dependencies','limits'):
        need(isinstance(c[group],list) and len(c[group])<=12,'invalid compatibility list')
        for line in c[group]:text(line)
    e=m['editorial'];groups=('changes','components','fixes','notes','apps')
    need(isinstance(e,dict) and set(e)=={'name','summary','card','description',*groups},'invalid editorial fields')
    text(e['name'],64);text(e['summary']);text(e['description'],800)
    need(e['card'] in ('major','minor'),'invalid card type')
    for group in groups:
        need(isinstance(e[group],list) and len(e[group])<=8,'invalid report list')
        for line in e[group]:text(line)
    need(not e['apps'],'Core does not install apps')
    a=m['archive'];need(isinstance(a,dict) and set(a)=={'name','bytes','sha256'},'invalid archive')
    need(a['name']=='heartchy-'+m['version']+'.tar.gz' and type(a['bytes']) is int and 0<a['bytes']<=LIMIT,'invalid archive name/size')
    need(isinstance(a['sha256'],str) and re.fullmatch('[0-9a-f]{64}',a['sha256']),'invalid archive hash')
    need(isinstance(m['files'],list) and len(m['files'])==len(RUNTIME_FILES)<=MAX_FILES,'invalid file inventory')
    names=set();total=0
    for f in m['files']:
        need(isinstance(f,dict) and set(f)=={'path','bytes','sha256','mode'},'invalid file record')
        need(f['path'] in RUNTIME_FILES and f['path'] not in names,'unexpected/duplicate resource')
        need(type(f['bytes']) is int and 0<=f['bytes']<=2_000_000 and f['mode'] in ('0644','0755'),'invalid resource size/mode')
        need(isinstance(f['sha256'],str) and re.fullmatch('[0-9a-f]{64}',f['sha256']),'invalid resource hash')
        names.add(f['path']);total+=f['bytes']
    need(total<=LIMIT,'uncompressed limit')
    return m

def verify_delivery(directory,trust):
    d=safe_path(directory)
    raw=read(d/'release.json',200000);sig=read(d/'release.json.sig',4096)
    verify_signature(raw,sig,trust);m=metadata(raw,trust)
    archive=read(d/m['archive']['name'])
    need(len(archive)==m['archive']['bytes'] and sha(archive)==m['archive']['sha256'],'archive hash/size mismatch')
    inventory={f['path']:f for f in m['files']};content={}
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(archive)) as compressed:
            plain = compressed.read(LIMIT + MAX_FILES * 2048 + 1)
        need(len(plain) <= LIMIT + MAX_FILES * 2048, 'decompression limit')
        with tarfile.open(fileobj=io.BytesIO(plain),mode='r:') as tar:
            for entry in tar:
                need(entry.name in inventory and entry.name not in content and entry.isfile() and not entry.pax_headers,'hostile/duplicate archive entry')
                f=inventory[entry.name]
                need(entry.size==f['bytes'] and entry.mode==int(f['mode'],8),'archive entry size/mode mismatch')
                stream=tar.extractfile(entry);data=stream.read(f['bytes']+1)
                need(len(data)==f['bytes'] and sha(data)==f['sha256'],'resource hash mismatch')
                content[entry.name]=data
                need(len(content)<=MAX_FILES,'too many archive members')
    except (tarfile.TarError,EOFError) as exc:raise Error('invalid archive') from exc
    need(set(content)==set(inventory),'incomplete archive')
    need(parse(content['client.json']) == {'schema':1,'version':m['version'],'source_commit':m['source_commit'],'contract':1}, 'client/release identity mismatch')
    return m,content

def extract(directory,output,trust):
    m,content=verify_delivery(directory,trust)
    out=safe_path(output);out.mkdir(mode=0o700)
    for f in m['files']:write_new(out/f['path'],content[f['path']],int(f['mode'],8))
    return m
