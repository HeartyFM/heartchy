# Aplicación controlada del Core — ARQ-004

ID: HCY-core-apply
Nombre: Primitivas Core apply/validate/rollback/recover
Estado: ISOLATED_TESTED
Último estado alcanzado: ISOLATED_TESTED
Bloqueo: primer LOCAL TEST BLOCKED antes de apply; bloqueos de entrypoint/TOML corregidos con fixtures. Nueva integración VISUAL/LOCAL/TARGET NOT_RUN; repetición real pendiente desde precheck nuevo, excluida de esta entrega.
Responsable: /root, único escritor; revisión independiente /root/review_readonly

## Objetivo
Demostrar candidate → plan → aprobación → apply → validate → rollback sobre fixtures, con propiedad acotada y recuperación de interrupciones. Sin updater.

## No objetivos
Aplicación personal, reload/restart/refresh, instalador, update, publicación, merge a main, remote/push, plugins, servicios o Features nuevas.

## Decisiones de Diego aplicables
Solicitud ARQ-004 de esta sesión, 2026-10-04: autoriza primitivas Core, pruebas aisladas y commits locales en feature/core-apply desde main @ 28b0e6c. Política ARQ-002 conservada: local por defecto, reemplazo explícito limitado; no force. Autoriza preparación documental del Local Test Gate, no ejecución. Identidad Git previamente aportada, sólo por comando.

Corrección de compatibilidad posterior al LOCAL bloqueado: Diego autoriza prefijo Lua con extensiones legítimas, TOML ajeno válido y aceptación explícita de coincidencias Shell sin atribuir creación. Sin nueva ejecución real ni cambios visuales/target/plugins; contratos actualizados sólo en arquitectura.

## Tipo de Feature
Core / herramientas CLI / persistencia de propiedad y recuperación.

## Subsistemas afectados
Fuentes Core sin cambio de valores; manifiesto marca aplicación separada del inventario. tools/heartchy-dev, heartchy-plan.py, nuevos heartchy-apply.py/heartchy-target.py; test/suite.py y fixture defaults stock; documentación directamente relacionada. Sin reorganizar fuentes ni otros proyectos.

## Integración con Omarchy
No IPC, ejecución del Lua del destinatario ni comandos mutadores externos. Descriptor explícito sólo para rutas consumidas por el loader comprobado. Aplicación local futura sigue su gate. Rutas/config reales no se escribieron en esta entrega.

## APIs/contratos utilizados
H-LUA-LOAD, H-LUA-RULES, H-SHELL-JSON, H-SHELL-TOKENS, H-STOCK-BAR según docs/upstream-contracts.md. El contrato ARQ-003 de reconocimiento/carga permanece; tres loaders instalados leídos selectivamente confirman sus hashes registrados. No se atribuye versión del paquete al commit upstream. Descriptor no certifica Shell ni la sesión.

## Persistencia
Estado y journals privados bajo build/state/<nombre>, generado/ignorado. managed.json compatible con bases del planner; ledger de originales/propiedad vinculado al descriptor; journals por UUID. Contrato único: docs/architecture.md#aplicacion-arq-004. No snapshots personales como fuente ni estado permanente innecesario.

## Privilegios
N/A. Sin sudo, paquetes ni servicios. Namespaces Bubblewrap para tests, sin sesión accesible.

## Dependencias
Python estándar/fcntl; Lua y Bubblewrap ya requeridos por el baseline. No dependencias nuevas instaladas.

## Compatibilidad conocida
Contratos declarados por fixtures y loaders con hashes conocidos; no rangos de versión ni compatibilidad gráfica prometida. Fuente Core conserva nueve candidatos. LOCAL/VISUAL/TARGET NOT_RUN.

## Criterios de aceptación
Apply revalida plan/candidato/hashes y aprobación, prepara todos los archivos antes de commit, preserva valores/bytes ajenos y distingue cambios escritos/referencias aceptadas. Rollback conserva ediciones posteriores, admite resolución limitada, no posee cargas equivalentes. EntryPoint stock con guard final Hyprmoncfg se reconoce sin modificarlo; TOML boolean/arrays/etc ajenos se preserva sin ignorar diferencias del consumidor stock. No-op sin duplicaciones/operaciones extra. Journals detectan interrupciones, recovery condicionada y fallos sin ocultar incertidumbre. Suite histórica pasa y copia portátil funciona. Procedimiento real exacto documentado; repetir desde cero.

