# Registro de contratos consumidos

Este registro identifica qué comparar; la semántica se define en [arquitectura](architecture.md), no se duplica aquí. Procedimiento de revisión en [upstream-compatibility](../agents/skills/upstream-compatibility.md). Evidencia fijada: [upstream-evidence.json](upstream-evidence.json); procedencia y prueba histórica: [provenance.json](provenance.json).

Clasificaciones con alcance obligatorio: `SUPPORTED_TESTED` = contrato/entorno/revisión y nivel acreditados; `UNTESTED` = falta evidencia para ese alcance; `INCOMPATIBLE` = incumplimiento concreto documentado. No son un comparador de versiones ni certifican todo un paquete. Probar un contrato en fixtures sólo permite SUPPORTED_TESTED para esa prueba aislada, no para la integración real. Una actualización vuelve UNTESTED el alcance afectado hasta revisarlo.

Base histórica: Omarchy 4.0.4-1.1, settings 4.0.4-1, Hyprland 0.56.2-2, Quickshell 0.3.1-1. Upstream comparado por separado: Omarchy `8e02fc84f5bdc511ed102e2a14f8935bba4f92bd`. No se presume commit del paquete instalado. No hay otra versión declarada compatible automáticamente.

| ID | Consumidores acotados | Evidencia/alcance actual | Clasificación |
|---|---|---|---|
| H-LUA-LOAD | `config/hypr/hyprland.lua`, `default/hypr/bootstrap.lua`, `default/hypr/omarchy.lua` | Orden/resolución/cache leídos; fixture y planner ARQ-003 probados aisladamente | SUPPORTED_TESTED para el modelo aislado; UNTESTED nueva carga gráfica |
| H-LUA-RULES | `default/hypr/helpers.lua` (`o.window`), APIs y limpieza de reglas de Hyprland | Lectura de consumidores y modelo de reglas ARQ-001 | SUPPORTED_TESTED para fixture; UNTESTED composición real con preferencias posteriores |
| H-SHELL-JSON | `shell/shell.qml`, `bin/omarchy-bar` | Selección JSON y CLI leídas; intención/plan/apply/retirada con fixtures | SUPPORTED_TESTED aislado; UNTESTED nueva integración gráfica |
| H-SHELL-TOKENS | `shell/Commons/Color.qml`, `Style.qml`, `bin/omarchy-theme-set-templates` | Merge/tokens/templates y walker estudiados; stdlib + compatibilidad de claves consumidas, edición/retirada aisladas | SUPPORTED_TESTED sólo evidencia indicada; UNTESTED nueva integración gráfica/cambio de tema |
| H-STOCK-BAR | `shell/plugins/bar/`, consumidor `bar.transparent` | Barra stock como requisito; apariencia original validada históricamente | SUPPORTED_TESTED histórico limitado; UNTESTED integración nueva |

Las pruebas Core históricas usaron otra forma de integrar los valores; no acreditan la integración gráfica nueva del aplicador ARQ-004. El primer LOCAL TEST quedó BLOCKED sin apply; sus fixes son pruebas aisladas. Evidencia ARQ-003 local en `build/arq003-verification.json`; no es dependencia de check ni garantía para otros equipos. No hay incompatibilidad global de una versión demostrada. Un archivo inválido/contrato declarado distinto bloquea el plan, sin declarar incompatible todo Omarchy.

Hooks/IPC/fachadas mencionados como posibilidades en arquitectura no son dependencias activas adicionales. Si una Feature los consume, añadir fila con archivo/símbolo, revisión instalada/upstream, prueba, clasificación y causa/límite; no crear un inventario de todo Omarchy. Registro y decisiones de revisión viven en la Feature; este índice mantiene sólo el estado pertinente vigente.
