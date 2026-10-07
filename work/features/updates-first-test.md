# Primer actualizador de prueba

ID: HEARTCHY-UPDATE-TEST-001
Nombre: Entrega firmada y recorrido funcional de prueba
Estado: ISOLATED_TESTED
Responsable: Codex /root; revisión independiente /root/review_readonly

## Objetivo
Fuentes identificadas → entrega acumulativa firmada → GitHub Releases → verificación → reporte/plan → aprobación → motor Core → validación/recuperación. Primera entrega PRUEBA/PRE-RELEASE, nunca oficial.

## No objetivos
Autoactualizar runtime en ejecución, integración en menú, instalar paquetes/plugins/apps, configuración personal, estable, Rafa, nuevos servicios o scripts arbitrarios.

## Decisiones de Diego aplicables
Encargo UPDATE-TEST-001 aprueba implementación y pruebas aisladas/ventanas propias, commits pertinentes y prerelease tras definir destino/confianza. Diego delegó explícitamente elección de repositorio, visibilidad y raíz de firma. Decisión: repositorio público dedicado HeartyFM/heartchy (consulta 404), firma OpenSSH Ed25519 exclusiva, consumidor anónimo. No reutilizar OmaPacks. Resumen remoto pendiente antes de cualquier escritura. Licencia de código nuevo aún pendiente; publicación de prueba no concede licencia libre implícita.

## Tipo de Feature
CLI, distribución de prueba, integración de UI existente y Core.

## Subsistemas afectados
`updates/`, `bin/heartchy-update`, herramientas de entrega; adaptaciones mínimas de motor y presentación; tests/skills/docs existentes. Código fuera del documento; sin framework.

## Integración con Omarchy
Reutilizar contratos Core fijados. No ejecutar actualizador Omarchy, servicios ni refresh. Su ruta UI es informativa. Revisar coordinación instalada mediante lock/flock y recheck, sin romper locks.

## APIs/contratos utilizados
REST GitHub Releases, OpenSSH ssh-keygen -Y sign/verify, HTTPS/TLS stdlib; JSON autenticado y tar acotado. Motor Core existente para toda escritura personal. Documentación upstream consultada 2026-10-07: quattro 902fd8aebd98b6eedaa58276886a2f9f2876755f (no paquete instalado).

## Persistencia
Descargas completas verificadas, planes, identidad cliente separada de Core, ledger y journal privados. Target/state explícitos; sin HOME implícito. No estado en build requerido por comando distribuido.

## Privilegios
Usuario normal. Sin sudo ni secretos en artefactos. Claves efímeras sólo laboratorio; clave permanente dedicada sólo para prerelease autorizada, nunca expuesta.

## Dependencias
Python estándar, OpenSSH, Lua; presentación Gum/Fzf/Alacritty existentes; ttfx 0.3.2 opcional con fallback instantáneo explícito.

## Compatibilidad conocida
Core contratos instalados Omarchy 4.0.4-1.1 / settings 4.0.4-1 / Hyprland 0.56.2-2 / Quickshell 0.3.1-1. No inferir versiones futuras. Sin compositor en suites.

## Criterios de aceptación
1. Entrega completa, reporte único firmado, inventario y runtime independiente.
2. Listado paginado Estable/Prueba explícito, red y extracción limitadas, firma externa confiable antes de ejecutar.
3. Plan revisable y digest; mismos recursos/motor; primera escritura JSON/TOML/Lua y A→B reales en targets aislados.
4. Preferencias, stale plans, bloqueos, no-op, rollback y recovery honestos; exclusión por target y state.
5. UI conserva recorrido y distingue demo de efectos en sandbox, sin progreso falso, aprobación segura.
6. Pruebas adversariales y cierre, check/suite/revisión; evidencia por nivel y commit/artefacto.
7. Publicación sólo prerelease borrador→assets→verificación→publicación; descarga anónima del mismo artefacto y prueba aislada.

## Pruebas requeridas
UNIT / ISOLATED_INTEGRATION / HTTP local / GitHub real / RENDERIZADO separados. Core gráfico desechable, Diego y Rafa NOT_RUN en este encargo. Matriz del usuario trazada en tests y reporte de resultados.

## Rollback / retirada
Motor restaura origen de propiedad; no prometer downgrade a release anterior. Recovery conserva terceros estados y bloquea siguientes operaciones hasta resolver journal. Runtime viejo permanece disponible; no sobrescribir programa activo.

## Riesgos
Firma autoriza código del runtime: clave separada y anclada fuera de descarga; protocolo sin garantía completa TUF. API interna ttfx no puede bloquear función. Múltiples archivos no son transacción global. Publicar no demuestra primera aplicación gráfica sobre stock.

## Decisiones pendientes de Diego
Promoción oficial, instalación personal permanente, Rafa y licencia libre quedan separadas; no bloquean laboratorio autorizado.

## Evidencia
Baseline a6b2b21: check PASS, 83 PASS / 0 FAIL / 0 SKIP / 1 NOT_RUN; build/updates-first-test/baseline-*.log. Trabajo UI anterior preservado en commit, sin merge main.
Revisión independiente de lectura /root/review_readonly: hallazgos corregidos y cierre confirmado; no ejecutó pruebas ni UI. Regresiones reproducen propiedad obsoleta entre ciclos, concurrencia por target, snapshot publicado, no-op sin propiedad, último journal inicial y validación de ediciones posteriores al commit/recover. `full-01.log` conservó fallos reales (scope del nuevo claim y fixture de paginación), corregidos sin quitar protecciones; `full-02.log`: 101 PASS / 0 FAIL / 0 SKIP / 1 NOT_RUN. Cierre posterior `full-03.log`: 102 PASS / 0 FAIL / 0 SKIP / 1 NOT_RUN, incluida variante de recovery con edición posterior. Revisor confirmó cierre de todos sus hallazgos por lectura.

Raíz de confianza generada con autorización delegada: OpenSSH Ed25519, fingerprint SHA256:1ZdLZEW69tbVk6TwiZV6+lDz+MHG3wDFZwQt+qDNInA. Sólo clave pública en Git. Clave privada exclusiva fuera de repo, sin exportar. Licencia propia pendiente; publicación pública de prueba autorizada.

Matriz: tests updater verifican first-write stock (TOML ausente, JSON stock false seleccionado explícitamente, módulo/prefijo Lua), A→B por TUI y motor, no-op, preferencias/semi-stock, stale, firma/inventario/tar hostil, HTTP loopback/paginación/caché/rate/timeout/retry, permisos/espacio/concurrencia, runtime independiente, recuperación antes/durante/después de commit y ausencia de propiedad falsa. B laboratorio sólo cambia bytes/comentario del módulo manteniendo valores Cristal; no es una nueva apariencia. No se publican fixtures maliciosos ni entregas A/B para inflar evidencia.

Pendientes al fijar candidato: cierre suite, artefacto Git identificado, GitHub real/descarga/runner del artefacto, rendering funcional propio. Core gráfico desechable, cambio global de tema, updater en Diego y Rafa NOT_RUN. No se halló VM/sesión desechable preparada; no instalar una por cuenta del agente.
