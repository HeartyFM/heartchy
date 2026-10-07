# Desarrollo de Heartchy

## Autoridad y ubicación del trabajo

Diego / Hearty_FM dirige producto. Decide qué funciones entran, comportamiento visible, defaults importantes, obligatoriedad/opcionalidad, cambios de arquitectura, dependencias relevantes, nuevas operaciones privilegiadas, efectos destructivos y publicación. Una recomendación del agente no constituye decisión de Diego.

Dentro de un alcance aprobado, el implementador investiga, compara alternativas, decide nombres/helpers y otros detalles internos reversibles, implementa y corrige bugs sin pedir permiso por cada edición. Un cambio que altera comportamiento no decidido vuelve al gate pertinente. Las autorizaciones explícitas previas valen dentro de su alcance; registrar su referencia evita pedirlas otra vez.

| Lugar | Responsabilidad |
|---|---|
| [AGENTS](../AGENTS.md) | Reglas globales y rutas a procedimientos |
| `agents/skills/*.md` | Cómo actuar ante cada tipo de trabajo; lectura selectiva por trigger |
| `docs/` | Contratos, razones y referencias, sin copiar los procedimientos |
| [plantilla](../work/FEATURE_TEMPLATE.md), `work/features/<slug>.md` | Objetivo, aceptación, responsable, decisiones y evidencia de una tarea |
| [STATUS](../STATUS.md) | Baseline, arquitectura activa, trabajo abierto/bloqueado y siguiente paso |
| `build/` | Candidatos y evidencia generada ignorados por Git; no fuente editable |

Las once Skills permanecen separadas: elección de subsistema, privilegio, migración, evaluación visual y publicación tienen precondiciones diferentes. Son guías Markdown locales descubiertas por AGENTS; no se instalan en el catálogo global ni se añade un framework de agentes. Se mantienen pequeñas por referencias a contratos comunes.

## Contrato de Feature

Toda función nueva o trabajo importante tiene un documento desde la [plantilla](../work/FEATURE_TEMPLATE.md). Su ID estable es `HCY-<slug>`; un ID de tarea externa, como HEARTCHY-ARQ-DEV-001, se conserva en decisiones aplicables. El slug no representa una versión. La plantilla es la definición de campos; `N/A` evita prosa artificial cuando algo no aplica. `PENDIENTE` significa desconocido y no una aprobación. No implementar sobre comportamiento esencial pendiente.

El documento coordina subsistemas; no contiene copias del código. Responsable y escritores se asignan al iniciar el trabajo. Evidencia: revisión/commit o hashes si no existe commit, entorno, nivel, comando/acción, resultado y artefacto; aprobación: quién, fecha, referencia a la instrucción y alcance/revisión autorizados. No almacenar conversaciones completas, secretos o logs privados. Un cambio material invalida la evidencia/aprobación afectada hasta revisarla.

<a id="estados"></a>
## Estados y bloqueo

| Estado | Hecho que permite registrarlo; nunca automático |
|---|---|
| `DESIGN` | Documento de objetivo/diseño; implementación aún no aprobada. Puede contener investigación y preguntas abiertas |
| `IMPLEMENTED` | Hay código dentro del alcance autorizado y rutas/revisión identificadas; no implica pruebas |
| `ISOLATED_TESTED` | Pasaron las pruebas aisladas requeridas para ese alcance, con resultados; no implica escritorio |
| `LOCAL_TESTED` | Esa revisión fue probada en Diego con autorización y evidencia real |
| `APPROVED` | Diego acepta expresamente el resultado identificado para Heartchy; distinto de autorizar implementación |
| `RELEASED` | Incluido en una release publicada identificable y autorizada |
| `RAFA_TESTED` | Esa release/Feature fue validada realmente en Rafa, con revisión, entorno y resultado |

