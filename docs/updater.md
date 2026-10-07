# Actualizador de prueba — contrato 1

GitHub Releases es el origen aprobado; Diego delegó repositorio, visibilidad y firma: **HeartyFM/heartchy**, público, Ed25519 exclusiva de Heartchy. Sólo PRUEBA/PRE-RELEASE. Licencia del código propio, estable, instalación permanente, menú y Rafa requieren decisiones independientes. [Feature](../work/features/updates-first-test.md) conserva aceptación y resultados; [Core](architecture.md#aplicacion-arq-004) sigue definiendo las transformaciones y la propiedad.

## Cliente y límite de confianza

`bin/heartchy-update` usa `updates/` y los mismos planner/apply/validate/rollback/recover de `tools/`. No hay segundo editor de configuración. `mockups/updates.py` aporta presentación; `heartchy-updates-mockup` sigue siendo demo sin efectos. La UI funcional anuncia PRUEBA y operaciones reales sobre un descriptor explícito; la opción Omarchy sólo informa. `--window` conserva 875×600. Gum/Fzf y los logos se reutilizan; Middleout/ttfx 0.3.2 es opcional: ausencia, error o versión no verificada producen transición instantánea con diagnóstico. No se instalan dependencias.

Raíz pública de prueba: `trust/heartchy-test.json`, fingerprint **SHA256:1ZdLZEW69tbVk6TwiZV6+lDz+MHG3wDFZwQt+qDNInA**. Clave privada generada exclusivamente para esta autorización, fuera del repositorio, directorio 0700/archivo 0600; no se reutilizó OmaPacks. Su custodia y eventual rotación requieren una operación separada.

El usuario proporciona `--trust` **por un canal previamente autorizado**, nunca aceptando la clave que venga en la descarga. El documento fija producto por código, repositorio y clave pública Ed25519. `heartchy-lab-trust` permite HTTP loopback exclusivamente para laboratorio y no publicación; `heartchy-trust` usa HTTPS/TLS público anónimo. No circula token de publicación. OpenSSH `ssh-keygen -Y` verifica firma separada con principal `heartchy`, namespace `heartchy-release-v1`; no criptografía propia.

El consumidor autentica `release.json` antes de interpretar/editorial/extraer. Esquema cerrado 1: producto, repo, versión, canal, commit completo, fecha de preparación, contrato/capacidades, compatibilidad, editorial único, inventario y archive. La fecha publicada viene de `published_at` de GitHub; no forma una prueba firmada de tiempo. Título/flag mutable de GitHub no promueven metadatos Prueba a Estable. Reportes rechazan controles ANSI/OSC/bidi; posicionales Gum se separan con `--`.

Las releases son completas y acumulativas. `card=major/minor` sólo presenta tarjetas, nunca un parche incremental. No se instalan apps, plugins ni scripts arbitrarios. La lista de archivos runtime/Core está cerrada por el cliente; incorporar un nuevo recurso exige integración, contrato y pruebas propias.

Límites: metadata 200 KB, firma 4 KB, archive 16 MiB, cada archivo 2 MB, hasta 100 miembros y total descomprimido acotado. Se rechazan duplicados, enlaces, tipos especiales, PAX, paths fuera de inventario, tamaños/modos/hashes distintos. La extracción crea una carpeta nueva. Ningún código descargado se ejecuta antes de verificación. El bundle incluye el runtime Heartchy, Core, atribuciones e inventario; dependencias externas declaradas, sin código de paquetes externos.

Red: paginación 100 × máximo 20 páginas; no `/latest`. Timeout 12 s, máximo tres intentos de transporte/5xx y espera acotada; 403/429 explícito, sin caída a otro canal/versión. Sin credenciales ni proxies heredados. Redirecciones API sólo api.github.com; assets sólo github.com, release-assets.githubusercontent.com y objects.githubusercontent.com, HTTPS y puerto normal. Descargas interrumpidas conservan un `.UUID.partial` no instalable; reintento usa otro. Caché sólo mediante `--cached`, reautenticada y marcada `CACHE_EXPLICIT_NOT_CURRENT`. No ofrece antirrollback/frescura completa de TUF ni rotación/revocación de claves automática.

## Target, autorización y estados

No hay target ni canal por defecto. `--target` es un **archivo target.json** (no HOME ni `.config` directamente), con descriptor `heartchy-local-target` de [core-application](core-application.md). Sólo puede mapear los cuatro archivos Core: `.config/hypr/heartchy.lua`, `.config/hypr/looknfeel.lua`, `.config/omarchy/shell.json`, `.config/omarchy/shell.toml`. Stock loaders y sombras se leen según ese contrato. No activa compositor/Shell.

`--state` es un directorio privado 0700 persistente, fuera de config. Conservarlo junto al runtime verificado para recuperación. Contiene descargas, candidatos, planes, `managed/` (ledger/journal Core), intento e identidad Core instalada. El cliente tiene `client.json` con su commit/versión; el plan liga además hash del código efectivo, incluidos helpers UI. Copiar un runtime nuevo **no actualiza Core**, y aplicar Core **no reemplaza el cliente ejecutándose**. No existe autoactualización del programa.

Plan público interno versionado, canonical JSON: identidad de entrega, cliente, target/state y plan Core completo. Su SHA256 es la aprobación explícita. `apply` revalida firma, candidato, todos los inputs y decisiones; una modificación obliga a plan/aprobación nuevos. Conflictos permiten conservar o seleccionar sólo `recurso:clave`; sin force. La UI prepara descarga y plan antes de confirmación Cancelar por defecto y muestra efectos separados del reporte editorial. El progreso muestra fases/resultados reales, sin sleep disfrazado de trabajo.

La autoridad por target se registra en `shadow_root/heartchy/core-authority.json` **después** de aprobación/preparación; fija el state root original, no el dueño de valores coincidentes. Flock sobre la carpeta física config evita escritores entre checkouts/state distintos; un lock privado protege la sesión. Para stock real `/usr/share/omarchy`, se comprueba el hash del helper instalado `omarchy-update-lock` y se usa su mismo flock `${XDG_RUNTIME_DIR:-/tmp}/omarchy-update.lock`; no se ejecuta su updater, no se borra el lock. Se rechaza pacman db.lck presente. Otros editores no cooperantes siguen sujetos a recheck: no hay CAS global de filesystem.

`prepare → commit por archivo → readback`. Antes del commit todo está preparado fuera de config; inicialización del primer journal se publica por rename de directorio completo. Residuos anteriores quedan en `managed/preparing`, sin cambios activos. Durante escritura se aplazan señales de cierre; SIGKILL/pérdida de energía dejan journal/attempt para `recover`. No matar al escritor para cancelar. Descarga/verificación se cancelan con Ctrl+C, y Cancelar UI actúa antes del commit.

Una operación interrumpida se distingue de un commit completo con edición local posterior. La primera exige `RECOVERY_REQUIRED`; la segunda queda `VALIDATION_PENDING`, conserva la edición y permite nuevo plan/resolución. El UI no muestra instalación completa sin validación. No-op sin propiedad ni referencias administradas da `NO_MANAGED_APPLICATION`, sin instalación falsa ni recuperación artificial. Coincidencias Shell aceptadas siguen separadas de propiedad escrita. Una versión sólo tiene indicador de instalada tras validación; retirada parcial invalida ese indicador. `APPLIED_WITH_LOCAL_PREFERENCES` explica divergencias elegidas, no acredita compatibilidad gráfica.

Rollback restaura **origen de propiedad**, no una release anterior. Un cambio local posterior se conserva y reporta; reemplazo sólo explícito y acotado. Versiones más antiguas están bloqueadas: no hay downgrade. `recover` usa journal, nunca un backup completo a ciegas. Mantener estados/descargas pendientes para diagnóstico; no borrarlos para sortear bloqueos.

## Comandos reales

Rutas en ejemplos son explícitas y deben existir; destinos de salida nuevos. No ejecutarlos contra configuración personal sin gate.

```sh
./bin/heartchy-update --help
./bin/heartchy-update catalog --trust trust/heartchy-test.json --channel test
./bin/heartchy-update fetch --trust trust/heartchy-test.json --channel test --version 0.1.0-test.2 --output /tmp/heartchy-delivery-review
./bin/heartchy-update verify --trust trust/heartchy-test.json --delivery /tmp/heartchy-delivery-review
./bin/heartchy-update extract --trust trust/heartchy-test.json --delivery /tmp/heartchy-delivery-review --output /tmp/heartchy-runtime-review
./test/release-artifact --delivery /tmp/heartchy-delivery-review --trust trust/heartchy-test.json
```

El último comando verifica y ejecuta ese runtime dentro de Bubblewrap, sin red/IPC/desktop; first-write stock, validate, no-op y rollback. Tiene un `/etc/passwd` sintético para OpenSSH, no acceso al real. El trust del ejemplo sólo es válido después de que Diego haya autorizado su fingerprint por un canal independiente de los assets.

```sh
/tmp/heartchy-runtime-review/bin/heartchy-update ui --trust /ruta/trust-autorizado.json --channel test --target /ruta/target.json --state /ruta/state-privado --window
/tmp/heartchy-runtime-review/bin/heartchy-update plan --trust /ruta/trust-autorizado.json --delivery /tmp/heartchy-delivery-review --target /ruta/target.json --state /ruta/state-privado --output /ruta/plan-nuevo.json
/tmp/heartchy-runtime-review/bin/heartchy-update apply --trust /ruta/trust-autorizado.json --delivery /tmp/heartchy-delivery-review --target /ruta/target.json --state /ruta/state-privado --plan /ruta/plan-nuevo.json --approve SHA256_REVISADO
/tmp/heartchy-runtime-review/bin/heartchy-update validate --target /ruta/target.json --state /ruta/state-privado
/tmp/heartchy-runtime-review/bin/heartchy-update rollback --target /ruta/target.json --state /ruta/state-privado --approve rollback
/tmp/heartchy-runtime-review/bin/heartchy-update recover --target /ruta/target.json --state /ruta/state-privado --approve recover
```

## Producción de prerelease

`releases/first-test.json` es la única fuente editorial de esta entrega. Actualizar sus notas junto al cambio real, recursos/compatibilidad/dependencias y evidencia. Revisar código/efectos y commit coherente; el builder rechaza dirty. Versiones libres se consultan antes, no se sobrescriben entregas. Ejemplo de preparación, con clave fuera del repositorio:

```sh
./tools/heartchy-dev check
./test/all
./tools/heartchy-release prepare --version 0.1.0-test.2 --repository HeartyFM/heartchy --trust trust/heartchy-test.json --signing-key /ruta/clave-autorizada --editorial releases/first-test.json --output build/prerelease-0.1.0-test.2
./tools/heartchy-release publish --delivery build/prerelease-0.1.0-test.2 --trust trust/heartchy-test.json --approve SHA256_METADATA_REVISADO
```

Publicar requiere resumen exacto y Release Gate ya autorizado; no ocurre al commit/merge. Source commit exacto debe existir remoto. Snapshot verificado antes de red, draft → tres assets por bytes fijados → hash/tamaño remoto → tag exacto (nuevo lightweight si ausente) → prerelease=true, make_latest=false. Ante fallo queda draft para inspección; no se reemplazan assets ni tags existentes. Inmutabilidad existente se respeta, sin cambios de administración. Descargar anónimamente la prerelease pública y ejecutar `test/release-artifact` sobre **esa descarga**, después revisión de Diego. Promover a oficial exige nuevo contrato/autorización coherente, no renombrar títulos.

La publicación inicial usó una copia pública revisada sin exportar el historial privado de desarrollo. `PUBLICATION.json` en esa rama vincula commit local, inventario/hashes y las dos sustituciones documentales de rutas personales. Runtime/Core no se transforman. Los commits de publicación son identidades reales distintas de los commits de desarrollo; no se atribuye a la release el SHA del checkout privado. Cambios posteriores se revisan sobre esa rama pública, sin subir automáticamente otro historial ni evidencia local.

## Nuevo LOCAL TEST GATE — NOT_RUN

Este updater no hereda la autorización del antiguo Local Test Core. Revisar versión/fingerprint/commit, descriptor con config real y los cuatro archivos anteriores, state root nuevo **sólo si no existe autoridad previa**. Si ya existe, usarlo con compatibilidad comprobada; no borrar/reasignar autoridad. Backup privado de esos archivos/hashes/modos y plan nuevo; comparar reglas históricas, referencias coincidentes y preferencias antes del digest. Primer test personal será temporal con rollback, no instalación permanente.

Tras autorización: usar el runtime descargado/verificado y comandos `plan/apply/validate` anteriores con target/state reales declarados, recarga/inspección limitada autorizada en [Core Local Test](core-application.md), comprobar nueve candidatos y ausencia de nuevos errores, replan/no-op, rollback por propiedad y comparar pre/post. Si JSON exige normalización, informar diferencia de formato; la preservación ajena es semántica para JSON y por bytes en zonas Lua/TOML no administradas. Detener ante stale/ambigüedad/recovery; preservar journal. Ni rendering TUI ni fixtures acreditan primera integración gráfica sobre stock, Diego o Rafa.

## Referencias verificadas

Consulta 2026-10-07: [GitHub Releases API](https://docs.github.com/en/rest/releases/releases) (listado, creación, assets, edición; cabecera API 2026-03-10); [releases inmutables](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases); [amenazas TUF](https://theupdateframework.io/docs/security/) como límite, sin copiar infraestructura. Omarchy quattro fijado en **902fd8aebd98b6eedaa58276886a2f9f2876755f**, distinto del paquete instalado: [update-process](https://github.com/omacom/omarchy/blob/902fd8aebd98b6eedaa58276886a2f9f2876755f/docs/update-process.md) coordinación/migraciones, [file-layout](https://github.com/omacom/omarchy/blob/902fd8aebd98b6eedaa58276886a2f9f2876755f/docs/file-layout.md) propiedad, [testing](https://github.com/omacom/omarchy/blob/902fd8aebd98b6eedaa58276886a2f9f2876755f/docs/testing.md) niveles. Helper instalado `/usr/bin/omarchy-update-lock`: líneas 9–10 y 34–35, SHA256 `9448e1748b10e46bb4310be37d69d0eba6090f69c71264cce4fc6f344278cb7d`. No se ejecutaron sus acciones.
