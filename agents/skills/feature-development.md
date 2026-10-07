---
name: feature-development
description: Coordinar una función nueva o cambio importante desde idea hasta preparación de release, sin decidir producto por Diego.
---
# Desarrollo de una Feature

1. Leer [autoridad, estados y gates](../../docs/development.md). Reutilizar el documento activo o iniciar `./tools/heartchy-dev feature new <slug>`; asignar responsable y aceptación. Una corrección pequeña puede usar el documento de su Feature; no abrir burocracia por cada línea.
2. Investigar sólo consumidores, interfaces, estado y restricciones pertinentes. Distinguir instalado, upstream fijado y propuesta propia. Registrar dudas; no implementar comportamiento aún no decidido. Preparar opciones concretas para Product Gate y continuar investigación independiente mientras se resuelve.
3. Determinar subsistemas y derivar por necesidad: [Core](core-config.md), [CLI](cli-command.md), [UI](shell-ui.md), [servicio](service-development.md), [privilegios](privileged-integration.md), [migración](migration.md). Ninguna Feature necesita todos automáticamente.
4. Con alcance/diseño autorizado, usar rama corta cuando exista historial. Implementar en el subsistema correcto, con lógica separada de efectos; actualizar aceptación si Diego cambia alcance. Una autorización anterior explícita sigue siendo válida para ese alcance.
5. Reproducir un defecto/criterio concreto → corrección mínima → regresión → recorrido afectado → revisión de efectos. Registrar evidencia y siguiente punto en la Feature. Tras tres intentos sin progreso, delimitar bloqueo y continuar partes independientes; no rebajar validación ni resolver preferencias por la fuerza. Leer [testing](testing.md); vincular criterios a pruebas y ejecutar las pertinentes. Para efectos visibles, [visual-verification](visual-verification.md). Solicitar revisión distinta si es posible; registrar hallazgos y quién revisó, sin atribuir independencia ficticia.
6. Preparar un resultado revisable antes del Local Test Gate. Cuando esos niveles correspondan y falte autorización o entorno, dejar LOCAL/VISUAL NOT_RUN; completar trabajo aislado. Si no corresponden, documentar N/A. Registrar restauración tras pruebas reales y aprobación del resultado por Diego, separadas de aprobación de implementación.
7. Actualizar el estado sólo por evidencia. Seguir [release-preparation](release-preparation.md) cuando se solicite preparar publicación; merge, candidato, publicación y prueba en Rafa son eventos distintos.

Salida: documento de trabajo con decisiones, rutas, pruebas, riesgos y próximo paso; no un diario duplicado en STATUS.