No es una promoción automática ni una obligación de inventar pasos: documentación/CLI pueden no necesitar VISUAL/LOCAL; anotarlos N/A y mantener evidencia de los hitos alcanzados. Una aprobación puede existir sin prueba local cuando ésta no corresponde, pero no crea LOCAL_TESTED retroactivo. El estado resume el último hito acreditado, no demuestra todos los anteriores por transitividad. El registro de evidencia conserva cada hito y sus límites.

`BLOCKED` suspende el avance cuando falta una decisión/dato/entorno necesario: conservar `Último estado alcanzado`, indicar causa concreta, responsable de resolverla y trabajo independiente posible. No rebajar ni borrar resultados previos. Al resolverlo, registrar evidencia y volver al último estado válido antes de avanzar. El CLI no cambia estados ni aprueba gates.

<a id="gates"></a>
## Gates de aprobación

| Gate | Antes de qué | Qué debe poder revisar Diego |
|---|---|---|
| Product Gate | Implementar una función con objetivo/comportamiento no decidido, o ampliar alcance | Objetivo, comportamiento/defaults, opcionalidad, alternativas relevantes y aceptación |
| Privilege Gate | Introducir operaciones privilegiadas nuevas | Operación exacta, motivo, límite de autoridad, amenazas y recuperación |
| Local Test Gate | Modificar o conducir la instalación/sesión real de Diego para probar | Revisión/candidato concreto, diff, efectos, backups, pasos, retirada y criterio para detenerse |
| Release Gate | Publicar | Resultado aceptado, candidato identificado, pruebas/compatibilidad, notas y límites; condiciones de distribución explicitadas; no inferir licencia libre |
| Destructive/Migration Gate | Aplicar una transformación que retire/sustituya estado significativo | Precondiciones, contenido afectado, conflictos, preimages, recuperación y preservación posterior |