## Pruebas requeridas
STATIC + UNIT + ISOLATED_INTEGRATION con suite; negativos de stale plan, corrupción, symlinks, preferencias, conflictos, permisos y fases interrumpidas. Auditoría de subprocess impide mutadores. Nueva integración VISUAL/LOCAL/TARGET NOT_RUN; no se repite la prueba real en esta entrega. Suite completa: 52 PASS / 0 FAIL / 0 SKIP / 1 NOT_RUN (53 casos).

## Rollback / retirada
Sólo propiedad acreditada; contrato y comandos en docs/core-application.md. Rollback de metadatos/cambios parciales mediante journal de emergencia únicamente si pre/post siguen reconocibles. No restauración ciega sobre terceros. La vuelta del runtime requiere gate de recarga separado.

## Riesgos
No hay transacción filesystem global ni CAS de kernel ante escritores ajenos. Watchers pueden observar estados intermedios; módulo precede a conexión al aplicar y retirada invierte esa dependencia. Estado interno inicial ligado al checkout; conservarlo si se aplica. Código personal ambiguo, sombras, loaders nuevos o bloques Cristal históricos pueden bloquear/impedir una adopción funcional; no se limpian aquí.

## Decisiones pendientes de Diego
Local Test Gate con candidato/plan concretos; adopción de bloques Cristal históricos si procede, sin duplicar reglas. Distribución/licencia/visibilidad permanecen aplazadas. No hace falta otra decisión de producto para cerrar las primitivas autorizadas.

## Evidencia
Fixes: Lua 6c5c3ea y TOML/aceptación en la misma rama. Ocho casos nuevos cubren stock/extensiones/guard/comentarios/duplicados/orden, apply/rollback con bytes ajenos, `[omafiles] glass = true`, arrays/multilínea/NaN, consumidor stock y colisiones de nombres, 62 coincidencias sin escritura/original falso, actualización/conflicto/reemplazo/retirada y recovery sólo de metadatos. Check PASS; suite completa aislada 52 PASS / 0 FAIL / 0 SKIP / 1 NOT_RUN. Core/manifiesto/target model sin cambios. No hubo IPC, apply real ni escritura de escritorio en los fixes.

Revisión independiente de lectura por review_readonly: operador Lua indivisible, discrepancias TOML/stock, colisiones flat, NaN ajeno y state_operation caducado corregidos y cubiertos. Un negativo nuevo falló inicialmente por construcción incorrecta del fixture (tabla repetida) y dos aserciones mal ubicadas; se corrigieron las pruebas, sin rebajar el bloqueo. La validación histórica no se promociona a LOCAL/VISUAL nueva.

Implementación local: commit 34b98fd, `Implement scoped Core application and recovery`, sobre feature/core-apply desde main @ 28b0e6c; sin merge. check PASS y suite completa precommit: 44 PASS / 0 FAIL / 0 SKIP / 1 NOT_RUN (45 casos), incluye suite ARQ-001/002/003/DEV-001 y ejecución portátil desde copia temporal. Salida local en build/arq004-final-precommit-tests.txt. Tras commit, check PASS y test_apply_prepare_partial_failure_journal_recovery_and_death PASS.

Revisión independiente de lectura por review_readonly, sin ejecución de pruebas: siete problemas corregidos con negativos (descriptor redirigido, origen corrupto, comentario inline, carga ya eliminada, orden Lua, permisos y metadatos alterados del mismo tipo). Dictamen sin hallazgos bloqueantes identificados; no se atribuye al revisor la suite. La recuperación de una preferencia local posterior reemplazada explícitamente también tiene prueba específica.

Fallos intermedios se investigaron: sintaxis inicial del helper y expectativas de tests (valor ya restaurado no debe ser conflicto; una edición de fixture afectaba varios tokens accidentalmente). No se rebajaron protecciones ni se convirtió NOT_RUN en PASS. Aceptación acreditada: STATIC/UNIT/ISOLATED_INTEGRATION; VISUAL/LOCAL/TARGET NOT_RUN. No se escribió configuración ni se invocó la sesión real. Procedimiento y comandos exactos en docs/core-application.md, pendientes de Local Test Gate. Los hashes de tres loaders instalados se reconfirmaron por lectura; no es una prueba de runtime.
