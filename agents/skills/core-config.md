---
name: core-config
description: Cambiar Core, apariencia compartida de Hyprland, tokens Shell o theming preservando la propiedad y preferencias.
---
# Core y configuración

1. Leer [contratos de integración](../../docs/architecture.md) y el [registro consumido](../../docs/upstream-contracts.md). Identificar fuente propia, consumidor, claves/bytes administrados, datos ajenos y retirada antes de editar.
2. Editar fuentes de `core/`; revisar alcance/aceptación antes de cambiar manifiesto y hashes. No capturar layouts, hardware, plugins ni preferencias del escritorio como defaults compartidos.
3. Aplicar ARQ-002 y ARQ-003: Lua módulo completo + conexión mínima; JSON de usuario sustituye stock; TOML mezcla por clave y fragmentos de tema reemplazan secciones. Una capa conceptual no crea precedencias físicas inexistentes.
4. Comparar B/C/P con fixtures. Probar primera adopción, conflicto conservado, reemplazo seleccionado, repetición, retirada y preservación ajena para cualquier transformador nuevo. Incompatibilidad no se resuelve con force ni reemplazo de archivo personal.
5. Ejecutar `check`, `./test/all` y planes sintéticos relevantes. Si cambia un consumidor, usar [upstream-compatibility](upstream-compatibility.md). Para apariencia, [visual-verification](visual-verification.md); sintaxis/mock no equivalen a compositor real.
6. Documentar valores heredados, reglas acumulativas y conflictos pendientes. Una futura transformación de estado requiere [migration](migration.md); no añadirla como requisito decorativo.

Salida: diferencia acotada, inventario coherente, pruebas y límites de integración. Aplicar al escritorio exige su gate, aunque el plan sea válido.
