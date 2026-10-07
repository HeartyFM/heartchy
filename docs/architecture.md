# Arquitectura propuesta — Cristal Core

## Alcance, fuentes y propiedad

Heartchy es un repositorio independiente de desarrollo, no una copia del equipo ni un fork completo de Omarchy. My Omarchy conserva la memoria del proyecto amplio; OmaPacks queda como legado/referencia. No se importan sus árboles. Una función futura puede ser un comando, una automatización o una interfaz: no necesita convertirse en paquete, daemon o plugin.

| Área | Fuente editable / propiedad | Resultado o estado |
|---|---|---|
| Cristal | `core/hypr/heartchy.lua`, `core/shell/cristal.toml`, `core/shell/settings-intent.json` | Única definición de los recursos propios |
| Inventario | `core/manifest.json` | Hashes, claves administradas y contratos; ninguna operación ejecutable |
| Herramientas | `tools/heartchy-dev`, `tools/heartchy-plan.py`, `tools/heartchy-lua-plan.py`, `tools/lua-contract.lua` | Check, stage y planificación simulada; sin aplicación |
| Pruebas | `test/` | Fixtures stock atribuidos y modelos explícitos; nunca recursos desplegables |
| Investigación | `docs/provenance.json`, `docs/upstream-evidence.json` | Resumen acotado/hashes; no dependencia de la colección original |
| Build y evidencia nueva | `build/<nombre>/`, ignorado por Git | Candidatos e informes generados; no fuentes versionadas alternativas |
| Ejecución futura | Configuración del usuario | Destino/preferencias; no origen de cada release |

El historial futuro pertenece a Git. No habrá directorios versionados `v1`, `v2`, `candidate` o `delivery` con duplicados editables. Tampoco se editará `~/.local/state/omarchy/current/theme` como fuente.

## Contratos de integración

Estos son destinos **propuestos**, no escrituras autorizadas ni realizadas por las herramientas de esta entrega. Las rutas `~/.config` reflejan los consumidores stock comprobados; no se promete soporte XDG alternativo que estos cargadores no ofrecen.

<a id="hypr"></a>
### Hyprland

`core/hypr/heartchy.lua` → bootstrap y API Lua stock, helper `o.window` → futuro `~/.config/hypr/heartchy.lua`.

