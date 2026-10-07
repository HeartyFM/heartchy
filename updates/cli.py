"""Explicit functional test client; no personal target or channel defaults."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
from release import Error,need,encode,parse,sha,read,write_new,trust_file,verify_delivery,extract
from network import Source,cached_catalog
from engine import Session,ROOT,load


def parser():
    p=argparse.ArgumentParser(description='Heartchy PRUEBA / PRE-RELEASE. Descarga firmada y operaciones reales sólo sobre target explícito; sin paquetes, servicios ni autoactualización del cliente.')
    sub=p.add_subparsers(dest='command',required=True)
    for command in ('catalog','fetch','verify','extract','plan','apply','validate','rollback','recover','ui'):
        c=sub.add_parser(command)
        if command in ('catalog','fetch','verify','extract','plan','apply','ui'):c.add_argument('--trust',required=True,help='Raíz pública autorizada previamente, nunca tomada de esta descarga.')
        if command in ('catalog','fetch','ui'):
            c.add_argument('--channel',choices=('stable','test'),required=True)
            c.add_argument('--lab-http',help='Sólo loopback y confianza heartchy-lab-trust para pruebas HTTP aisladas.')
        if command in ('verify','extract','plan','apply'):c.add_argument('--delivery',required=True)
        if command=='catalog':
            c.add_argument('--cache-output',help='Archivo nuevo de catálogo autenticado para consulta offline explícita.')
            c.add_argument('--cached',help='Leer explícitamente un catálogo anterior; no acredita frescura actual.')
        if command=='fetch':c.add_argument('--version',required=True)
        if command in ('fetch','extract','plan'):c.add_argument('--output',required=True,help='Destino nuevo explícito; nunca sobrescribe.')
        if command in ('plan','apply','validate','rollback','recover','ui'):
            c.add_argument('--target',required=True,help='Archivo target.json con config_root/shadow_root/stock_root; sin HOME implícito.')
            c.add_argument('--state',required=True,help='Directorio privado 0700 estable por target. Conservar para recuperación.')
        if command=='plan':
            c.add_argument('--prefer-heartchy',action='append',default=[])
            c.add_argument('--keep-local',action='append',default=[])
        if command=='apply':
            c.add_argument('--plan',required=True)
            c.add_argument('--approve',required=True,help='SHA256 exacto del documento revisado; recheck no replantea decisiones.')
        if command in ('rollback','recover'):c.add_argument('--approve',choices=(command,),required=True)
        if command=='rollback':c.add_argument('--replace',action='append',default=[],help='Sólo recurso:clave previamente administrado; no force global.')
        if command=='ui':
            c.add_argument('--window',action='store_true')
            c.add_argument('--no-animation',action='store_true')
    return p

def execute(args):
    trust=trust_file(args.trust) if hasattr(args,'trust') else None
    if args.command in ('catalog','fetch','ui'):
        source=Source(trust,args.lab_http)
    if args.command=='catalog':
        c=cached_catalog(args.cached,trust,args.channel) if args.cached else source.catalog(args.channel)
        if args.cache_output:write_new(args.cache_output,encode(c))
        return c
    if args.command=='fetch':return source.fetch(args.version,args.output,args.channel)
    if args.command=='verify':return verify_delivery(args.delivery,trust)[0]
    if args.command=='extract':return extract(args.delivery,args.output,trust)
    if args.command=='ui':
        if args.window:
            app=load(ROOT/'mockups/updates.py')
            argv=app['window_command'](animation=not args.no_animation)
            cut=argv.index('-e')
            arguments=sys.argv[1:];arguments.remove('--window')
            return {'window_exit':subprocess.call(argv[:cut+1]+[str(ROOT/'bin/heartchy-update'),*arguments])}
        from tui import run
        return run(args,source,trust)
    session=Session(args.target,args.state)
    if args.command=='plan':
        with session.lock():envelope=session.plan(args.delivery,trust,args.prefer_heartchy,args.keep_local)
        write_new(args.output,encode(envelope))
        return {'plan':str(Path(args.output).absolute()),'approve':sha(encode(envelope)),'blocked':envelope['core_plan']['blocked'],'pending_conflicts':envelope['core_plan']['pending_conflicts'],'summary':envelope['core_plan']['summary']}
    if args.command=='apply':return session.apply(parse(read(args.plan)),args.approve,args.delivery,trust)
    if args.command=='validate':return session.invoke('validate')
    if args.command=='rollback':return session.rollback(args.replace)
    if args.command=='recover':return session.recover()
    raise Error('unknown operation')

def main():
    args=parser().parse_args()
    try:
        result=execute(args)
        print(encode(result).decode(),end='')
        return 3 if result.get('result') in ('FAIL','PARTIAL_ROLLBACK','LOCAL_PRESERVED','VALIDATION_PENDING') or result.get('blocked') or result.get('pending_conflicts') else 0
    except KeyboardInterrupt:
        print('Cancelado; si hubo una escritura interrumpida, conserve state y use recover.',file=sys.stderr);return 130
    except (Error,OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError) as exc:
        # Core Invalid is loaded dynamically and handled separately below.
        print('HEARTCHY BLOCKED: '+str(exc),file=sys.stderr);return 1
    except Exception as exc:
        if type(exc).__name__!='Invalid':raise
        print('HEARTCHY BLOCKED: '+str(exc),file=sys.stderr);return 1

if __name__=='__main__':raise SystemExit(main())
