---
name: release-preparation
description: Preparar, verificar y publicar sólo una entrega expresamente autorizada con evidencia y confianza definidas.
---
# Preparación de release

1. Leer [estados/gates](../../docs/development.md) y el [contrato de prueba](../../docs/updater.md). Una Feature debe aportar comportamiento aceptado, recursos administrados soportados, compatibilidad, dependencias, recuperación, reporte editorial y evidencia. Un recurso nuevo requiere integración/pruebas; no se admite un script libre dentro del paquete.
2. Revisar diff, pruebas requeridas y fuente identificada; `./tools/heartchy-dev check` y `./test/all`. Revisar por separado UNIT, aisladas, HTTP lab, GitHub real, rendering, Core gráfico, Diego y Rafa. Mantener FAIL/NOT_RUN honestos.
3. Actualizar una única fuente editorial revisada. Commit coherente y limpio; `tools/heartchy-release prepare` firma entrega acumulativa completa según comandos del contrato. La clave permanente autorizada está fuera del repo; claves laboratorio nunca se publican. Verificar inventario/runtime independiente.
4. Antes de escribir remoto comprobar repo exacto, visibilidad, raíz de confianza y autorización para esa prerelease; mostrar commit/tag/assets/digest. `tools/heartchy-release publish` usa draft→assets→verificación→prerelease; sin force, sin reemplazar entregas ni publicar automáticamente por commit/merge. Si falta autorización, completar lo local y presentar bloqueo concreto.
5. Descargar anónimamente la release pública con `heartchy-update fetch`, verificar y ejecutar `test/release-artifact` sobre esa descarga, no el candidato original. Si es privada, requiere contrato de autenticación distinto aprobado; el cliente actual es público.
6. Revisión de Diego antes de prueba personal/promoción. Merge ≠ candidato ≠ release ≠ instalado ≠ probado en Rafa. Promoción estable, instalación permanente y Rafa no se infieren de tests ni publicación. El código propio no adquiere licencia libre por publicarse.

Salida: artefacto/revisión, resultados por nivel y gate siguiente. La Skill no concede permisos; comandos y límites se mantienen en el contrato único.
