"""Updater tests; mixed into the existing isolated suite, never host execution."""
import contextlib
import hashlib
import http.server
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tarfile
import threading
import time
import unittest
from unittest.mock import patch

ENV={'PATH':'/usr/bin:/bin','LC_ALL':'C.UTF-8','TMPDIR':'/sandbox','HOME':'/nonexistent'}

def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def contents(p):return {str(f.relative_to(p)):f.read_bytes() for f in p.rglob('*') if f.is_file() and not f.is_symlink()}

class UpdatesMixin:
    def update_cli(self,*args,root=None,timeout=30):
        return subprocess.run([str((root or self.repo)/'bin/heartchy-update'),*map(str,args)],env=ENV,cwd=self.area,capture_output=True,text=True,timeout=timeout)

    def git_lab(self,*args):
        r=subprocess.run(['/usr/bin/git',*args],cwd=self.repo,env=ENV,capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr);return r.stdout.strip()

    def lab_release(self):
        self.key=self.area/'signing';self.trust=self.area/'trust.json'
        subprocess.run(['/usr/bin/ssh-keygen','-q','-t','ed25519','-N','','-f',str(self.key)],env=ENV,check=True,capture_output=True)
        key=' '.join(self.key.with_suffix('.pub').read_text().split()[:2])
        self.trust.write_text(json.dumps({'schema':1,'kind':'heartchy-lab-trust','repository':'laboratory/heartchy','public_key':key}))
        self.git_lab('init','-q','-b','main');self.git_lab('add','--all')
        self.git_lab('-c','user.name=Isolated Test','-c','user.email=test@example.invalid','commit','-qm','Test fixture source')
        self.a=self.build_release('0.1.0-test.1')
        return self.a

    def build_release(self,v):
        out=self.area/v
        r=subprocess.run([str(self.repo/'tools/heartchy-release'),'prepare','--version',v,'--repository','laboratory/heartchy','--trust',str(self.trust),'--signing-key',str(self.key),'--editorial','releases/first-test.json','--output',str(out)],env=ENV,capture_output=True,text=True,timeout=20)
        self.assertEqual(r.returncode,0,r.stderr);return out

    def release_b(self):
        p=self.repo/'core/hypr/heartchy.lua';p.write_bytes(b'-- Cumulative laboratory revision B; same visual values.\n'+p.read_bytes())
        m=self.repo/'core/manifest.json';obj=json.loads(m.read_text());obj['resources'][0]['sha256']=digest(p);m.write_text(json.dumps(obj,indent=2)+'\n')
        self.git_lab('add','core');self.git_lab('-c','user.name=Isolated Test','-c','user.email=test@example.invalid','commit','-qm','Laboratory cumulative B')
        return self.build_release('0.1.0-test.2')

    def update_target(self):
        # Exact stock loaders already attributed in planner fixtures, copied
        # without desktop IPC or any host personal data.
        fixture=self.repo/'test/fixtures/planner/lua-first'
        root=self.area/'recipient';config=root/'.config';config.mkdir(parents=True)
        shutil.copytree(fixture/'config/hypr',config/'hypr')
        (config/'omarchy').mkdir();shutil.copyfile(self.repo/'test/fixtures/updates-stock/shell.json',config/'omarchy/shell.json')
        shutil.copyfile(self.repo/'test/fixtures/updates-stock/looknfeel.lua',config/'hypr/looknfeel.lua')
        # Stock has no personal shell.toml; the first apply must create it.
        stock=self.area/'stock';(stock/'config/hypr').mkdir(parents=True);(stock/'default/hypr').mkdir(parents=True)
        shutil.copyfile(fixture/'config/hypr/hyprland.lua',stock/'config/hypr/hyprland.lua')
        shutil.copyfile(self.repo/'test/fixtures/omarchy/bootstrap.lua',stock/'default/hypr/bootstrap.lua')
        shutil.copyfile(self.repo/'test/fixtures/omarchy/defaults.lua',stock/'default/hypr/omarchy.lua')
        marker=json.loads((fixture/'target.json').read_text());marker.update(kind='heartchy-local-target',config_root=str(config),shadow_root=str(root/'.local/state'),stock_root=str(stock))
        self.target=self.area/'target.json';self.target.write_text(json.dumps(marker))
        self.state=self.area/'state';self.config=config
        return config

    def up_plan(self,delivery,*options):
        path=self.area/('plan-'+str(time.monotonic_ns())+'.json')
        r=self.update_cli('plan','--delivery',delivery,'--trust',self.trust,'--target',self.target,'--state',self.state,'--output',path,*options)
        self.assertIn(r.returncode,(0,3),r.stderr)
        return path,json.loads(r.stdout),json.loads(path.read_text())

    def up_apply(self,delivery,p):
        return self.update_cli('apply','--delivery',delivery,'--trust',self.trust,'--target',self.target,'--state',self.state,'--plan',p,'--approve',digest(p))

    def up_effect(self,command,*extra):
        args=[command,'--target',self.target,'--state',self.state]
        if command in ('rollback','recover'):args+=['--approve',command]
        return self.update_cli(*args,*extra)

    def sign_metadata(self,delivery,m):
        (delivery/'release.json').write_text(json.dumps(m,sort_keys=True,indent=2)+'\n')
        (delivery/'release.json.sig').unlink()
        subprocess.run(['/usr/bin/ssh-keygen','-Y','sign','-f',str(self.key),'-n','heartchy-release-v1',str(delivery/'release.json')],check=True,capture_output=True,env=ENV)

    def test_updater_first_writes_update_noop_and_rollback_portable(self):
        self.lab_release();self.update_target();before=contents(self.config)
        p,summary,plan=self.up_plan(self.a,'--prefer-heartchy','shell_intent:bar.transparent')
        self.assertFalse(summary['blocked'],json.dumps(plan));self.assertFalse(summary['pending_conflicts'])
        self.assertEqual({r['resource'] for r in plan['core_plan']['entries']},{'hypr_module','hypr_connection','shell_intent','shell_tokens'})
        self.expect_ok(self.up_apply(self.a,p))
        self.assertNotEqual(contents(self.config),before)
        self.assertTrue(json.loads((self.config/'omarchy/shell.json').read_text())['bar']['transparent'])
        self.assertIn(b'normal-fill-alpha = 0.035',(self.config/'omarchy/shell.toml').read_bytes())
        b=self.release_b();p,_,_=self.up_plan(b);self.expect_ok(self.up_apply(b,p))
        self.assertTrue((self.config/'hypr/heartchy.lua').read_bytes().startswith(b'-- Cumulative'))
        applied=contents(self.config);p,_,_=self.up_plan(b);r=self.up_apply(b,p);self.expect_ok(r)
        self.assertEqual(json.loads(r.stdout)['apply']['result'],'NO_CHANGE');self.assertEqual(contents(self.config),applied)
        self.assertEqual((self.config/'hypr/looknfeel.lua').read_text().count('-- BEGIN HEARTCHY'),1)
        self.expect_ok(self.up_effect('validate'))
        extracted=self.area/'runtime';self.expect_ok(self.update_cli('extract','--delivery',b,'--trust',self.trust,'--output',extracted))
        self.expect_ok(self.update_cli('validate','--target',self.target,'--state',self.state,root=extracted))
        self.expect_ok(self.update_cli('rollback','--target',self.target,'--state',self.state,'--approve','rollback',root=extracted))
        # JSON may be normalized by owned-key editing; semantic foreign data
        # and exact Lua/TOML bytes are preserved, not a whole-file backup restore.
        self.assertEqual(json.loads((self.config/'omarchy/shell.json').read_text()),json.loads(before['omarchy/shell.json']))
        self.assertFalse((self.config/'omarchy/shell.toml').exists())
        self.assertEqual((self.config/'hypr/looknfeel.lua').read_bytes(),before['hypr/looknfeel.lua'])
        self.assertFalse((self.config/'hypr/heartchy.lua').exists())

    def test_updater_preferences_stale_plan_and_post_apply_conflict(self):
        self.lab_release();self.update_target()
        p=self.config/'omarchy/shell.toml';p.write_text('[menu]\nborder-alpha = 0.9 # personal\n[omafiles]\nglass = true\n')
        plan,_,obj=self.up_plan(self.a)
        row=next(r for r in obj['core_plan']['entries'] if r['key']=='menu.border-alpha')
        self.assertEqual(row['decision'],'LOCAL_PRESERVED')
        p.write_text(p.read_text()+'# later\n');self.expect_bad(self.up_apply(self.a,plan),'STALE_PLAN')
        plan,_,_=self.up_plan(self.a,'--prefer-heartchy','shell_tokens:menu.border-alpha');self.expect_ok(self.up_apply(self.a,plan))
        self.assertIn('glass = true',p.read_text());self.assertIn('# later',p.read_text())
        p.write_text(p.read_text().replace('border-alpha = 0.6','border-alpha = 0.8'))
        result=self.up_effect('rollback');self.assertEqual(result.returncode,3,result.stderr)
        self.assertIn('border-alpha = 0.8',p.read_text())
        self.assertIn('glass = true',p.read_text())
        self.assertEqual(json.loads((self.state/'installed.json').read_text())['result'],'PARTIAL_ROLLBACK')
        r=self.driver("from engine import Session; assert Session(sys.argv[2],sys.argv[3]).installed() is None",self.target,self.state)
        self.assertEqual(r.returncode,0,r.stderr)

    def test_updater_signature_identity_archive_and_presentation_attacks(self):
        self.lab_release()
        for field,value in [('product','other'),('channel','stable'),('client_contract',99)]:
            d=self.area/field;shutil.copytree(self.a,d);m=json.loads((d/'release.json').read_text());m[field]=value;self.sign_metadata(d,m)
            self.assertNotEqual(self.update_cli('verify','--delivery',d,'--trust',self.trust).returncode,0)
        for i,bad in enumerate(('evil\x1b]52;c;secret\x07','evil\u202e')):
            d=self.area/('ansi'+str(i));shutil.copytree(self.a,d);m=json.loads((d/'release.json').read_text());m['editorial']['name']=bad;self.sign_metadata(d,m)
            self.assertNotEqual(self.update_cli('verify','--delivery',d,'--trust',self.trust).returncode,0)
        d=self.area/'altered';shutil.copytree(self.a,d);p=d/'release.json';p.write_bytes(p.read_bytes()+b' ')
        self.expect_bad(self.update_cli('verify','--delivery',d,'--trust',self.trust),'SIGNATURE_INVALID')
        d=self.area/'truncated';shutil.copytree(self.a,d);m=json.loads((d/'release.json').read_text());a=d/m['archive']['name'];a.write_bytes(a.read_bytes()[:-2])
        self.expect_bad(self.update_cli('verify','--delivery',d,'--trust',self.trust),'hash/size')
        # Even with a valid laboratory signature, extraction rejects an extra link.
        d=self.area/'hostile';shutil.copytree(self.a,d);m=json.loads((d/'release.json').read_text());a=d/m['archive']['name']
        with tarfile.open(a,'w:gz') as tar:
            link=tarfile.TarInfo('../escape');link.type=tarfile.SYMTYPE;link.linkname='/etc/passwd';tar.addfile(link)
        m['archive'].update(bytes=a.stat().st_size,sha256=digest(a));self.sign_metadata(d,m)
        self.expect_bad(self.update_cli('extract','--delivery',d,'--trust',self.trust,'--output',self.area/'bad-extract'),'hostile')
        self.assertFalse((self.area/'bad-extract').exists())

    @contextlib.contextmanager
    def http_lab(self,deliveries,*,rate=False,truncate=False,paginate=False):
        requests=[];repo='laboratory/heartchy'
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self,*a):pass
            def do_GET(self):
                requests.append(self.path)
                if rate:self.send_response(429);self.end_headers();return
                if self.path.startswith('/repos/'):
                    rows=[{'tag_name':'v'+json.loads((d/'release.json').read_text())['version'],'prerelease':True,'draft':False,'published_at':'2026-10-07T12:00:00Z'} for d in deliveries]
                    if paginate: rows = ([{'draft':True}]*100 if self.path.endswith('&page=1') else rows)
                    data=json.dumps(rows).encode()
                else:
                    try:
                        tag,name=self.path.split('/releases/download/')[1].split('/')
                        d=next(d for d in deliveries if tag=='v'+json.loads((d/'release.json').read_text())['version'])
                        data=(d/name).read_bytes()
                    except (IndexError,StopIteration,FileNotFoundError,ValueError):self.send_response(404);self.end_headers();return
                self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data[:-3] if truncate else data)
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:yield 'http://127.0.0.1:'+str(server.server_port),requests
        finally:server.shutdown();server.server_close();thread.join()

    def test_updater_http_download_cache_channels_and_rate_limit(self):
        self.lab_release();b=self.release_b()
        with self.http_lab([self.a,b]) as (url,requests):
            base=['--trust',self.trust,'--channel','test','--lab-http',url]
            cache=self.area/'catalog.json';r=self.update_cli('catalog',*base,'--cache-output',cache);self.expect_ok(r)
            self.assertEqual([r['metadata']['version'] for r in json.loads(r.stdout)['releases']],['0.1.0-test.2','0.1.0-test.1'])
            self.assertIn('per_page=100&page=1',requests[0])
            d=self.area/'download';self.expect_ok(self.update_cli('fetch',*base,'--version','0.1.0-test.2','--output',d))
            self.assertEqual(contents(d),contents(b))
            r=self.update_cli('catalog','--trust',self.trust,'--channel','stable','--lab-http',url);self.expect_ok(r);self.assertEqual(json.loads(r.stdout)['releases'],[])
        self.expect_ok(self.update_cli('catalog',*base,'--cached',cache))
        self.expect_bad(self.update_cli('catalog',*base),'NETWORK_UNAVAILABLE')
        with self.http_lab([self.a],rate=True) as (url,_):
            self.expect_bad(self.update_cli('catalog','--trust',self.trust,'--channel','test','--lab-http',url),'RATE_LIMIT')
        with self.http_lab([self.a],truncate=True) as (url,_):
            r=self.update_cli('fetch','--trust',self.trust,'--channel','test','--lab-http',url,'--version','0.1.0-test.1','--output',self.area/'truncated-download')
            self.assertNotEqual(r.returncode,0);self.assertFalse((self.area/'truncated-download').exists())

    def driver(self,code,*args):
        prefix="import sys; sys.dont_write_bytecode=True; sys.path.insert(0,sys.argv[1]+'/updates'); "
        return subprocess.run(['/usr/bin/python3','-I','-B','-c',prefix+code,str(self.repo),*map(str,args)],env=ENV,cwd=self.area,capture_output=True,text=True,timeout=25)

    def test_updater_recovery_after_interrupted_core_and_metadata_residue(self):
        self.lab_release();self.update_target();before=contents(self.config);p,_,_=self.up_plan(self.a)
        code='''
from engine import Session
from release import parse,read,sha,trust_file
s=Session(sys.argv[2],sys.argv[3]);old=s.operations['Operations']
class Fault(old):
 def __init__(self,*a,**k):
  super().__init__(*a,**k)
  def fail(phase,index):
   if phase=='after_replace' and index==0:raise SystemExit(97)
  self.fault=fail
s.operations['Operations']=Fault
s.apply(parse(read(sys.argv[4])),sha(read(sys.argv[4])),sys.argv[5],trust_file(sys.argv[6]))
'''
        r=self.driver(code,self.target,self.state,p,self.a,self.trust);self.assertEqual(r.returncode,97,r.stderr)
        self.expect_bad(self.up_apply(self.a,p),'RECOVERY_REQUIRED')
        (self.state/'attempt.json.new').write_text('interrupted old temporary file')
        (self.state/'installed.json.new').write_text('interrupted old temporary file')
        self.expect_ok(self.up_effect('recover'));self.assertEqual(contents(self.config),before)
        p,_,_=self.up_plan(self.a);self.expect_ok(self.up_apply(self.a,p))
        self.expect_ok(self.up_effect('rollback'))
        journals=list((self.state/'managed/operations').glob('*/journal.json'))
        self.assertTrue(any(json.loads(j.read_text())['status']=='RECOVERED' for j in journals))

    def test_updater_runtime_plan_binding_symlinks_space_and_concurrency(self):
        import fcntl
        self.lab_release();self.update_target();p,_,_=self.up_plan(self.a);before=contents(self.config)
        engine=self.repo/'updates/engine.py';original=engine.read_bytes();engine.write_bytes(original+b'\n# changed runtime\n')
        self.expect_bad(self.up_apply(self.a,p),'runtime changed');engine.write_bytes(original)
        self.state.joinpath('tools').mkdir();self.state.joinpath('tools/lua-contract.lua').write_text('error("UNTRUSTED_DECOY")')
        p,_,_=self.up_plan(self.a)
        r=self.driver('''
from engine import Session
from release import parse,read,sha,trust_file
from unittest.mock import patch
from types import SimpleNamespace
with patch('shutil.disk_usage',return_value=SimpleNamespace(free=0)):
 Session(sys.argv[2],sys.argv[3]).apply(parse(read(sys.argv[4])),sha(read(sys.argv[4])),sys.argv[5],trust_file(sys.argv[6]))
''',self.target,self.state,p,self.a,self.trust)
        self.assertNotEqual(r.returncode,0);self.assertIn('INSUFFICIENT_SPACE',r.stderr);self.assertEqual(contents(self.config),before)
        with (self.state/'session.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.expect_bad(self.up_apply(self.a,p),'another updater')
        link=self.area/'bad-state';link.symlink_to(self.state,target_is_directory=True)
        self.expect_bad(self.update_cli('validate','--target',self.target,'--state',link),'symlink')
        self.expect_ok(self.up_apply(self.a,p));self.assertFalse(any('UNTRUSTED_DECOY' in f.read_text(errors='ignore') for f in (self.state/'managed').glob('*.json')))

    def test_updater_tui_uses_same_motor_a_to_b_and_safe_omarchy_dispatch(self):
        import pty,fcntl,termios,struct,select,re,signal
        self.lab_release();b=self.release_b();self.update_target()
        p,_,_=self.up_plan(self.a,'--prefer-heartchy','shell_intent:bar.transparent');self.expect_ok(self.up_apply(self.a,p))
        with self.http_lab([self.a,b]) as (url,_):
            master,slave=pty.openpty();fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',55,130,0,0));attrs=termios.tcgetattr(slave)
            process=subprocess.Popen([str(self.repo/'bin/heartchy-update'),'ui','--trust',str(self.trust),'--target',str(self.target),'--state',str(self.state),'--channel','test','--lab-http',url,'--no-animation'],env={**ENV,'TERM':'xterm-256color'},stdin=slave,stdout=slave,stderr=slave,start_new_session=True,preexec_fn=lambda:fcntl.ioctl(slave,termios.TIOCSCTTY,0));os.close(slave)
            output=bytearray();total=bytearray()
            def wait(needle):
                until=time.monotonic()+10
                while time.monotonic()<until:
                    if needle.encode() in output:return
                    if select.select([master],[],[],.1)[0]:
                        try:data=os.read(master,65536)
                        except OSError:break
                        output.extend(data);total.extend(data)
                        for index in re.findall(rb'\x1b]4;([0-9]+);\?\x1b\\',data):os.write(master,b'\x1b]4;'+index+b';rgb:1111/2222/3333\x1b\\')
                self.fail('Missing '+needle+': '+output.decode(errors='replace')[-1800:])
            def send(data):
                time.sleep(.12);output.clear();os.write(master,data)
            try:
                wait('Esc salir');send(b'\r');wait('Su actualizador no se ejecuta');send(b'\r');wait('Esc salir')
                send(b'\x1b[B\r');wait('Buscar versi');time.sleep(.2);send(b'\r');wait('Revisar confirmaci')
                send(b'\r');wait('Efectos del motor');wait('Cancelar y volver')
                # No conflicts on A→B. Options: next, cancel, confirmation.
                send(b'\x1b[B\x1b[B\r');wait('Aplicar exactamente este plan');wait('Cancelar')
                send(b'\x1b[D\r');wait('Aplicaci');wait('estructural comprobada');wait('Volver al listado')
                self.assertIn(b'APPLIED',total);self.assertNotIn(b'SIMULACI',total)
                send(b'\x1b[B\r');process.wait(timeout=8)
                self.assertEqual(process.returncode,0);self.assertEqual(termios.tcgetattr(master),attrs)
                self.assertNotIn(b'^[[',total)
                self.assertEqual(json.loads((self.state/'installed.json').read_text())['version'],'0.1.0-test.2')
            finally:
                if process.poll() is None:os.killpg(process.pid,signal.SIGKILL);process.wait()
                os.close(master)
        self.expect_ok(self.up_effect('rollback'))

    def test_updater_authority_is_atomic_and_approval_does_not_claim(self):
        self.lab_release();self.update_target();p,_,_=self.up_plan(self.a)
        authority=self.config.parent/'.local/state/heartchy/core-authority.json'
        r=self.update_cli('apply','--delivery',self.a,'--trust',self.trust,'--target',self.target,'--state',self.state,'--plan',p,'--approve','0'*64)
        self.assertNotEqual(r.returncode,0);self.assertFalse(authority.exists())
        before=contents(self.config)
        code='''
from engine import Session
from release import parse,read,sha,trust_file
s=Session(sys.argv[2],sys.argv[3]);old=s.operations['Operations']
class Fault(old):
 def __init__(self,*a,**k):
  super().__init__(*a,**k)
  def fail(phase,index):
   if phase==sys.argv[7]:raise SystemExit(96)
  self.fault=fail
s.operations['Operations']=Fault
s.apply(parse(read(sys.argv[4])),sha(read(sys.argv[4])),sys.argv[5],trust_file(sys.argv[6]))
'''
        for phase in ('authority_prepared','initial_journal_prepared'):
            r=self.driver(code,self.target,self.state,p,self.a,self.trust,phase)
            self.assertEqual(r.returncode,96,r.stderr)
            if phase=='authority_prepared':self.assertFalse(authority.exists())
            self.assertEqual(contents(self.config),before)
            self.expect_ok(self.up_effect('recover'))
        p,_,_=self.up_plan(self.a);self.expect_ok(self.up_apply(self.a,p))
        self.assertEqual(json.loads(authority.read_text())['schema_version'],1)

    def test_updater_pagination_retry_channel_flags_redirect_timeout(self):
        self.lab_release()
        with self.http_lab([self.a],paginate=True) as (url,requests):
            r=self.update_cli('catalog','--trust',self.trust,'--channel','test','--lab-http',url)
            self.expect_ok(r);self.assertEqual(len(json.loads(r.stdout)['releases']),1)
            self.assertTrue(any('page=2' in p for p in requests))
        r=self.driver('''
from release import trust_file,read,parse,Error
from network import Source
from unittest.mock import patch
from pathlib import Path
trust=trust_file(sys.argv[2]);s=Source(trust,'http://127.0.0.1:9',timeout=.01)
d=Path(sys.argv[3]);out=Path(sys.argv[4]);m=parse(read(d/'release.json'))
original=lambda url,limit,asset=False:read(d/url.rsplit('/',1)[-1])
def interrupted(url,limit,asset=False):
 if url.endswith('.tar.gz'):raise Error('truncated fixture')
 return original(url,limit,asset)
with patch.object(s,'get',side_effect=interrupted):
 try:s.fetch(m['version'],out,'test')
 except Error:pass
assert not out.exists() and list(out.parent.glob(out.name+'.*.partial'))
with patch.object(s,'get',side_effect=original):s.fetch(m['version'],out,'test')
assert out.exists()
for url in ['http://evil.example/file','http://user:secret@127.0.0.1:9/file','https://github.com.evil.test/file']:
 try:s.allowed(url,True);raise AssertionError('redirect accepted')
 except Error:pass
with patch('urllib.request.OpenerDirector.open',side_effect=TimeoutError),patch('network.time.sleep'):
 try:s.get('http://127.0.0.1:9/file',100);raise AssertionError('timeout ignored')
 except Error as e:assert 'NETWORK_UNAVAILABLE' in str(e)
# Mutable GitHub prerelease=False never promotes signed test metadata.
row={'draft':False,'prerelease':False,'tag_name':'v'+m['version'],'published_at':'2026-10-07T00:00:00Z'}
from release import encode
with patch.object(s,'get',side_effect=lambda url,limit,asset=False:encode([row]) if '/repos/' in url else original(url,limit,asset)):
 assert s.catalog('stable')['releases']==[]
''',self.trust,self.a,self.area/'retry')
        self.assertEqual(r.returncode,0,r.stderr)

    def test_updater_publish_draft_new_tag_assets_and_exact_commit(self):
        self.lab_release()
        r=self.driver('''
from engine import load,ROOT
from release import parse,read,sha,Error
from types import SimpleNamespace
m=parse(read(sys.argv[2]+'/release.json'));calls=[]
u=load(ROOT/'tools/heartchy-release')
original=u['trust_file']
u['trust_file']=lambda p:{**original(p),'kind':'heartchy-trust'}
# Signature still checked with the same laboratory public key; no remote calls.
def gh(*a,input=None):
 calls.append(a);url=next((x for x in a if x.startswith(('repos/','https://uploads.'))),'')
 if url.endswith('/commits/'+m['source_commit']):return {'sha':m['source_commit']}
 if '/git/matching-refs/' in url:return []
 if 'releases?per_page' in url:return [[]]
 if url.endswith('/git/refs'):assert parse(input)['sha']==m['source_commit'];return {}
 if '/git/ref/tags/' in url:return {'object':{'type':'commit','sha':m['source_commit']}}
 if url.startswith('https://uploads.'):
  assert a[a.index('--input')+1]=='-'
  if url.endswith(m['archive']['name']):assert sha(input)==m['archive']['sha256']
  return {'size':len(input),'digest':'sha256:'+sha(input)}
 if '--method' in a and a[a.index('--method')+1]=='PATCH':
  assert len([c for c in calls if any(x.startswith('https://uploads.') for x in c)])==3
  assert parse(input)=={'draft':False,'prerelease':True,'make_latest':'false'}
  return {'prerelease':True,'draft':False,'html_url':'https://example.invalid/prerelease'}
 if '--method' in a:
  assert parse(input)['draft'] and parse(input)['prerelease']
  from pathlib import Path
  Path(sys.argv[2],m['archive']['name']).write_bytes(b'mutated after remote draft creation')
  return {'id':1}
 return {'private':False}
u['gh']=gh
args=SimpleNamespace(trust=sys.argv[3],delivery=sys.argv[2],approve=sha(read(sys.argv[2]+'/release.json')))
assert u['publish'](args)['result']=='PRE_RELEASE_PUBLISHED'
assert any('/git/refs' in x for c in calls for x in c)
''',self.a,self.trust)
        self.assertEqual(r.returncode,0,r.stderr)

    def test_updater_report_data_not_options_and_animation_optional(self):
        r=self.driver('''
from engine import load,ROOT
from types import SimpleNamespace
from unittest.mock import patch
from tui import FunctionalUI,UI
captured=[]
ui=FunctionalUI.__new__(FunctionalUI);ui.indexed_colors=False;ui.env={};ui.pink='#df82ab'
ui.tool=lambda args,**kw:(captured.append(args) or SimpleNamespace(returncode=0))
ui.panel(['--help','--width=999'])
args=captured[-1];assert args.index('--')<args.index('--help')
ui.animation=True;ui.warning=''
with patch.object(UI['NativeUI'],'prepare_middleout',side_effect=ValueError('ttfx 0.3.2 required')):ui.prepare_middleout()
assert not ui.animation and '0.3.2' in ui.warning
''')
        self.assertEqual(r.returncode,0,r.stderr)

    def test_updater_matching_unowned_noop_is_not_recovery_or_installation(self):
        self.lab_release();self.update_target()
        (self.config/'hypr/heartchy.lua').write_bytes((self.repo/'core/hypr/heartchy.lua').read_bytes())
        p=self.config/'hypr/looknfeel.lua';p.write_bytes(b'require("hypr.heartchy")\n'+p.read_bytes())
        (self.config/'omarchy/shell.toml').write_bytes((self.repo/'core/shell/cristal.toml').read_bytes())
        before=contents(self.config)
        plan,summary,_=self.up_plan(self.a,'--keep-local','shell_intent','--keep-local','shell_tokens')
        self.assertFalse(summary['blocked']);r=self.up_apply(self.a,plan);self.expect_ok(r)
        result=json.loads(r.stdout);self.assertIsNone(result['installed']);self.assertEqual(result['validation']['result'],'NO_MANAGED_APPLICATION')
        self.assertEqual(contents(self.config),before);self.assertFalse((self.state/'installed.json').exists())
        self.assertEqual(json.loads((self.state/'attempt.json').read_text())['status'],'SUCCESS')

    def test_updater_post_commit_local_edit_allows_new_plan_without_false_recovery(self):
        self.lab_release();self.update_target();plan,_,_=self.up_plan(self.a)
        r=self.driver('''
from engine import Session
from release import parse,read,sha,trust_file,Error
from pathlib import Path
s=Session(sys.argv[2],sys.argv[3]);original=s.validate_plan
p=Path(s.marker['config_root'])/'omarchy/shell.toml'
def later(envelope):
 p.write_text(p.read_text().replace('border-alpha = 0.6','border-alpha = 0.8'))
 return original(envelope)
s.validate_plan=later
try:s.apply(parse(read(sys.argv[4])),sha(read(sys.argv[4])),sys.argv[5],trust_file(sys.argv[6]));raise AssertionError('false PASS')
except Error as e:assert 'post-apply validation failed' in str(e)
assert s.pending()['status']=='VALIDATION_PENDING' and s.installed() is None
''',self.target,self.state,plan,self.a,self.trust)
        self.assertEqual(r.returncode,0,r.stderr)
        p,_,obj=self.up_plan(self.a,'--keep-local','shell_tokens:menu.border-alpha')
        self.expect_ok(self.up_apply(self.a,p))
        self.assertIn('border-alpha = 0.8',(self.config/'omarchy/shell.toml').read_text())
        self.assertEqual(json.loads((self.state/'installed.json').read_text())['result'],'APPLIED_WITH_LOCAL_PREFERENCES')

    def test_updater_old_release_permissions_target_lock_and_incompatible_loader(self):
        import fcntl
        self.lab_release();b=self.release_b();self.update_target()
        plan,_,_=self.up_plan(b);before=contents(self.config)
        fd=os.open(self.config,os.O_RDONLY|os.O_DIRECTORY)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.expect_bad(self.up_apply(b,plan),'operation already in progress on this target')
        finally:os.close(fd)
        self.expect_ok(self.up_effect('recover'));self.assertEqual(contents(self.config),before)
        plan,_,_=self.up_plan(b)
        folder=self.config/'hypr';folder.chmod(0o500)
        try:
            r=self.up_apply(b,plan);self.assertNotEqual(r.returncode,0)
            self.assertEqual(contents(self.config),before)
        finally:folder.chmod(0o755)
        self.expect_ok(self.up_effect('recover'))
        plan,_,_=self.up_plan(b);self.expect_ok(self.up_apply(b,plan))
        r=self.update_cli('plan','--delivery',self.a,'--trust',self.trust,'--target',self.target,'--state',self.state,'--output',self.area/'old.json')
        self.expect_bad(r,'OLDER_RELEASE_UNSUPPORTED')
        loader=self.area/'stock/default/hypr/bootstrap.lua';loader.write_text(loader.read_text()+'-- untested contract\n')
        r=self.update_cli('plan','--delivery',b,'--trust',self.trust,'--target',self.target,'--state',self.state,'--output',self.area/'incompatible.json')
        self.assertNotEqual(r.returncode,0)

    def test_updater_unknown_signer_and_hostile_members(self):
        self.lab_release()
        other=self.area/'other-key';subprocess.run(['/usr/bin/ssh-keygen','-q','-t','ed25519','-N','','-f',str(other)],env=ENV,check=True,capture_output=True)
        trust=json.loads(self.trust.read_text());trust['public_key']=' '.join(other.with_suffix('.pub').read_text().split()[:2])
        unknown=self.area/'unknown.json';unknown.write_text(json.dumps(trust))
        self.expect_bad(self.update_cli('verify','--trust',unknown,'--delivery',self.a),'SIGNATURE_INVALID')
        for i,(name,kind) in enumerate([('/absolute',tarfile.REGTYPE),('core/hypr/heartchy.lua',tarfile.FIFOTYPE),('core/hypr/heartchy.lua',tarfile.LNKTYPE)]):
            d=self.area/('hostile-'+str(i));shutil.copytree(self.a,d);m=json.loads((d/'release.json').read_text());a=d/m['archive']['name']
            with tarfile.open(a,'w:gz') as tar:
                entry=tarfile.TarInfo(name);entry.type=kind;entry.linkname='/etc/passwd';tar.addfile(entry)
            m['archive'].update(bytes=a.stat().st_size,sha256=digest(a));self.sign_metadata(d,m)
            self.expect_bad(self.update_cli('extract','--delivery',d,'--trust',self.trust,'--output',self.area/('extract-'+str(i))),'hostile')
        # A validly signed inventory still cannot accept duplicated members.
        d=self.area/'duplicate';shutil.copytree(self.a,d);m=json.loads((d/'release.json').read_text());a=d/m['archive']['name']
        with tarfile.open(a,'r:gz') as original:
            entry=original.next();payload=original.extractfile(entry).read()
        with tarfile.open(a,'w:gz',format=tarfile.USTAR_FORMAT) as tar:
            tar.addfile(entry,io.BytesIO(payload));tar.addfile(entry,io.BytesIO(payload))
        m['archive'].update(bytes=a.stat().st_size,sha256=digest(a));self.sign_metadata(d,m)
        self.expect_bad(self.update_cli('verify','--delivery',d,'--trust',self.trust),'duplicate')

    def test_updater_recover_completed_commit_with_later_preserved_edit(self):
        self.lab_release();b=self.release_b();self.update_target()
        p,_,_=self.up_plan(self.a);self.expect_ok(self.up_apply(self.a,p))
        tokens=self.config/'omarchy/shell.toml';tokens.write_text(tokens.read_text().replace('border-alpha = 0.6','border-alpha = 0.8'))
        p,_,_=self.up_plan(b,'--keep-local','shell_tokens:menu.border-alpha')
        r=self.driver('''
from engine import Session
from release import parse,read,sha,trust_file
s=Session(sys.argv[2],sys.argv[3])
def interrupted(envelope):raise SystemExit(97)
s.validate_plan=interrupted
s.apply(parse(read(sys.argv[4])),sha(read(sys.argv[4])),sys.argv[5],trust_file(sys.argv[6]))
''',self.target,self.state,p,b,self.trust)
        self.assertEqual(r.returncode,97,r.stderr)
        tokens.write_text(tokens.read_text().replace('border-alpha = 0.8','border-alpha = 0.7'))
        before=contents(self.config);r=self.up_effect('recover')
        self.assertEqual(r.returncode,3,r.stderr);self.assertEqual(json.loads(r.stdout)['result'],'VALIDATION_PENDING')
        self.assertEqual(contents(self.config),before)
        p,_,_=self.up_plan(b,'--keep-local','shell_tokens:menu.border-alpha');self.expect_ok(self.up_apply(b,p))
        self.assertIn('border-alpha = 0.7',tokens.read_text())