Una carga `require("hypr.heartchy")` al principio del `looknfeel.lua` existente es el punto mínimo propuesto. Omarchy ya carga ese archivo después de defaults y del tema. Las preferencias escritas después conservan precedencia para valores escalares. Heartchy poseería su módulo y reconocería un bloque de carga identificable; no poseería el archivo personal completo. La planificación acotada de esa integración se especifica en el [contrato ARQ-003](#lua-arq-003).

Claves exactas en `manifest.resources[hypr].managed`: bordes generales/de grupo, perfil de blur, regla selectiva, opacidad del compositor para el tag `terminal` y animación `workspaces`. Son el inventario del contenido permitido del módulo, **no unidades para mezclar propiedades del destinatario**: ARQ-003 administra el módulo completo por bytes. Se quitó únicamente `rounding=0` de la importación por ser stock y estar fuera de los nueve candidatos. Se conservan vibrancy/contrast/brightness del perfil validado. `slidevert` es una preferencia visual validada con dwindle; no se afirma un bug vigente de Scrolling.

El bootstrap invalida `package.loaded` para `hypr.*` y reconstruye `package.path`. La fuente de Hyprland 0.56.2 estudiada también invalida módulos y limpia el motor de reglas durante una recarga válida. El test de fixtures verifica la recarga del módulo y el modelo de registros; no ejecuta el compositor.

**Las reglas no son escalares.** `o.window` transmite el match a `hl.window_rule`; no añade un nombre ni desregistra reglas anteriores. Cada ejecución de una regla anónima registra otra regla. En el consumidor de Hyprland, una regla con el mismo nombre reutiliza su objeto: tampoco debe suponerse una sustitución total de todos sus campos. `require` evita ejecutar dos veces el módulo en una carga, pero llamar directamente al archivo repetidas veces no ofrece esa protección. La precedencia de matches solapados y el multiplicador de opacidad requieren prueba gráfica específica.

Antes de cualquier aplicación futura sobre el escritorio actual hay que revisar los bloques Cristal que aún estén en su `looknfeel.lua`. Añadir el require y dejar aquellos bloques podría mantener dos autoridades y duplicar la regla anónima de terminales. ARQ-003 conserva todas las declaraciones personales y advierte que no comprueba estos conflictos semánticos; no elimina ni reordena reglas para obtener precedencia artificial. No existe un transformador de adopción de bloques históricos en esta entrega.

Desactivación futura: retirar exclusivamente el bloque de carga gestionado completo (BEGIN, require y END) y el módulo intacto de Heartchy, tras comprobar propiedad y ediciones posteriores; conservar el resto del archivo. Una carga equivalente sin propiedad acreditada no se retira automáticamente. La recarga completa que reconstruya valores y reglas requiere autorización propia. No basta con borrar un archivo o poner blur=false mientras siguen vivas las reglas. La retirada estructural está implementada en ARQ-004; no recarga el compositor.

<a id="shell_intent"></a>
### Shell JSON

`core/shell/settings-intent.json` → intención de `bar.transparent=true` → edición controlada sobre `~/.config/omarchy/shell.json`.

**No es un shell.json instalable.** Omarchy selecciona el JSON del usuario válido con `version: 1` como configuración completa; no hace deep merge con el stock. La intención no contiene versión stock, bar.id, layout, widgets, reloj, idle ni plugins. La barra stock es un requisito comprobable del entorno, no un cambio de identidad escondido en el Core.

La CLI instalada ofrece `omarchy bar transparent true` y `omarchy bar use omarchy.bar`. La segunda elimina `bar.id` para utilizar el identificador predeterminado. Se inspeccionaron, no se ejecutaron. El helper nativo conserva claves ajenas mediante una mutación jq, normaliza la estructura y reescribe el JSON; llama a reloadConfig. Por ello no puede invocarse durante un stage ni para preparar silenciosamente una transición de barra.

Para una aplicación futura: JSON válido → comparar sólo la intención y preservar claves ajenas; ausente → la CLI puede partir del stock **del destino**, pero la creación de un JSON completo y su pérdida de herencia futura deben quedar explícitas; inválido, vacío o con versión no admitida → detenerse y conservar el archivo, aunque el shell use un fallback en memoria. Nunca reemplazarlo por un layout capturado en Diego. Leer y validar antes de usar la CLI, porque su normalización no reemplaza una política de conflictos.

Desactivación futura: restaurar únicamente el valor/base de `bar.transparent` si sigue igual al último aplicado. Si el usuario lo cambió después, preservar su decisión. No restaurar un backup completo ni regenerar el layout.

<a id="shell_tokens"></a>
### Shell TOML y theming

`core/shell/cristal.toml` → `Color.parseShell/mergeShell`, `Style.applyShellValues`, consumidores `Border` → propuesta: edición controlada de las claves indicadas en `~/.config/omarchy/shell.toml`.

Se conservan como fuente única los tokens neutrales validados, sin paleta/fondo/fuente fija. El consumidor mezcla el TOML generado del tema con el personal **por clave** y el personal gana. No hay includes, un directorio personal de overlays ni API genérica persistente de tokens. `shell applyTheme` actualiza la base en memoria y no implementa una tercera capa persistente.

| Alternativa stock | Ventaja | Límite comprobado |
|---|---|---|
| Editar sólo claves del TOML personal | Mantiene herencia de todas las demás claves y nuevos defaults del tema; sobrevive a cambios de tema | Comparte archivo y claves con preferencias locales; exige conservar comentarios y detectar conflictos |
| `themes/<slug>/shell.<sección>.toml` | Poseer un fragmento independiente para un tema | Reemplaza la sección entera; acoplado al slug; usuario TOML gana después |
| `themed/shell.<sección>.toml.tpl` | Generación transversal sin copiar template completo | Un archivo ya suministrado por el tema impide generar ese output; reemplazo por sección, no mezcla; necesita generación de tema |
| Copiar `shell.toml.tpl` entero | Control total de lo generado | Congela defaults ajenos y amplía propiedad sin necesidad |

**Decisión técnica propuesta para revisión:** futura edición por claves del TOML personal. Es la menor operación que reproduce la semántica actual y conserva herencia por clave; no se escoge theming por estética arquitectónica. **Edición acotada implementada en ARQ-004; aplicación personal pendiente.** No hay dos motores alternativos. La decisión de Diego sobre preferencias se especifica únicamente en la [política ARQ-002](#politica-arq-002).

Las mismas claves físicas no pueden representar simultáneamente una capa Heartchy y otra capa local. La separación conceptual de tres capas no crea tres niveles de precedencia en el consumidor. El editor acotado es consciente del texto: `tomllib` lee, pero no conserva comentarios al reserializar ni implementa escritura; no se usará un round-trip indiscriminado. Detecta sintaxis que acepte un parser y no el parser limitado de Shell, secciones duplicadas o valores ambiguos. No añadir claves inventadas `heartchy.*`.

La retirada futura elimina/restaura únicamente claves aún iguales a lo aplicado, respeta cambios posteriores y preserva secciones/comentarios ajenos. `[hyprland]` en este TOML sólo define roles de Shell; el compositor sigue configurándose por Lua. Lock/polkit son tokens de apariencia existentes: no se modifica autenticación ni se acredita su funcionamiento con esta entrega.

## Compatibilidad y ciclo de vida

Estados separados:

- **PROBADO HISTÓRICAMENTE:** los nueve candidatos originales en Omarchy 4.0.4-1.1, omarchy-settings 4.0.4-1, Hyprland 0.56.2-2, Quickshell 0.3.1-1, `/usr/share/omarchy`, dwindle y barra stock. Alcance exacto en provenance; no prueba Rafa, todos los temas, autenticación o energía.
- **PROBADO AISLADAMENTE:** sólo lo que registre el runner de esta entrega: declaraciones, carga/cache mediante fixtures, alcance y staging. No es prueba gráfica del nuevo punto de carga ni del editor.
- **NO PROBADO:** otras versiones, nueva integración gráfica, instalación personal, Rafa y publicación. Una versión numéricamente mayor no obtiene compatibilidad automática.
- **INCOMPATIBLE CON CAUSA:** un destino sin Lua/API/helper requeridos, un consumidor que ya no reconozca los tokens, o una barra ajena al contrato. JSON inválido/conflictos son bloqueos locales, no prueba de incompatibilidad de toda una versión. No se ha declarado incompatible una versión completa sin probarla.

Requisitos verificables: resolución/invalidation de `hypr.*`; APIs `hl.config/layer_rule/animation` y `o.window` con el tag stock `terminal`; limpieza/identidad de reglas conocida; semántica de JSON v1 y CLI de transparencia; mezcla TOML por clave y roles actuales; `omarchy.bar` activa. La igualdad de algunos hashes de archivos no identifica un paquete entero.

Un recurso nuevo sin estado persistente no exige por sí mismo una migración. Renombrar una clave, adoptar bloques ya aplicados o cambiar un formato persistente sí puede exigirla. Paleta, selección de tema, monitores, hardware y preferencias ajenas siguen siendo decisiones locales, fuera del Core.

Para futuras migraciones propias: idempotentes, ordenadas, con precondiciones y evidencia de resultado; registrar éxito únicamente después de comprobarlo. Estado y registro bajo un espacio Heartchy independiente, nunca dentro de las migrations ni los marcadores de Omarchy. Una interrupción deja la operación pendiente; no continuar sobre estado incompleto. No se ha creado directorio ni runner de migraciones ficticias.

La comparación de tres estados está implementada para simulaciones según la [política ARQ-002](#politica-arq-002). ARQ-004 registra sólo cambios escritos o referencias coincidentes aceptadas y sus bases, no todo el escritorio. El rollback distingue ambas procedencias; nunca pisa ediciones posteriores por defecto.

Preparar fuera de rutas observadas, verificar de nuevo los preimages antes de activar y planificar el orden de escritura/arranque con autorización explícita. Renombrar atómicamente un archivo no hace atómico un conjunto ante watchers. Una transición que cambie el contrato de la barra exige arranque limpio; esta entrega no hace transiciones ni mantiene un proceso que reimponga valores.

Al cambiar Omarchy: registrar versiones y hashes nuevos; comparar únicamente cargador/cache/helper Lua, registro/limpieza de reglas, selección JSON/CLI, parser/merge TOML/tokens, y cualquier punto público realmente consumido. Ejecutar pruebas específicas, repetir prueba gráfica desechable y anotar contratos cambiados antes de promover el estado de compatibilidad. No hacer rebase sobre todo Omarchy ni volver a importar el escritorio. `omarchy update` sigue independiente; no instalar un hook post-update para reimponer Heartchy.

<a id="politica-arq-002"></a>
## Política aprobada y planificación — HEARTCHY-ARQ-002

**Decisión de Diego:** respetar preferencias locales por defecto y permitir solicitar valores Heartchy por ajuste o conjunto explícito. La selección no aprueba una aplicación. El aplicador exige el plan revisado con sus cambios exactos, aprobación vinculada a su hash, respaldo y recuperación; no puede saltarse validación, incompatibilidades o propiedad de archivos mediante esa selección. No hay `--force`.

Ésta es la única definición normativa de la política; los flags y campos de salida implementan este contrato. B es el último valor administrado o referencia coincidente aceptada tras una aplicación exitosa, C es la configuración actual y P es la propuesta validada del candidato. Ausencia de estado, ausencia de una clave y valor desconocido son estados diferentes. Coincidir con Heartchy no acredita que lo haya creado ni concede propiedad sobre bytes automáticamente.

| Condición, en orden | Decisión | Resultado previsto |
|---|---|---|
| Datos inválidos, contrato incompatible o información insuficiente | `BLOCKED` | No cambia; las selecciones no eliminan el bloqueo |
| C=P | `NO_CHANGE` | No escribe configuración. Sin B, Shell puede proponer aceptar una referencia coincidente mediante el apply aprobado; nunca afirma haber creado el valor |
| Selección explícita `--keep-local` | `LOCAL_PRESERVED` | Conserva C y cierra esa discrepancia |
| Selección explícita `--prefer-heartchy` | `REPLACEMENT_REQUESTED` | Solicita P, con aprobación y backup pendientes |
| Sin B y clave explícita ausente | `MANAGED_CHANGE` | Propone añadir sólo esa clave, identificada como primera adopción |
| Sin B y valor existente distinto | `LOCAL_PRESERVED` | Conserva C; primera aplicación no presume propiedad |
| C=B y P distinto | `MANAGED_CHANGE` | Cambio administrado aplicable a nivel de clave |
| P=B y C distinto, incluida eliminación local | `LOCAL_PRESERVED` | Conserva C |
| B, C y P difieren | `CONFLICT_PENDING` | Conserva C por defecto; convergencia pendiente de elección explícita |

El significado de «aplicable» es una decisión de datos dentro de la simulación; no acredita integración gráfica ni permiso para escribir. Si el usuario retiró una clave administrada, `absent` es su cambio local y no una invitación a reponerla. Añadir una clave ausente de TOML describe una diferencia física: su valor heredado/efecto visual puede ser desconocido. La selección de un recurso abarca exclusivamente sus claves enumeradas; selectores desconocidos, contradictorios o fuera de `--resource` fallan.

### Entradas explícitas y contratos por formato

`plan --candidate build/<candidato> --target test/fixtures/planner/<caso>`; alternativamente el target puede ser `build/simulations/<nombre>`. Todos los paths relativos pertenecen al checkout, no al CWD. Las rutas físicas externas sólo se admiten mediante el descriptor explícito de ARQ-004; se rechazan `..`, enlaces y hardlinks. Una copia temporal del checkout ofrece el mismo mecanismo. `plan` no escribe archivos; text/JSON van a stdout. Los fixtures son datos sintéticos, sin capturas del escritorio.

El candidato debe tener un inventario de stage con el payload conocido, tamaños y hashes correctos; además se validan manifiesto y fuentes con los mismos validadores de `check`. No se acepta un `settings-intent.json` suelto como shell.json completo. Los hashes identifican bytes, no autentican una release. Un candidato ARQ-001 existente sigue siendo legible: su documentación histórica no sustituye esta política del planificador actual.

El target contiene `target.json` con `schema_version: 1`, `kind: "heartchy-simulated-target"` y `contracts`. Los contratos Shell son `shell_intent: "omarchy-shell-json-v1"` y `shell_tokens: "omarchy-shell-toml-key-merge-v1"`; los dos contratos Lua se especifican en [ARQ-003](#lua-arq-003). Son contratos **declarados por el fixture**, no detección ni certificación del sistema instalado. Contratos no reconocidos bloquean el recurso. Sólo se leen las rutas fijas siguientes:

| Recurso | Archivos de la simulación | Límite del análisis |
|---|---|---|
| `shell_intent` | `config/omarchy/shell.json` | JSON v1, barra stock; compara sólo `bar.transparent`. JSON ausente exige seed del destinatario y queda bloqueado; inválido tampoco se reemplaza. Layout y claves ajenas nunca aparecen en el plan |
| `shell_tokens` | `config/omarchy/shell.toml` | Compara exclusivamente claves del manifiesto, no secciones completas. Conserva bytes/comentarios sin reserializar. Archivo ausente permite planificar adiciones explícitas; sintaxis fuera del subconjunto stock seguro bloquea el recurso aunque sea TOML general válido |
| `hypr_module`, `hypr_connection` | Módulo y conexión especificados en [ARQ-003](#lua-arq-003) | Dos recursos de planificación derivados de la única fuente Core `hypr`; no mezcla por propiedades ni ejecución del destinatario |

`--resource` limita el análisis a recursos seleccionados, repetible; sin él se muestran los cuatro recursos de planificación. `hypr` es un alias explícito para módulo y conexión. No planifica por extensión archivos arbitrarios ni intenta adivinar preferencias. Lua del **candidato** sí se valida mediante el entorno declarativo restringido existente; no es código del destinatario.

### Estado anterior y salida

`state.json`, opcional en el target, tiene `schema_version: 1`, `kind: "heartchy-managed-state"`, `successful: true`, `application_id` y `resources`. Cada recurso incluye su `contract` y un mapa `values` sólo con claves efectivamente administradas. Cada valor es `{"state":"present","value":...}` o `{"state":"absent"}`. Véase `test/fixtures/planner/conflict/state.json` en el checkout; los fixtures no se transportan en el candidato. Es un formato de simulación, no un registro de instalaciones reales ni una migración implementada.

Sin archivo de estado la fase es `first_application`. Con estado válido es `subsequent_application`; claves no registradas siguen sin propietario. Estado inválido/incompleto o con claves ajenas bloquea, en lugar de degradarse silenciosamente a primera instalación. `plan` nunca escribe estado exitoso ni adopta claves.

La salida JSON `heartchy-change-plan` contiene `resource`, `key`, `base`, `current`, `proposed`, `planned`, `decision` y `reason` por entrada, además de selección y requisitos de aprobación/backup. `base.state=unmanaged` identifica ausencia de propiedad; `unknown` indica conocimiento insuficiente. `inputs` registra SHA-256 de los archivos realmente leídos y un sentinel `exists:false, sha256:null` para ausencias comprobadas; incluye candidato, configuración pertinente, estado, contratos simulados y herramientas. No transporta los archivos personales completos de Shell ni looknfeel. ARQ-003 sí presenta el diff de bytes del módulo sintético: ese recurso se administra como archivo completo.

La salida text presenta esos valores, motivos, resumen y hashes. Código de salida **0**: comparación completada sin bloqueos/conflictos pendientes (un reemplazo aún requiere aprobación futura); **3**: plan con bloqueos/conflictos pendientes; **1**: error de entrada/selector/lectura no recuperable; **2**: argumentos inválidos. Estos códigos son del planificador, no resultados PASS/FAIL de pruebas gráficas.

<a id="lua-arq-003"></a>
### Contrato de integración Lua — HEARTCHY-ARQ-003

Se mantienen las seis decisiones y la política ARQ-002. No existe un editor genérico Lua: `tools/heartchy-lua-plan.py` compara bytes y reconoce un subconjunto cerrado de declaraciones para proponer una única inserción. La fuente Cristal no se duplica; el manifiesto permanece un inventario, no un lenguaje de instalación.

| Recurso / selector | Propiedad, comparación y operación permitida |
|---|---|
| `hypr_module:content` | Archivo completo `config/hypr/heartchy.lua`; B/C/P son fingerprints `{sha256, bytes}` de la última aplicación registrada, archivo actual y fuente del candidato. Operaciones: `create-file`, `replace-file` o `none`; nunca mezcla por propiedades |
| `hypr_connection:load` | Sólo bloque de carga al inicio de `config/hypr/looknfeel.lua`; la operación `insert-prefix` especifica offset **0** y bytes exactos. El resto del archivo se conserva literalmente. No existe reemplazo completo, reparación de marcadores, reordenación ni eliminación de reglas |

Los contratos del target sintético son `hypr_module: "heartchy-lua-module-bytes-v1"` y `hypr_connection: "omarchy-lua-prefix-v1"`. El placeholder ARQ-002 `hypr: "lua-adoption-unresolved"` **no acredita** esos contratos y sigue bloqueado. Tampoco se convierte un viejo registro de propiedades `hypr` en evidencia de propiedad del archivo. Se admiten candidatos ARQ-001/002 con la fuente `hypr` original; la proyección en dos recursos pertenece al planificador, no a un lenguaje de instalación dentro del manifiesto.

El formato de estado exitoso continúa igual: `resources.hypr_module.values.content` registra `present` con fingerprint del archivo aplicado, o `absent`. `resources.hypr_connection.values.load` registra el fingerprint de los bytes exactos del bloque administrado; una base de bloque desconocida queda bloqueada. Los registros sintéticos de pruebas no acreditan ninguna instalación real.

Para el módulo, ausencia inicial permite creación; coincidencia con P no cambia ni adopta propiedad; coincidencia con B permite actualización; una edición local sigue la comparación ARQ-002 y admite elección acotada. La eliminación posterior de un módulo administrado también es un cambio local: se conserva o requiere resolución según B/C/P, no se recrea silenciosamente. Un módulo existente sin base conocida queda local por defecto. Si se conserva contenido diferente del candidato, el plan emite una advertencia explícita de compatibilidad funcional no validada; no convierte esa conservación en un fallo oculto ni interpreta su Lua.

La plantilla de carga tiene una única definición ejecutable en `LOAD_BLOCK` del helper: comentario `BEGIN HEARTCHY: hypr.heartchy v1`, llamada `require("hypr.heartchy")` y comentario `END HEARTCHY: hypr.heartchy v1`, cada uno terminado con LF. Se inserta delante de los bytes originales, sin normalizar su codificación ni sus finales de línea. Una entrada vacía, sólo comentarios o con CRLF puede conservarse exactamente; BOM, NUL, CR aislado o UTF-8 inválido quedan bloqueados para conexión.

**Ubicación comprobada por lectura del instalado:** `config/hypr/hyprland.lua:14` carga defaults; `:19–23` carga monitores/input/bindings/looknfeel/autostart. `default/hypr/omarchy.lua:17,22` aplica looknfeel stock y tema antes de la parte personal. `default/hypr/bootstrap.lua:4–28` invalida caché `hypr.*`, y `:33–38` busca primero en estado generado, después en config y después en Omarchy. Hashes y líneas reconfirmados en `docs/upstream-evidence.json → lua_planning_verification`; no hubo recarga ni prueba del compositor.

Para planificar conexión se reconoce por tokens el prefijo stock de `config/hypr/hyprland.lua`: bootstrap → defaults → monitores/input/bindings/looknfeel/autostart → toggles. No se exige el hash del archivo personal. Después se permiten requires literales únicos de otros módulos `hypr.*` y el guard final conocido de Hyprmoncfg. Comentarios y cadenas se distinguen de instrucciones; orden cambiado, cargas duplicadas/Core adicionales y código fuera de este subconjunto quedan BLOCKED. No se interpreta ni ejecuta código del destinatario. La posición estable sigue siendo byte 0 de looknfeel, después de defaults/tema y antes de preferencias personales. EntryPoint y Hyprmoncfg se conservan literalmente y nunca se administran. Los tres loaders stock del descriptor mantienen sus hashes comprobados; ampliar un prefijo/revisión requiere revisar ese contrato.

Se comprueba ausencia de `state/hypr/heartchy.lua` y `state/hypr/looknfeel.lua`, que podrían ocultar ambos archivos personales según ese bootstrap. Esas ausencias y el entrypoint completo forman parte de `--recheck`. Los contratos del fixture declaran el runtime stock; no prueban que módulos posteriores o una sesión real no alteren la resolución/valores efectivos. No se garantiza semántica de extensiones personales por reconocer su carga literal.

El reconocedor separa comentarios cortos/largos, cadenas entrecomilladas/largas, escapes simples, nombres y puntuación. Después admite únicamente llamadas top-level a `hl.config`, `hl.animation`, `hl.bezier`, `hl.layer_rule`, `hl.window_rule` y `o.window` con tablas/literales, y una carga literal de `hypr.heartchy`. No ejecuta código ni evalúa expresiones. Referencias a variables, condicionales, funciones, alias, cargas indirectas, aritmética/concatenación, escapes no soportados o sintaxis ambigua bloquean con motivo concreto. Se limita cada archivo Lua a 64 KiB y la profundidad de tablas; el módulo sólo necesita bytes, no ese subconjunto sintáctico.

Una carga equivalente literal sin marcadores, antes de cualquier otra instrucción, se reutiliza sin cambios y sin apropiación. Puede usar comillas simples/dobles, paréntesis o una cadena larga literal. Comentarios y cadenas que contienen texto parecido a `require` o a marcadores no cuentan como instrucciones ni marcadores reales. Una carga posterior a declaraciones personales queda bloqueada; no se mueve. Marcadores incompletos, duplicados, alterados, desplazados del prefijo o retirados de un bloque acreditado quedan bloqueados incluso con `--prefer-heartchy`. Un bloque exacto preexistente sin estado se reconoce pero continúa sin propietario acreditado. `looknfeel.lua` ausente queda bloqueado: no se inventa un archivo personal completo.

La conexión depende de los bytes del módulo que quedarían tras el plan. Si el módulo está bloqueado, pendiente de conflicto, conservado ausente o conservado con bytes distintos de P, la conexión queda `BLOCKED` con causa de dependencia. Si se selecciona sólo `hypr_connection`, el módulo se inspecciona como dependencia **sin proponer cambios en él** y debe coincidir ya con P. Una creación/actualización del módulo incluida en el plan permite una conexión condicionada a esa operación; un reemplazo pendiente de aprobación transmite esa condición. No se amplía el ámbito del selector silenciosamente.

Las entradas Lua muestran archivo, operación, decisión, base/actual/propuesta, diff de la propuesta y dependencia. El diff de conexión tiene contexto cero y sólo añade el bloque; no transporta el archivo personal completo. El módulo usa diff textual o representación base64 si sus bytes actuales no son UTF-8. En decisiones conservadas/bloqueadas el diff es una comparación de la propuesta, **no una operación autorizada**. Un plan obsoleto elimina la operación/inserción y marca sus dependencias como no satisfechas.

**Límite:** fingerprints coincidentes y estructura reconocida no prueban carga funcional, reglas sin conflicto ni apariencia. El reconocedor no valida aridad, tipos de opciones ni validez de argumentos para las APIs de Hyprland; su aceptación sintáctica no equivale a que `hl.config` u `o.window` aceptarían una llamada al ejecutarla. Las declaraciones personales posteriores permanecen intactas y pueden sobreescribir escalares o acumular reglas; los módulos anteriores tampoco se evalúan. `functional_validation` permanece `NOT_RUN` en ambos recursos. Prueba gráfica e instalación siguen requiriendo una entrega y autorización separadas.

### Vigencia del plan

Se puede guardar stdout JSON bajo `build/` y repetir la misma operación con `--recheck build/<plan>.json`. Se comparan todos los hashes/ausencias examinados y la selección, incluso si sólo cambió un comentario o una clave ajena del archivo leído. Un cambio produce `STALE` y bloquea todas las entradas del nuevo plan, aun con reemplazos seleccionados. Cambiar candidato, herramienta, contrato, estado o selección también exige revisión nueva. Un hash coincidente no convierte un plan editado manualmente en autoridad: la decisión siempre se recalcula para comprobar su integridad.

La lectura de varios archivos no es una instantánea atómica. `apply` compara nuevamente entradas, decisiones y ausencias contra el plan revisado, y verifica preimages antes de commit y de cada reemplazo. El hash aprobado corresponde al JSON exacto del plan, no a una autorización permanente. El contrato de efectos, propiedad y recuperación está en [ARQ-004](#aplicacion-arq-004).

<a id="aplicacion-arq-004"></a>
## Aplicación controlada — HEARTCHY-ARQ-004

`apply --candidate ... --target ... --state-root ... --plan ... --approve SHA256` es una primitiva explícita, no un updater. No contacta al compositor, Shell, hooks ni servicios. `validate` relee estado administrado; `rollback --approve rollback` retira/restaura solamente propiedad acreditada; `recover --approve recover` recupera una operación interrumpida. No instala herramientas ni administra versiones remotas. Comandos y Local Test Gate: `docs/core-application.md` en el checkout.

### Destinos, autorización y operación

Targets simulados siguen en sus raíces ARQ-002. Un descriptor privado `build/local-targets/<nombre>/target.json` puede señalar explícitamente `config_root`, `shadow_root` y `stock_root`, con los cuatro contratos existentes y `kind: heartchy-local-target`. No hay HOME por defecto. Sólo se mapean los cuatro archivos Core, entrypoint personal y dos posibles sombras Lua; se leen tres loaders stock cuyo hash debe coincidir con la evidencia fijada. Config/shadow deben estar bajo `/home`, `/tmp` o `/sandbox`, corresponder a `.config` y `.local/state` de un mismo HOME explícito y no tener symlinks; config pertenece al usuario. Stock es lectura selectiva de `/usr/share/omarchy` o fixture controlado. Otros roots, enlaces, hardlinks, FIFOs, escapes y permisos no contemplados bloquean. El descriptor no certifica el runtime Shell ni la sesión: requiere revisión de compatibilidad y Local Test Gate.

Se exige state root dedicado `build/state/<nombre>`; no se usa estado de Omarchy. `plan --state-root` lee esa base y su ledger; el viejo `state.json` sintético sigue disponible sólo para planes históricos. `apply` exige plan generado con el mismo root, mismo candidato/destino/selección y herramientas, sin BLOCKED ni CONFLICT_PENDING. Reproduce las decisiones para comprobar su integridad, no para elegir nuevas resoluciones. LOCAL_PRESERVED permanece local, explícito y sin acreditación funcional; no se registra como adoptado. La aceptación Shell de NO_CHANGE se delimita debajo; Lua equivalente sin propiedad nunca se reclama. `--prefer-heartchy` resuelve sólo claves seleccionadas; la aprobación corresponde al plan exacto. No existe force.

| Recurso | Escritura y propiedad | Retirada |
|---|---|---|
| Módulo Lua | Bytes completos propios; sólo creación/actualización/reemplazo seleccionados | Hash aplicado intacto permite restaurar bytes originales o ausencia; edición posterior conserva/conflicta |
| Conexión | Prefijo canónico único; todo el resto idéntico | Sólo prefijo insertado y acreditado; carga equivalente preexistente no se reclama ni retira. No retirar un módulo que siga teniendo una carga no administrada |
| Shell JSON | Sólo bar.transparent; reserialización JSON válida preserva semánticamente claves ajenas | Valor original o ausencia, si intacto; edición posterior conservada. No backup completo como rollback |
| Shell TOML | Líneas simples de claves del inventario; conserva líneas/comentarios ajenos y comentarios inline de claves cambiadas | Valores originales o eliminación de adiciones; secciones creadas vacías se retiran si no contienen comentarios posteriores. Sintaxis ambigua bloquea |

TOML del destinatario se valida con `tomllib` estándar: strings, enteros/float, booleanos, arrays y tablas ajenas se admiten sin convertirlos en recursos Core. Una máscara léxica evita confundir cadenas multilínea o arrays con encabezados/asignaciones. Las claves administradas se leen por tabla/key, sin aplanar nombres literales ajenos con puntos. Además se compara la ubicación de cada asignación Core con la interpretación por líneas de Color.parseShell; un lookalike multilínea o una tabla quoted/dotted ignorada por Shell que interfiera con Core produce BLOCKED, incluso si reproduce el mismo valor. Esta comprobación usa el consumidor instalado leído `shell/Commons/Color.qml:178–198`, hash cc9b62e2eaf8c307aa02206d9320c3d0ca349cf8feed452a6eddf387adaa5320 (coincide con la evidencia instalada registrada; reconfirmado 2026-10-04, no ejecutado).

Sólo los tokens administrados exigen secciones/keys simples y literales que ese consumidor interpreta; spellings ambiguos o tipos incompatibles en esas claves bloquean, aunque sean TOML válido. La fuente `cristal.toml` conserva su validador stock estricto. Los NaN/Inf ajenos se conservan con comparación semántica estable; no se permiten en valores administrados. No hay editor TOML universal ni garantía funcional de secciones ajenas.

### Procedencia: cambio escrito, coincidencia aceptada y preferencia local

- **Cambio escrito por Heartchy:** `owned` contiene el valor/ausencia real previo a la escritura y el aplicado. No significa que Heartchy creara todo el archivo. Si añadió una clave, el original es ausencia; si sustituyó un valor, ese valor real es el original recuperable.
- **Coincidencia Shell preexistente aceptada:** sin B y C=P, el plan conserva `NO_CHANGE`, motivo `ALREADY_MATCHES`, `state_operation: accept-matching-reference`. Sólo apply con aprobación del plan guarda C como referencia en `accepted`, sin escribir el archivo, sin `original`, sin reclamar su creación. `--keep-local` excluye esa clave de la aceptación, incluso si coincide. No se adopta el resto del archivo ni la carga Lua preexistente. `plan` solo no guarda estado.
- **Preferencia local preservada:** queda sin propiedad/referencia nueva; conservarla no acredita compatibilidad funcional. Una referencia ya aceptada puede permanecer como B cuando el usuario se separa de ella; no se actualiza silenciosamente a su nueva preferencia.

Una referencia aceptada permite la comparación B/C/P en próximas actualizaciones y aparece como `base_origin: matching-preexisting`; un cambio escrito aparece como `heartchy-written`. Al primer cambio efectivo de una clave aceptada se captura C como original real y se convierte sólo esa clave en `owned`. Una elección explícita sobre una edición local captura esa edición para retirada. Rollback de una mera aceptación retira únicamente su referencia, aun si el usuario cambió luego el valor: no escribe configuración ni necesita inventar una restauración. Repetir apply del mismo estado/candidato no crea otro journal ni reescribe metadatos. Esto no demuestra aceptación funcional/gráfica de valores heredados.

### Estado y journal privados

`managed.json` mantiene la base compatible con el planificador: contratos, valores/fingerprints aplicados o aceptados y application_id. Una lista opcional `resources.<recurso>.accepted` distingue referencias Shell de cambios escritos; registros anteriores sin ella siguen legibles. `ledger.json` liga esa base por SHA-256 al descriptor exacto del target; separa `owned` (original/applied) de `accepted` (sólo referencia presente), verifica correspondencia y disyunción, y registra identidad del candidato (inventario/plan), tiempo, resultado y existencia previa de archivos escritos. Una preferencia local posterior reemplazada explícitamente pasa a ser el original recuperable; una actualización administrada normal conserva el original de la primera escritura. Sólo guarda bytes originales del módulo completo cuando es necesario restaurarlo. No guarda snapshots del layout ni del looknfeel como estado permanente. La identidad es de candidato local, no de release. Borrar el state root pierde evidencia; no reconstruir propiedad por coincidencia de valores.

Cada operación efectiva tiene UUID y `operations/<id>/journal.json`: identidad del descriptor, hashes pre/post, rutas permitidas, modo, commit observado y restauración. No-op no crea otra operación ni modifica el estado. Los locks excluyen escritores sobre state y carpeta física del target. La autoridad persistente en estado Heartchy liga el target al state root original, sin reclamar preferencias por coincidencia. No bloquean editores no cooperantes. Journal/estado son formato interno inicial, no protocolo público estable.

Prepare calcula todos los resultados, comprueba valores y preservación ajena, guarda pre/post images privados fuera de config y relee sus hashes. Estados PREPARING → PREPARED → COMMITTING → SUCCESS. Sólo entonces se reemplaza cada archivo con rename + fsync; eliminación de archivo propio es unlink. Los archivos de estado forman parte del mismo journal y se registran después de config. SUCCESS requiere readback exacto de todos los postimages. La validación posterior de valores distingue ediciones locales; no valida compositor, aridad Lua, reglas semánticas, apariencia ni autenticación.

Fallo anterior a commit no cambia config. Fallo durante commit intenta restauración condicionada usando el journal; interrupción del proceso deja RECOVERY_REQUIRED para la siguiente operación. `recover` acepta sólo archivos todavía iguales al preimage o postimage registrado. Un tercer estado, preimage necesario ausente, metadatos corruptos o ruta inesperada bloquean y exigen inspección; no sobrescribe para conseguir recuperación aparente. RECOVERED sólo tras comprobar todos los hashes previos. Pre/post images completos sirven exclusivamente para esa emergencia y se eliminan tras éxito/recuperación; hashes y journal permanecen. El rollback normal nunca usa esas copias.

### Límites de atomicidad y rollback

No hay transacción global de filesystem ni aislamiento frente a watchers. Preparación ocurre fuera de rutas observadas; en commit se crea un temporal vecino para el rename atómico por archivo, incluso si state y config están en filesystems distintos. Hash-check y rename no son CAS de kernel frente a un escritor no cooperante; detener ediciones durante el Local Test Gate. Una interrupción puede ser visible a consumidores antes de recuperar. El primer journal se publica como directorio completo por rename: una interrupción anterior sólo deja preparación privada fuera de operations, sin configuración aplicada. Un journal publicado corrupto sigue bloqueando.

Rollback compara exclusivamente cada valor/bloque/módulo aplicado. Conserva ediciones posteriores por defecto, informa LOCAL_PRESERVED y mantiene su propiedad pendiente en el estado; puede retirar otras claves independientes y devolver PARTIAL_ROLLBACK. `--replace recurso:clave` autoriza restaurar sólo ese valor original, nunca reparar estructura ambigua ni superar dependencias Lua. Una edición ya idéntica al original conocido libera su registro sin escribir; retirar manualmente el bloque no provoca su reinserción. Repetición totalmente retirada es NO_CHANGE. Restaurar configuración no recarga ni reconstruye reglas vivas; validación/recarga real requieren el gate separado.

## Evolución de funciones propias

Comandos futuros usan `heartchy-*` y mantienen la lógica separada de los efectos. Un hook se justifica sólo si existe un evento stock adecuado: el dispatcher comprobado admite `~/.config/omarchy/hooks/<evento>` y `<evento>.d/`; `theme-set` y `post-update` tienen llamadas verificadas, pero ninguno se registra ahora. Un servicio de usuario sólo se plantea cuando una función necesita persistencia real y se separa de su interfaz.

Las interfaces futuras usarán puntos públicos comprobados de menú/IPC o una propuesta separada si requieren un plugin. No se amplía silenciosamente el Core. No se accede a `bar.shell`, `_services`, geometría privada, parent-walking para saltar fachadas ni identidades falsas first-party. Las fachadas reducen autoridad, no son una garantía de sandbox dentro del proceso QML.

Clasificar cada necesidad como extensión soportada, API ausente o bug upstream. Si exige cambios en Omarchy, las opciones a evaluar son una contribución upstream o un parche/fork acotado con commit base, diferencia y pruebas conocidos. Ninguna autoriza editar el árbol instalado.

## Límite de herramientas y candidato

`check` valida lectura segura sin enlaces, formatos, hashes, inventario, alcance y referencias locales. Restringe el TOML a secciones/claves simples, strings sin escapes y números decimales que reconoce `Color.parseShell`; TOML válido como `7e-1` o claves entrecomilladas se rechaza para evitar un PASS que el consumidor ignoraría. Ejecuta Lua en un entorno de captura sin io/os/package/IPC, con límite de instrucciones y timeout; no carga el Omarchy instalado. Los tests aportan aislamiento de procesos y filesystem adicional. Las dependencias no se instalan.

`stage` valida primero, crea sólo un hijo nuevo directo de `build/` (y su directorio padre si falta) y escribe copias regulares de los tres recursos y documentos de contrato/procedencia. Rechaza escapes, enlaces en fuentes/destino y sobrescrituras. Una copia temporal del proyecto puede usar su propio `build/`; no hay destino por defecto en HOME. Fallos de escritura dejan un candidato parcial para inspección y nunca borran una ruta ajena. El inventario se escribe al final; sin él no hay candidato completo.

`inventory.json` cubre bytes, tamaño y modo de cada payload; no incluye su propio hash ni `local.json`. El payload y el inventario son reproducibles con las mismas fuentes/herramientas. `local.json` contiene tiempo e identidad Git variables: HEAD puede ser null y el worktree estar sin commit. Incluso un checkout limpio produce un candidato local, no una release. `stage` no es un archivo instalable de Omarchy ni decide distribución final.

## Arquitectura del desarrollo

La separación de autoridad, documentos de Feature, estados y gates se define en `docs/development.md` del checkout; `AGENTS.md` enruta a procedimientos especializados. `docs/upstream-contracts.md` identifica consumidores y alcance probado. Estas referencias pertenecen al checkout, no al payload reducido de stage. No cambian los contratos ARQ-001/002/003 anteriores.

`feature new` es scaffolding documental fuera del payload Core: una plantilla, un documento de trabajo nuevo, sin código de producto ni operación sobre el destinatario. `check` también valida ese contrato documental y sus referencias. No existe motor de estados de Features; el publicador de prueba se define separadamente en `docs/updater.md`; las primitivas Core de ARQ-004 son independientes de feature new. El stage conserva su inventario anterior; las guías de desarrollo viven en el checkout, no son recursos instalables.

## Entregas de prueba

`docs/updater.md` define el contrato de runtime, confianza, metadatos, transporte y adaptación UI del encargo UPDATE-TEST-001. Reutiliza las primitivas de esta arquitectura; no añade otro editor ni cambia la política de conflictos. Identidad cliente y Core aplicada son independientes.