Los gates pueden coincidir en una aprobación explícita que cubra sus alcances; ninguno salta incompatibilidades ni autoriza archivos fuera de propiedad. Un reemplazo seleccionado en `plan` sigue requiriendo la aprobación al aplicarse de [ARQ-002](architecture.md#politica-arq-002). Pruebas aisladas autorizadas y decisiones técnicas internas no necesitan otra aprobación. Preparar trabajo concreto y revisable antes de solicitar cada gate; continuar lo independiente mientras una decisión esté abierta.

## Código y Git

| Clase | Fuente actual o futura cuando exista trabajo aprobado |
|---|---|
| Cristal | `core/hypr/heartchy.lua`, `core/shell/cristal.toml`, `core/shell/settings-intent.json` |
| Inventario/contratos | `core/manifest.json`, [arquitectura](architecture.md) |
| Herramientas | `tools/`; comparación en `heartchy-plan.py` y `heartchy-lua-plan.py` |
| Comando de producto | `bin/heartchy-*`, sin sustituir omarchy-* |
| Interfaz propia | `shell/`, fuera de Core si requiere plugin y con aprobación separada |
| Backend persistente | `services/`, sólo tras justificar persistencia |
| Transformación de estado | `migrations/`, espacio Heartchy propio, cuando exista una necesidad real |
| Pruebas/investigación | `test/`, registro de [contratos](upstream-contracts.md) y evidencia acotada |

`bin/`, `shell/`, `services/` y `migrations/` no se crean en esta entrega. No se importa el escritorio para una release ni se cambia un hash sólo para silenciar aceptación. El stage actual genera exclusivamente el Core y sus documentos de contrato/procedencia; no es un empaquetador de futuras Features.

`main` es la línea integrada. Cuando haya historial: `main → feature/<slug>` o `fix/<slug> → implementación → pruebas → revisión → aprobación correspondiente → merge`. Sin ramas permanentes develop/staging/production. Una rama no es instalación; merge no instala ni publica. Procedimiento de commits posterior: con autorización e identidad real, revisar `git status --short`, `git diff --check`, seleccionar rutas con `git add -- <rutas>`, revisar `git diff --cached` y `git commit`. Una intención por commit, mensajes breves, sin mezclar refactorizaciones grandes ajenas. No inventar identidad ni historial. El registro inicial de Heartchy Development Foundation tiene autorización de Diego para commits locales; estado y evidencia vigentes en STATUS y el documento de trabajo. Ningún commit concede permiso para remoto, push, tag, release o instalación.

## Paralelismo

Una Feature tiene un responsable de integración y un escritor por subsistema. Registrar áreas antes de delegar; agentes paralelos no editan los mismos archivos. Cambios independientes pueden usar ramas/worktrees separados; la investigación puede ser paralela y la revisión de sólo lectura puede acompañar implementación. El responsable integra después de revisar las diferencias; no hace falta infraestructura de locking. Registrar quién revisó: revisión propia no se denomina independiente.

## Herramientas existentes

```sh
./tools/heartchy-dev --help
./tools/heartchy-dev check
./test/all
./tools/heartchy-dev feature new <slug>
./tools/heartchy-dev stage --output build/<nombre-nuevo>
```

Sustituir los metavariables entre ángulos. `feature new` crea sólo `work/features/<slug>.md` desde la plantilla, con DESIGN y pendientes explícitos. Slug: 1–64 caracteres ASCII en minúsculas/números, primer carácter letra, grupos separados por guion simple. Rechaza existencia previa, escapes y enlaces; no crea código, rama ni commits, no llama a Git ni al escritorio. CWD independiente. Ayuda/argumentos inválidos sin efectos. No existe `feature check`: el `check` global valida routing, plantilla y referencias, pero no certifica decisiones ni aprobaciones humanas.

Ejemplos ejecutables con el candidato existente (sin escrituras en destinatarios):

```sh
./tools/heartchy-dev plan --candidate build/arq003-review --target test/fixtures/planner/conflict --resource shell_tokens --keep-local shell_tokens:menu.background-alpha
./tools/heartchy-dev plan --candidate build/arq003-review --target test/fixtures/planner/conflict --resource shell_tokens --prefer-heartchy shell_tokens:menu.background-alpha --format json
./tools/heartchy-dev plan --candidate build/arq003-review --target test/fixtures/planner/lua-first --resource hypr --format json
```

En una copia sin builds, generar primero un stage nuevo y usar su ruta. Plan, formatos y `--recheck` permanecen definidos sólo en [arquitectura](architecture.md#politica-arq-002). `check`/plan no escriben; stdout puede guardarse explícitamente en un archivo nuevo bajo build. El candidato no es fuente del siguiente. Aplicación/retirada explícitas y Local Test Gate del Core: [procedimiento ARQ-004](core-application.md); contrato único en arquitectura.

## Ejemplo real y ejemplo futuro

Cristal es el primer trabajo real: fuentes únicas y nueve candidatos, planificación mínima con preferencias conservadas, tests aislados y evidencia histórica limitada. El nuevo punto de carga no tiene prueba gráfica nueva; [arquitectura](architecture.md#lua-arq-003) define el límite. No tratar lo pendiente como instalado.

**Heartchy Power Manager — sólo ejemplo de recorrido, sin diseño técnico ni implementación:** Diego propone la idea → documento Feature → investigación selectiva de interfaces Linux/Omarchy → Diego decide objetivo/comportamiento → determinar si requiere CLI, servicio, UI o root → leer las Skills de esos tipos → Product/Privilege Gate si corresponden → rama `feature/power-manager` cuando haya historial → implementación autorizada → UNIT/ISOLATED_INTEGRATION y revisión → resultado concreto para Local Test Gate → prueba real/restauración y VISUAL si corresponde → aceptación de Diego → merge → preparación y Release Gate → publicación futura → prueba real autorizada en Rafa. Ninguno de esos pasos decide ahora backend, dependencias, root, defaults ni UI. No se genera un documento Power Manager como si fuese trabajo activo.

La [Skill principal](../agents/skills/feature-development.md) contiene el procedimiento; las [prácticas adaptadas](upstream.md#desarrollo-dev-001) y su [evidencia fijada](development-upstream.json) explican su origen. Evidencia y niveles de prueba en [testing](testing.md).
