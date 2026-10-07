# Heartchy Development Foundation — registro local

ID: HCY-development-foundation
Nombre: Registro de Heartchy Development Foundation
Estado: ISOLATED_TESTED
Último estado alcanzado: ISOLATED_TESTED
Bloqueo: N/A
Responsable: /root; revisión independiente review_readonly

## Objetivo
Registrar Heartchy Development Foundation como baseline Git local coherente, tras revisión y pruebas; conservar el alcance ARQ-001/002/003/DEV-001.

## No objetivos
Remote, push, GitHub, tags, releases, instalación, apply/update, paquetes, servicios, plugins, Power Manager, cambios de escritorio o continuación automática de la siguiente fase.

## Decisiones de Diego aplicables
Autorización de revisión final, correcciones pequeñas, documentación y primeros commits LOCALES en esta sesión del 2026-10-04. Identidad de autor proporcionada por Diego; usarla sólo en comandos de commit, sin configurar globalmente ni autenticar servicios.

## Tipo de Feature
Cierre de baseline y documentación; ninguna Feature nueva del escritorio.

## Subsistemas afectados
Repositorio completo para clasificación/versionado. Correcciones sólo en documentación/estado y comentarios de .gitignore. Responsable escritor /root; review_readonly revisa sin editar.

## Integración con Omarchy
Sin cambios. Contratos de configuración y planificación ARQ-001/002/003 conservados.

## APIs/contratos utilizados
check, stage, plan y feature new existentes; Git local para registrar el trabajo. Ninguna API nueva de Omarchy.

## Persistencia
Fuentes y documentación en Git local. Resultados de esta revisión bajo build/, excluidos del historial. No cambia el estado de ejecución del usuario.

## Privilegios
N/A para el baseline; sólo permiso para crear el aislamiento Bubblewrap de las pruebas, sin acceso a la sesión real.

## Dependencias
Las existentes; no se instala nada.

## Compatibilidad conocida
Check y suite aislada acreditan únicamente sus contratos. La integración gráfica nueva del Core continúa NOT_RUN; instalación, publicación y Rafa no probados.

## Criterios de aceptación
Árbol registrado por intención coherente, sin secretos/artefactos; check y suite pasan; contratos conservados; diff cached sin errores antes de cada commit; pruebas posteriores y estado final limpio salvo ignorados.

## Pruebas requeridas
git diff --check, check y suite antes de editar; git diff --cached --check antes de cada commit; comprobaciones pertinentes después de cada commit; cierre con check, suite, status y log. No pruebas sobre el escritorio.

## Rollback / retirada
N/A en runtime. Conservar evidencia y candidatos anteriores; el historial local permite revisar/revertir cambios posteriores sin sobrescribir el escritorio. No reescribir commits ni reconstruir entregas antiguas.

## Riesgos
check y la suite integran dependencias cruzadas entre Core, planners, Skills, plantilla, fixtures y docs; separarlas artificialmente por ARQ dejaría estados incompletos.

## Decisiones pendientes de Diego
Licencia/visibilidad, distribución y siguiente capacidad técnica permanecen sin decidir en esta tarea. Nada de ello bloquea el registro local autorizado.

## Evidencia
Revisión inicial: check PASS; suite 31 PASS, 0 FAIL, 0 SKIP, 1 NOT_RUN en build/baseline-initial-tests.txt. Revisión independiente review_readonly sin ejecuciones: corregidas prohibiciones temporales de commits y retirada Lua descrita como línea en vez de bloque completo. Escaneo acotado de candidatos sin indicadores de secretos, ficheros de credenciales ni rutas /home/USER; no certifica ausencia universal de secretos. Fixture JSON inválido deliberado preservado como prueba negativa.

## Auditoría de versionado

| Clasificación | Rutas y motivo |
|---|---|
| VERSIONAR | `core/`, manifiesto, `tools/`, `test/` y fixtures sintéticos/stock atribuidos: fuentes y contratos necesarios para reproducir validación |
| VERSIONAR | AGENTS, README, NOTICE, STATUS, `docs/`, `agents/skills/`, plantilla y documentos relevantes de `work/`: diseño, procedimiento y evidencia resumida |
| VERSIONAR | `docs/provenance.json`, `docs/upstream-evidence.json`, `docs/development-upstream.json`: metadatos acotados de procedencia/investigación, hashes y referencias; sin logs privados ni configuración personal completa |
| NO VERSIONAR | `build/`: candidatos, verification JSON generados, logs, capturas/vídeos, backups/preimages, descargas de consulta y temporales; toda evidencia privada permanece fuera del historial |
| NO VERSIONAR | Cachés/bytecode Python y `.DS_Store`; .gitignore conserva reglas existentes con comentarios, sin ocultar fuentes |

Los candidatos antiguos mantienen su identidad histórica sin commit; crear HEAD no los convierte retroactivamente en releases. No se exporta la colección privada de validación de Diego.

## Intención de los commits

1. Base ejecutable completa: fuentes Core y herramientas/planners, junto a workflow, pruebas, fixtures y documentación que ya requieren. No se recrea una versión intermedia anterior de ARQ-001/002/003.
2. Cierre documental de la auditoría y validación posterior al primer commit, con su identidad real. Es trabajo nuevo verificable, no una división retrospectiva ficticia entre entregas.

## Registro y validación del baseline

- Commit inicial real: `b99dd9610ca829047e8d82c115716c95e47649aa` — Establish Heartchy development foundation. Registra 76 archivos; diff cached comprobado antes de crearlo. Autor/committer suministrados por Diego sólo mediante opciones de ese comando, sin configuración global ni autenticación externa.
- Después de ese commit: `./tools/heartchy-dev check` PASS; `./test/all` = 31 PASS, 0 FAIL, 0 SKIP, 1 NOT_RUN. Informe local `build/baseline-post-first-tests.txt`, SHA-256 `f1bf61836ca91470471b5df9744268bf6e05c070ec0cbb8bad8003759ccd6d1d`. La integración gráfica nueva del Core es el NOT_RUN; no se ejecutó sobre Diego.
- El commit documental de cierre registra estos hechos, sin modificar Core, herramientas, tests ni contratos. Su identidad corresponde al historial Git, sin autorreferencias inventadas; el cierre final repetirá check/suite y verificará árbol limpio. Resultados finales locales quedan bajo build, no dentro del commit.
- No se crearon remotos, tags, release, instalación ni operaciones sobre el escritorio. Rafa no está probado. Los candidatos/evidencia anteriores permanecen ignorados e intactos; su procedencia no se reasigna al commit nuevo.
