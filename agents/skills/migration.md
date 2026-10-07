---
name: migration
description: Diseñar o cambiar transformaciones propias de estado Heartchy con repetición segura y preservación ajena.
---
# Migraciones propias

1. Distinguir recurso nuevo, preferencia local y transformación necesaria de estado existente según [arquitectura](../../docs/architecture.md). No crear migraciones sólo por cambiar una fuente.
2. Documentar precondición observable, alcance exacto, base aplicada, propuesta, conflicto y retirada. Leer estado antes de mutar; preservar contenido ajeno y ediciones posteriores. No interpretar código arbitrario para adivinar preferencias.
3. Migración y registro pertenecen a Heartchy, nunca al directorio/registro de Omarchy. Idempotencia y éxito verificable antes de marcar completada; fallo conserva pendiente y detiene dependientes. No implementar un runner sin alcance aprobado.
4. Probar estado antiguo, nuevo, ya migrado, personalizado, inválido, repetición, fallo parcial y recuperación con [testing](testing.md). Los fixtures no prueban que una instalación real haya migrado.
5. Presentar diff, preimages y recuperación para Destructive/Migration Gate antes de aplicar una transformación significativa. Privilege Gate si corresponde; Local Test Gate si toca Diego. No borrar marcadores reales para hacer pasar pruebas.

Salida: predicado acotado, prueba de repetición/preservación y evidencia separada de aplicación. Un backup completo no autoriza sobrescribir ediciones posteriores.
