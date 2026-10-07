---
name: cli-command
description: Crear o modificar comandos heartchy-* y herramientas CLI con análisis de argumentos y efectos separados.
---
# Comandos CLI

1. Confirmar comportamiento y rutas en la Feature. Comandos de producto futuros van en `bin/heartchy-*`; herramientas internas permanecen en `tools/`. No sustituir `omarchy-*` ni crear un router nuevo sin necesidad.
2. Inspeccionar helpers públicos existentes antes de duplicar utilidades. Registrar dependencias y ausencia de API; no inventar fallback silencioso. La lógica pura acepta datos explícitos; el adaptador concentra IO y efectos.
3. Analizar todos los argumentos antes de operar. `--help`, subayuda y argumentos inválidos no crean archivos ni procesos de trabajo. Explicar efectos y códigos de salida implementados; errores con contexto útil y sin secretos.
4. Delimitar rutas/propiedad, enlaces y sobrescrituras. No depender del CWD ni usar HOME personal por defecto para herramientas de desarrollo. Ningún sudo oculto; si hace falta privilegio, [privileged-integration](privileged-integration.md).
5. Con [testing](testing.md), probar lógica, ayuda, entradas inválidas, CWD ajeno, copia temporal, fallo de dependencia, permisos y ausencia de efectos fuera del ámbito. Usar stubs/auditoría e inputs hostiles; nunca un mutador real para probar su bloqueo.

Salida: comando pequeño, ayuda honesta, contrato de IO y evidencia STATIC/UNIT/ISOLATED_INTEGRATION según efectos. No exigir VISUAL a una CLI sin UI gráfica.
