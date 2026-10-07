"""Functional adapter of the approved Gum/Fzf presentation, not another editor."""
import json
import subprocess
from pathlib import Path
import shutil
import sys
import textwrap
from release import Error,need,sha,encode,version,read
from engine import Session,ROOT,load

UI=load(ROOT/'mockups/updates.py')

class Model(UI['Model']):
    @property
    def action(self):
        if self.installed==self.current.version:return 'Revalidar versión '+self.current.version
        if not self.installed:return 'Instalar Heartchy '+self.current.version+' · PRUEBA'
        if version(self.current.version)<version(self.installed):return 'Versión anterior: no se admite downgrade'
        return 'Actualizar de '+self.installed+' a '+self.current.version+' · PRUEBA'

    def event(self,key,now=0):
        if self.screen=='report' and key=='enter':self.screen='prepare';return
        if self.screen=='confirm' and key=='enter':
            self.screen='progress' if self.button==0 else 'releases';return
        super().event(key,now)

class FunctionalUI(UI['NativeUI']):
    def __init__(self,model,session,source,trust,records,animation):
        super().__init__(model,animation=animation)
        self.notice='PRUEBA / PRE-RELEASE · Operaciones reales sobre target explícito'
        self.session,self.source,self.trust,self.records=session,source,trust,records
        self.delivery=None;self.approved=None;self.outcome=None;self.warning=''

    def prepare_middleout(self):
        try:super().prepare_middleout()
        except (ValueError,OSError,subprocess.SubprocessError) as exc:
            self.animation=False;self.warning=str(exc)
            self.notice='PRUEBA · Animación no disponible; transición instantánea (diagnóstico al salir)'

    def live_banner(self,name,columns,rows):
        return super().live_banner(name,columns,rows).replace(UI['SIMULATION'],self.notice)

    def report_content(self,width):
        lines=UI['report_lines'](self.model,width)
        return [line.replace('Actual simulada:','Core registrado:').replace('Ninguna en esta versión ficticia.','Ninguna; sólo Core Cristal.') for line in lines]

    def choices(self,options):
        r=self.tool(['/usr/bin/gum','choose','--header','','--no-show-help','--',*options],capture=True)
        if r.returncode in (1,130):return None
        need(r.returncode==0 and r.stdout.strip() in options,'invalid UI choice')
        return r.stdout.strip()

    def prepare(self):
        self.brand();self.panel(['Preparando propuesta verificada',self.model.current.version,'Target: '+str(self.session.target),'Descarga/verificación/plan; todavía no aplica. Ctrl+C cancela.'])
        try:
            folder=self.session.root/'downloads'/self.model.current.version
            if not folder.exists():self.source.fetch(self.model.current.version,folder,self.records['channel'])
            self.delivery=folder
            with self.session.lock():self.proposal=self.session.plan(folder,self.trust)
            self.model.screen='effects'
        except Exception as exc:
            self.outcome={'result':'BLOCKED','reason':str(exc)};self.model.screen='result'

    def effects(self):
        page=0
        while self.model.screen=='effects' and not self.model.closed:
            plan=self.proposal['core_plan'];rows=plan['entries']
            size=shutil.get_terminal_size();width=max(28,size.columns-8);capacity=max(3,size.lines-24)
            lines=['Target: '+str(self.session.target),'Privilegios: usuario normal; sin reload/servicios/paquetes.']
            for block in plan['blocks']:lines.extend(textwrap.wrap('BLOCKED: '+json.dumps(block,ensure_ascii=True),width))
            for row in rows:
                data=row['resource']+':'+row['key']+' '+row['decision']+' '+json.dumps(row['current'],ensure_ascii=True)+' → '+json.dumps(row.get('planned',row['proposed']),ensure_ascii=True)
                lines.extend(textwrap.wrap(data,width))
            pages=[lines[i:i+capacity] for i in range(0,len(lines),capacity)];page=min(page,len(pages)-1)
            self.brand();self.panel([f'Efectos del motor · {page+1}/{len(pages)}',*pages[page]],padding='0 2')
            conflict=[r for r in rows if r['decision'] in ('LOCAL_PRESERVED','CONFLICT_PENDING')]
            options=['Cancelar y volver']
            if page+1<len(pages):options.insert(0,'Página siguiente')
            if page:options.append('Página anterior')
            if conflict:options.append('Resolver una preferencia')
            if not plan['blocked'] and not plan['pending_conflicts']:options.append('Revisar confirmación definitiva')
            choice=self.choices(options)
            if choice=='Página siguiente':page+=1
            elif choice=='Página anterior':page-=1
            elif choice=='Resolver una preferencia':
                ids=[r['resource']+':'+r['key'] for r in conflict];key=self.choices(['Volver',*ids])
                if key not in ids:continue
                resolution=self.choices(['Conservar local','Elegir Heartchy sólo para '+key,'Volver'])
                if not resolution or resolution=='Volver':continue
                sel=plan['selection'];prefer=set(sel['prefer_heartchy']);keep=set(sel['keep_local']);prefer.discard(key);keep.discard(key)
                (keep if resolution=='Conservar local' else prefer).add(key)
                with self.session.lock():self.proposal=self.session.plan(self.delivery,self.trust,sorted(prefer),sorted(keep))
                page=0
            elif choice=='Revisar confirmación definitiva':self.model.screen='confirm'
            else:self.model.screen='releases'

    def confirm(self):
        self.brand();self.panel(['Confirmar aplicación PRUEBA',self.model.action,'Target: '+self.session.marker['config_root'],'Estado: '+str(self.session.root),'Plan SHA256: '+sha(encode(self.proposal)),'Sólo Core indicado en el plan. Sin privilegios ni recarga.'])
        r=self.tool(['/usr/bin/gum','confirm','¿Aplicar exactamente este plan?','--default=false','--affirmative','Aplicar','--negative','Cancelar','--no-show-help'])
        if r.returncode==0:self.approved=sha(encode(self.proposal));self.model.screen='progress'
        elif r.returncode in (1,130):self.model.screen='releases'
        else:raise Error('confirmation failed')

    def progress(self):
        self.brand();self.panel(['Aplicación en curso','Recheck → preparación → commit → validación','Espere el resultado del motor; cierre aplazado durante escritura.','No se muestra un porcentaje inventado.'])
        try:
            self.outcome=self.session.apply(self.proposal,self.approved,self.delivery,self.trust)
            if self.outcome['installed']:self.model.installed=self.outcome['installed']['version']
        except Exception as exc:self.outcome={'result':'BLOCKED','reason':str(exc),'recovery':'Conserve estado/journal; use recover si se indica RECOVERY_REQUIRED.'}
        self.model.screen='result'

    def result(self):
        self.brand();width=max(28,shutil.get_terminal_size().columns-8)
        if 'apply' in self.outcome and not self.outcome.get('installed'):
            lines=['Sin aplicación administrada','Preferencias conservadas; ninguna versión se marca instalada.','No se creó propiedad ni se requiere recuperación.']
        elif 'apply' in self.outcome:
            lines=['Aplicación estructural comprobada',self.outcome['installed']['result'],self.model.current.version,'Validación gráfica: NOT_RUN','Operación: '+str(self.outcome['apply'].get('operation_id'))]
        else:lines=['Operación no completada',*textwrap.wrap(json.dumps(self.outcome,ensure_ascii=True),width)]
        self.panel(lines)
        choice=self.choices(['Volver al listado','Salir'])
        self.model.closed=choice!='Volver al listado'
        if not self.model.closed:self.model.screen='releases'

    def omarchy(self):
        self.brand('OMARCHY');self.panel(['Omarchy permanece independiente','Su actualizador no se ejecuta en esta prueba.'])
        self.choices(['Volver']);self.model.screen='selector'

def run(args,source,trust):
    session=Session(args.target,args.state)
    session.require_clean()
    catalog=source.catalog(args.channel)
    need(catalog['releases'],'no authenticated releases in selected channel')
    releases=[]
    for row in catalog['releases']:
        m=row['metadata'];e=m['editorial']
        releases.append(UI['Release'](e['name'],m['version'],e['card'],row['published_at'][:10],e['summary'],e['description'],*(tuple(e[k]) for k in ('changes','apps','components','fixes','notes'))))
    installed=session.installed();model=Model(tuple(releases),installed['version'] if installed else None)
    ui=FunctionalUI(model,session,source,trust,catalog,not args.no_animation)
    ui.run()
    if ui.warning:print(ui.warning,file=sys.stderr)
    return {'result':'CLOSED','target':str(session.target),'state':str(session.root)}
