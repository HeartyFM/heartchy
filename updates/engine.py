"""Portable adapter to the existing Core planner/transaction; no second editor."""
import contextlib
import fcntl
import io
import os
from pathlib import Path
import shutil
import signal
import uuid
from types import SimpleNamespace
from release import Error,need,sha,encode,parse,read,write_new,safe_path,verify_delivery

ROOT=Path(__file__).resolve().parents[1]
SUPPORT=('core/manifest.json','core/hypr/heartchy.lua','core/shell/cristal.toml','core/shell/settings-intent.json','docs/provenance.json','docs/upstream-evidence.json','docs/architecture.md','docs/upstream.md','NOTICE.md')
TOOLS=('heartchy-dev','heartchy-plan.py','heartchy-lua-plan.py','heartchy-target.py','heartchy-apply.py','lua-contract.lua')

def load(path):
    ns={'__name__':'heartchy_library','__file__':str(path)}
    exec(compile(read(path),str(path),'exec'),ns)
    return ns

def replace(path,value):
    p=safe_path(path);tmp=p.with_name('.'+p.name+'.'+uuid.uuid4().hex+'.new')
    write_new(tmp,encode(value));os.replace(tmp,p)
    fd=os.open(p.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)

class Session:
    def __init__(self,target,state):
        self.target=safe_path(target);self.root=safe_path(state)
        need(self.target.name=='target.json','target must be an explicit target.json descriptor')
        descriptor=read(self.target,20000);marker=parse(descriptor)
        need(marker.get('kind')=='heartchy-local-target','explicit config/shadow/stock descriptor required')
        config=safe_path(marker['config_root']);shadow=safe_path(marker['shadow_root'])
        need(not self.root.is_relative_to(config) and not config.is_relative_to(self.root),'state/config overlap')
        need(any(self.root.is_relative_to(p) and self.root!=Path(p) for p in ('/home','/tmp','/sandbox')),'state outside allowed roots')
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        need(self.root.stat().st_uid==os.getuid() and self.root.stat().st_mode&0o077==0,'state must be private mode 0700')
        destination=self.root/'target/target.json'
        if destination.exists():need(read(destination)==descriptor,'state belongs to a different target descriptor')
        else:write_new(destination,descriptor)
        self.api=load(ROOT/'tools/heartchy-dev')
        self.api['ROOT']=self.root;self.api['RUNTIME_MODE']=True
        source=lambda rel: ROOT/rel if rel.startswith(('tools/','core/')) else self.root/rel
        self.api['source_path']=source
        def reader(rel,missing_ok=False):
            self.api['relative_parts'](rel)
            try:return read(source(rel),2_000_000)
            except FileNotFoundError:
                if missing_ok:return None
                raise self.api['Invalid']('missing runtime/workspace input: '+rel)
        self.api['read_project']=reader
        self.planning=load(ROOT/'tools/heartchy-plan.py')
        self.operations=load(ROOT/'tools/heartchy-apply.py')
        self.client_hash=sha(encode({str(p.relative_to(ROOT)):sha(read(p)) for p in [*(ROOT/'tools'/f for f in TOOLS),*sorted((ROOT/'updates').glob('*.py')),ROOT/'mockups/updates.py',ROOT/'mockups/animation_preview.py',ROOT/'bin/heartchy-update']}))
        self.marker=marker

    @contextlib.contextmanager
    def lock(self):
        p=self.root/'session.lock';fd=os.open(p,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
        try:
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError as exc:raise Error('another updater is using this state') from exc
            yield
        finally:os.close(fd)

    @contextlib.contextmanager
    def system_guard(self):
        # Isolated fixture contracts do not touch any host lock. A future
        # personal test shares the installed Omarchy lock, without running it.
        if self.marker['stock_root'] != '/usr/share/omarchy':
            yield
            return
        expected = '9448e1748b10e46bb4310be37d69d0eba6090f69c71264cce4fc6f344278cb7d'
        need(sha(read('/usr/bin/omarchy-update-lock')) == expected,
             'INCOMPATIBLE Omarchy update-lock contract; review before writing')
        lock_root = safe_path(os.environ.get('XDG_RUNTIME_DIR') or '/tmp')
        lock_path = safe_path(lock_root / 'omarchy-update.lock')
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(fd)
            need(info.st_uid == os.getuid() and info.st_nlink == 1,
                 'unsafe Omarchy coordination lock')
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise Error('OMARCHY_UPDATE_BUSY: retry with a new plan later') from exc
            need(not Path('/var/lib/pacman/db.lck').exists(), 'PACKAGE_TRANSACTION_BUSY')
            yield
        finally:
            os.close(fd)

    def prepare(self,delivery,trust):
        m,content=verify_delivery(delivery,trust)
        # Authentication precedes validation/evaluation of any candidate Lua.
        identity=sha(read(Path(delivery)/'release.json'))
        folder='candidates/'+identity
        for name in (*SUPPORT,'inventory.json'):
            p=self.root/folder/name
            if p.exists():need(read(p)==content[name],'candidate cache altered')
            else:write_new(p,content[name],0o644)
        return m,identity,folder

    def pending(self):
        p=self.root/'attempt.json'
        return parse(read(p)) if p.exists() else None

    def require_clean(self):
        pending=self.pending()
        need(not pending or pending['status'] not in ('COMMITTING','RECOVERY_REQUIRED'),'RECOVERY_REQUIRED: reopen with recover before another update')
        op=self.op('validate')
        op.clean();op.ledger()

    def installed(self):
        path=self.root/'installed.json'
        if not path.exists():return None
        record=parse(read(path))
        if record.get('result') not in ('APPLIED','APPLIED_WITH_LOCAL_PREFERENCES','RECOVERED_COMMITTED'):
            return None
        # A downloaded or rolled-back release is never an installed marker.
        state,_=self.op('validate').ledger()
        if not state or not state['resources']:return None
        return record

    def op(self,command,**extra):
        args=SimpleNamespace(command=command,target='target',state_root='managed',format='json',approve=command,replace=[],**extra)
        return self.operations['Operations'](self.api,args)

    def plan(self,delivery,trust,prefer=(),keep=()):
        self.require_clean();m,identity,candidate=self.prepare(delivery,trust)
        installed=self.installed()
        if installed:
            from release import version
            need(version(m['version'])>=version(installed['version']),'OLDER_RELEASE_UNSUPPORTED: rollback restores origin, not a downgrade')
        args=SimpleNamespace(candidate=candidate,target='target',state_root='managed',resource=None,prefer_heartchy=list(prefer),keep_local=list(keep),recheck=None,format='json')
        plan=self.planning['Planner'](self.api,args).run()
        raw=encode(plan);path='plans/'+sha(raw)+'.json'
        if not (self.root/path).exists():write_new(self.root/path,raw)
        envelope={'schema':1,'kind':'heartchy-release-plan','release':{'version':m['version'],'commit':m['source_commit'],'sha256':identity},'client_sha256':self.client_hash,'target':str(self.target),'state':str(self.root),'core_plan':plan,'core_plan_path':path}
        return envelope

    def inspect_plan(self,envelope,approval,delivery,trust):
        need(sha(encode(envelope))==approval,'approval must equal the reviewed canonical plan digest')
        need(envelope.get('schema')==1 and envelope.get('kind')=='heartchy-release-plan','invalid approval document')
        need(envelope['target']==str(self.target) and envelope['state']==str(self.root) and envelope['client_sha256']==self.client_hash,'plan target/runtime changed')
        sel=envelope['core_plan']['selection']
        current=self.plan(delivery,trust,sel['prefer_heartchy'],sel['keep_local'])
        need(current==envelope,'STALE_PLAN: regenerate and approve again')
        need(not current['core_plan']['blocked'] and not current['core_plan']['pending_conflicts'],'BLOCKED/unresolved conflict')
        return current

    @contextlib.contextmanager
    def commit_signals(self):
        # Once commit starts, closing a TUI may not kill the writer midway.
        # Power loss/SIGKILL still rely on the persistent Core journal.
        blocked={signal.SIGINT,signal.SIGTERM,signal.SIGHUP}
        previous={s:signal.signal(s,signal.SIG_IGN) for s in blocked}
        try:yield
        finally:
            for s,h in previous.items():signal.signal(s,h)

    def invoke(self,command,**extra):
        op=self.op(command,**extra)
        try:
            if command!='validate':op.acquire()
            return getattr(op,command)()
        finally:
            for fd in (op.lock,op.target_lock):
                if fd is not None:os.close(fd)

    def apply(self,envelope,approval,delivery,trust):
        with self.lock(), self.system_guard():
            self.inspect_plan(envelope,approval,delivery,trust)
            need(shutil.disk_usage(self.root).free>=8*1024*1024,'INSUFFICIENT_SPACE: state needs 8 MiB reserve')
            need(shutil.disk_usage(self.marker['config_root']).free>=8*1024*1024,'INSUFFICIENT_SPACE: target needs 8 MiB reserve')
            attempt={'status':'COMMITTING','plan':envelope,'previous':self.installed()}
            with self.commit_signals():
                replace(self.root/'attempt.json',attempt)
                committed=False
                try:
                    plan=envelope['core_plan']
                    op=self.op('apply',candidate=plan['candidate'],plan=envelope['core_plan_path'])
                    op.args.approve=sha(encode(plan))
                    try:
                        op.acquire();result=op.apply();committed=True
                    finally:
                        for fd in (op.lock,op.target_lock):
                            if fd is not None:os.close(fd)
                    managed,_=self.op('validate').ledger()
                    if not managed or not managed['resources']:
                        attempt.update(status='SUCCESS',result=result,validation={'result':'NO_MANAGED_APPLICATION'})
                        replace(self.root/'attempt.json',attempt)
                        return {'apply':result,'validation':attempt['validation'],'installed':None,'graphical':'NOT_RUN'}
                    validation=self.validate_plan(envelope)
                    need(validation['result'] in ('PASS','LOCAL_PRESERVED'),'post-apply validation failed')
                    record={**envelope['release'],'result':'APPLIED_WITH_LOCAL_PREFERENCES' if result['local_preserved'] else 'APPLIED','client_sha256':self.client_hash,'operation_id':result.get('operation_id') or (self.installed() or {}).get('operation_id')}
                    if record!=self.installed():replace(self.root/'installed.json',record)
                    attempt.update(status='SUCCESS',result=result,validation=validation);replace(self.root/'attempt.json',attempt)
                    return {'apply':result,'validation':validation,'installed':record,'graphical':'NOT_RUN'}
                except Exception:
                    attempt['status']='VALIDATION_PENDING' if committed else 'RECOVERY_REQUIRED'
                    if committed and (self.root/'installed.json').exists():
                        record=parse(read(self.root/'installed.json'));record['result']='VALIDATION_PENDING';replace(self.root/'installed.json',record)
                    replace(self.root/'attempt.json',attempt)
                    raise

    def validate_plan(self,envelope):
        result=self.invoke('validate')
        # An intentional preserved preference is an expected divergence from
        # the old owned reference, never implicit ownership of the local edit.
        allowed={r['resource']+':'+r['key']:r for r in envelope['core_plan']['entries'] if r['decision']=='LOCAL_PRESERVED'}
        if result['result']=='FAIL' and set(result['mismatches'])<=set(allowed):
            op=self.op('validate')
            for key in result['mismatches']:
                row=allowed[key];actual=op.values(row['resource'],op.read(op.paths[row['resource']]))
                need(actual.get(row['key'],{'state':'absent'})==row['planned'],'local value changed after plan')
            result={**result,'result':'LOCAL_PRESERVED','expected_local_preferences':result['mismatches']}
        return result

    def recover(self):
        with self.lock(),self.system_guard(),self.commit_signals():
            result=self.invoke('recover');pending=self.pending()
            if pending and pending['status'] in ('COMMITTING','RECOVERY_REQUIRED') and pending.get('kind') == 'rollback':
                marker=self.root/'installed.json'
                if marker.exists():
                    record=parse(read(marker));record['result']='UNVERIFIED_AFTER_ROLLBACK';replace(marker,record)
                pending['status']='RECOVERED';replace(self.root/'attempt.json',pending)
                return {**result,'installation':'UNVERIFIED_AFTER_ROLLBACK; replan required'}
            if pending and pending['status'] in ('COMMITTING','RECOVERY_REQUIRED'):
                op=self.op('validate');state,ledger=op.ledger()
                expected=sha(encode(pending['plan']['core_plan']))
                if ledger and ledger['candidate'].get('plan_sha256')==expected:
                    try:
                        checked=self.validate_plan(pending['plan'])
                    except Exception as exc:
                        checked={'result':'FAIL','reason':str(exc)}
                    if checked['result'] not in ('PASS','LOCAL_PRESERVED'):
                        pending['status']='VALIDATION_PENDING';replace(self.root/'attempt.json',pending)
                        marker=self.root/'installed.json'
                        if marker.exists():
                            record=parse(read(marker));record['result']='VALIDATION_PENDING';replace(marker,record)
                        return {'result':'VALIDATION_PENDING','validation':checked,'next':'Replan; preserve or explicitly resolve the later edit. No restoration performed.'}
                    replace(self.root/'installed.json',{**pending['plan']['release'],'result':'RECOVERED_COMMITTED','client_sha256':self.client_hash,'operation_id':ledger['operation_id']})
                pending['status']='RECOVERED';replace(self.root/'attempt.json',pending)
            return result

    def rollback(self,replacements=()):
        with self.lock(),self.system_guard(),self.commit_signals():
            self.require_clean()
            attempt={'kind':'rollback','status':'COMMITTING','previous':self.installed()}
            replace(self.root/'attempt.json',attempt)
            op=self.op('rollback');op.args.replace=list(replacements)
            try:
                op.acquire();result=op.rollback()
            finally:
                for fd in (op.lock,op.target_lock):
                    if fd is not None:os.close(fd)
            marker=self.root/'installed.json'
            if marker.exists():
                record=parse(read(marker))
                record['result']='PARTIAL_ROLLBACK' if result['result'] in ('PARTIAL_ROLLBACK','LOCAL_PRESERVED') else 'REMOVED'
                replace(marker,record)
            attempt['status']='SUCCESS';replace(self.root/'attempt.json',attempt)
            return result
