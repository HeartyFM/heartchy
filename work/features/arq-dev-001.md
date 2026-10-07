# HEARTCHY-ARQ-DEV-001 — Arquitectura de desarrollo

ID: HCY-arq-dev-001
Nombre: Arquitectura de desarrollo, Skills y flujo de Features
Estado: ISOLATED_TESTED
Último estado alcanzado: ISOLATED_TESTED
Bloqueo: N/A
Responsable: agente implementador /root; revisión independiente review_readonly


## Objetivo
Establecer procedimientos locales y una entrada documental consistente para funciones futuras, preservando ARQ-001/002/003.

## No objetivos
Ninguna función nueva, Power Manager, aplicador, instalador, updater, publicación, plugins ni cambios de escritorio.

## Decisiones de Diego aplicables
Petición HEARTCHY-ARQ-DEV-001 de esta sesión (2026-10-03, fecha local de contexto): autoriza Skills, contrato de Feature, estados/gates, herramienta documental y pruebas aisladas. Product Gate para este alcance cubierto por esa petición; aceptación del resultado sigue pendiente.

## Tipo de Feature
Herramientas y arquitectura de desarrollo; no Feature de producto del escritorio.

## Subsistemas afectados
agents/skills, documentación, plantilla work, tools/heartchy-feature.py, routing de tools/heartchy-dev y test. Un escritor: /root. Revisor de sólo lectura: review_readonly.

## Integración con Omarchy
N/A en runtime. Investigación selectiva de guías públicas fijadas; contratos de integración Core existentes intactos.

## APIs/contratos utilizados
Reutiliza read_project/write_new y validación Core; interfaces plan/stage de ARQ-001/002/003 conservadas. Nuevo contrato documental definido por work/FEATURE_TEMPLATE.md.

## Persistencia
Sólo documento nuevo bajo work/features y resultados generados bajo build/temporales. No estado de aplicación ni transición automática.

## Privilegios
N/A en producto. La suite requiere permiso para crear namespaces Bubblewrap; no ejecuta operaciones privilegiadas del sistema ni accede a la sesión.

## Dependencias
Sólo Python estándar y runtimes de pruebas existentes. Ninguna dependencia nueva.

## Compatibilidad conocida
Herramienta del checkout; no acredita compatibilidad gráfica. Registros Core y compatibilidad upstream mantienen su alcance anterior.

## Criterios de aceptación
Routing completo de once Skills, enlaces/plantilla válidos; feature new genera sólo un documento; ayuda/errores sin efectos; rechaza escapes/enlaces/sobrescritura; CWD/copia independiente; suite anterior preservada; resultados por nivel.

## Pruebas requeridas
STATIC check documental/Core; UNIT contratos de plantilla y argumentos; ISOLATED_INTEGRATION generación, IO acotado, rechazos, copia portátil y regresión completa. VISUAL/LOCAL/TARGET N/A para este cambio documental/CLI; prueba gráfica Core histórica pendiente sigue NOT_RUN.

## Rollback / retirada
Retirar sólo cambios de esta tarea después de comparar con preimages en build/arq-dev001-preimages; preservar ediciones posteriores y documentos de trabajo nuevos. No hay instalación que revertir.

## Riesgos
Validadores de Markdown soportan el estilo inline del repo, no todo CommonMark. Metadatos y enlaces correctos no prueban aprobación humana ni calidad de una decisión de producto.

## Decisiones pendientes de Diego
Revisión/aceptación del resultado de esta entrega. Licencia/visibilidad y distribución futuras permanecen pendientes; no bloquean esta base.

## Evidencia
- STATIC: `./tools/heartchy-dev check` PASS, Core y contrato documental. Hashes finales en `build/arq-dev001-verification.json`.
- Suite aislada completa: `./test/all`, 31 PASS, 0 FAIL, 0 SKIP, 1 NOT_RUN. Informe `build/arq-dev001-final-test-results.txt`; conserva toda la suite ARQ-001/002/003 y prueba desde copia temporal sin build, Git ni evidencia original.
- Prueba focalizada: `./test/all --only test_feature_scaffold_scope_and_portability`, 1 PASS; informe `build/arq-dev001-focused-results.txt`. Ejercita CWD ajeno, generación única, ausencia de procesos y conservación del árbol exterior.
- Revisión independiente de sólo lectura: agente review_readonly. Ejercicio documental Power Manager sin implementarlo; detectó duplicados de metadatos, ambigüedad N/A/NOT_RUN y enlaces de desarrollo ausentes del payload stage. Corregidos y verificados por lectura; pruebas de duplicados y enlaces agregadas. Sin hallazgos bloqueantes al cierre. El revisor no ejecutó tests ni UI.
- Investigación: `docs/development-upstream.json` conserva URLs/commit/hashes/líneas. Core/manifiesto y ambos planificadores coinciden con `build/arq-dev001-preimages/protected.json`; tres candidatos anteriores verificaron sus inventarios y el plan sigue leyendo ARQ-003.
- El NOT_RUN es la integración gráfica Core preexistente. VISUAL/LOCAL/TARGET de este cambio documental/CLI no aplican; no hay aprobación del resultado por Diego aún, publicación ni prueba en Rafa.
