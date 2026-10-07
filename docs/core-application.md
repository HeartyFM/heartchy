# Prueba controlada del Core

Contrato y propiedad: [arquitectura ARQ-004](architecture.md#aplicacion-arq-004). Este procedimiento no concede autorización. Estado técnico/evidencia: [Feature](../work/features/core-apply.md). No es updater ni despliegue automático.

## Prueba aislada reproducible

Desde un checkout, usando nombres nuevos:

```sh
./tools/heartchy-dev check
./test/all
./tools/heartchy-dev stage --output build/core-review
mkdir -p build/simulations
cp -R test/fixtures/planner/lua-first build/simulations/review
./tools/heartchy-dev plan --candidate build/core-review --target build/simulations/review --state-root build/state/review --resource hypr --format json > build/core-plan.json
sha256sum build/core-plan.json
```

Revisar el plan. Con su hash exacto en lugar de `SHA256_REVISADO`:

```sh
./tools/heartchy-dev apply --candidate build/core-review --target build/simulations/review --state-root build/state/review --plan build/core-plan.json --approve SHA256_REVISADO
./tools/heartchy-dev validate --target build/simulations/review --state-root build/state/review
./tools/heartchy-dev rollback --target build/simulations/review --state-root build/state/review --approve rollback
./tools/heartchy-dev recover --target build/simulations/review --state-root build/state/review --approve recover
```

El último comando sólo actúa si hay un journal interrumpido. No es una manera de ignorar conflictos. Un nuevo apply, incluso del mismo candidato, exige plan nuevo si cambió algún input; repetición con valores ya aplicados no crea estado/journal extra. Exit 0 operación comprobada/no-op, 3 valores locales pendientes o validación negativa, 1 error/bloqueo, 2 argumentos inválidos. Resultado gráfico siempre separado.

## LOCAL TEST GATE — preparado, NOT_RUN

Responsable: Diego autoriza candidato, archivos, valores seleccionados y ventana de prueba. No ejecutar estos pasos en esta entrega. No ejecutar refresh global. Tener una terminal disponible para recovery/rollback; no editar configuración durante commit. Registrar revisión Git, candidato/inventario, versiones reales y hashes de los contratos consumidos. Revisar Shell JSON/TOML y loaders conforme a [compatibilidad](../agents/skills/upstream-compatibility.md); tres hashes de carga Lua verificados no prueban compatibilidad Shell.

**Precondición importante:** el escritorio histórico contiene bloques Cristal personales. El reconocedor no los elimina ni demuestra que no se acumulen reglas. Antes de aplicar hay que revisar cuáles siguen activos y obtener una autorización separada para una adopción mínima si duplica la fuente. Código Lua fuera del subconjunto reconocido, sombras generadas, loader diferente o marcadores dañados producen BLOCKED; este procedimiento se detiene, no modifica looknfeel completo ni usa force.

El primer intento LOCAL quedó BLOCKED antes de apply por exigir el hash exacto del entrypoint personal y rechazar `[omafiles] glass = true`. Los fixes aislados reconocen el prefijo stock con el guard final conocido de Hyprmoncfg y aceptan TOML ajeno válido. No se alteró Hyprmoncfg ni el escritorio. Los 61 tokens y bar.transparent ya coincidentes se revisan como `ALREADY_MATCHES` con aceptación de referencia, no como creación; véase [procedencia](architecture.md#procedencia-cambio-escrito-coincidencia-aceptada-y-preferencia-local). Una carga equivalente ajena sigue sin propiedad. Estos fixes no eliminan la revisión semántica de reglas históricas ni acreditan la prueba gráfica.

Para repetir desde cero: nuevo precheck/versiones/árbol limpio, backup fechado, candidato de los commits corregidos, descriptor y state root nuevos, plan/digest nuevos y recheck. No reutilizar como aprobación el plan/candidato del intento bloqueado. En la prueba comparar PRE/POST completos de los cuatro archivos tras rollback; las referencias coincidentes no deben provocar escrituras en esos archivos.

Crear después del gate un descriptor privado nuevo, sin symlinks. Este ejemplo es explícitamente local a Diego; no fuente distribuible del Core. `config_root` apunta a configuración, `shadow_root` al estado generado que el bootstrap busca primero; comprobar que este último sea el real del destino antes de aprobar:

```sh
mkdir -p build/local-targets/diego-core
cat > build/local-targets/diego-core/target.json <<'JSON'
{
  "schema_version": 1,
  "kind": "heartchy-local-target",
  "config_root": "/home/USER/.config",
  "shadow_root": "/home/USER/.local/state",
  "stock_root": "/usr/share/omarchy",
  "contracts": {
    "hypr_module": "heartchy-lua-module-bytes-v1",
    "hypr_connection": "omarchy-lua-prefix-v1",
    "shell_intent": "omarchy-shell-json-v1",
    "shell_tokens": "omarchy-shell-toml-key-merge-v1"
  }
}
JSON
./tools/heartchy-dev stage --output build/core-local-review
./tools/heartchy-dev plan --candidate build/core-local-review --target build/local-targets/diego-core --state-root build/state/diego-core --format json > build/core-local-plan.json
```

Primero respetar preferencias. Si Diego solicita todos los tokens Core y transparencia, regenerar explícitamente con `--prefer-heartchy shell_tokens --prefer-heartchy shell_intent:bar.transparent`; no extender a otros recursos por comodidad. Revisar cada fila, diff Lua y advertencias; guardar hash con `sha256sum build/core-local-plan.json`. No ejecutar apply con entradas bloqueadas o conflicto pendiente. No automatizar aprobación mediante una sustitución que compute y acepte el hash sin revisión.

Comando exacto preparado, sustituyendo únicamente el hash ya revisado y aprobado:

```sh
./tools/heartchy-dev apply --candidate build/core-local-review --target build/local-targets/diego-core --state-root build/state/diego-core --plan build/core-local-plan.json --approve SHA256_REVISADO
./tools/heartchy-dev validate --target build/local-targets/diego-core --state-root build/state/diego-core
```

Tras commit, recarga de compositor/reinicio limpio de Shell son efectos separados: confirmar el procedimiento stock disponible y pedir autorización concreta si no estaba incluida en el gate. No prometer que los watchers dan una transición global atómica ni invocar servicios desde esta herramienta. Verificar `hyprctl configerrors`, archivo módulo/hash, bloque único y ausencia de sombras; `hyprctl animations` debe reflejar slidevert. Inspeccionar blur 6/2, bordes neutros 1px, terminales y blur de superficies/popups. Comprobar barra stock/transparencia y tokens Cristal en menú/superficies, con hover/selected/focus y scrim. Inspeccionar nuevos errores persistentes de Shell y IPC oficial de barra. Capturas para bordes/transparencia y video corto de workspaces. Registrar comandos efectivamente usados, tiempos y resultados; no almacenar logs privados en Git.

Checks preparados para la ventana autorizada (no ejecutados aquí):

```sh
hyprctl reload
hyprctl configerrors
hyprctl getoption decoration:blur:size
hyprctl getoption decoration:blur:passes
hyprctl getoption general:border_size
hyprctl animations
omarchy-shell shell reloadConfig
omarchy-shell shell ping
omarchy-shell shell listPlugins | jq '.[] | select(.id == "omarchy.bar") | {id, active}'
omarchy-shell shell listShellConfig | jq '{bar_transparent: .bar.transparent}'
journalctl --user -t omarchy-shell --since "FECHA_INICIO_PRUEBA" --no-pager
```

Exigir configerrors vacío, ping ok, barra activa y valores esperados cuando no haya preferencias posteriores. El hash del módulo/bloque y los valores efectivos son comprobaciones separadas; no presentar sólo existencia del archivo como prueba de carga. Si no puede demostrarse carga por el contrato/efectos observados, dejar ese criterio pendiente. El watcher personal TOML de Color.qml relee al cambiar el archivo; si el runtime no refleja tokens, detener evaluación y revisar, no marcar PASS por el archivo correcto.

Las APIs IPC se comprobaron sólo leyendo el instalado: bin/omarchy-shell, shell/shell.qml:1590–1595,1670–1714; Color.qml:242–251 para watcher TOML. shell.qml SHA-256: 71db75d164564d1db60a1f6ad088bfacfd812cddabeae003f6aafa0507da7afe. No se ejecutó IPC. Un reinicio limpio opcional con `omarchy-restart-shell` debe incluirse expresamente en el gate: el helper inspeccionado puede intentar reiniciar invitaciones y manejar lock, por lo que no se invoca como efecto implícito de apply. Su hash e4c996275a15025c9aac829d34913d6bcaf8a30a17fae5ce5e260df2ddf21cd7 no garantiza que siga igual en la fecha de prueba. Ejecutar con sesión desbloqueada y alcance revisado; reconfirmar antes sus efectos. No guardar el journal completo como evidencia pública.

Rollback real preparado:

```sh
./tools/heartchy-dev rollback --target build/local-targets/diego-core --state-root build/state/diego-core --approve rollback
./tools/heartchy-dev validate --target build/local-targets/diego-core --state-root build/state/diego-core
```

Estado sin recursos tras retirada valida estructuralmente como vacío; comprobar además hashes/valores restaurados del journal, ausencia del módulo creado y del bloque propio, conservación de preferencias posteriores. Restaurar runtime mediante la recarga autorizada y repetir configerrors/inspección Shell/visual. Si hubo una edición posterior, rollback preserva y reporta: obtener decisión de Diego antes de `--replace recurso:clave`. Nunca restaurar un backup completo por comodidad. Ante RECOVERY_REQUIRED, inspeccionar journal y ejecutar recover autorizado; tercer estado inesperado exige resolución manual revisada, no force.

Este state root es local al checkout, deliberadamente inicial: conservarlo mientras exista una aplicación. Distribución, ubicación permanente futura y protocolo de estado permanecen fuera de ARQ-004. Ningún resultado aislado acredita Diego, Rafa, una release o compatibilidad gráfica.
