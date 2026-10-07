---
name: visual-verification
description: Inspeccionar cambios visibles en una UI real, con capturas o vídeo y autorización del entorno.
---
# Verificación visual

1. Identificar estados/capturas de referencia y criterios visuales en la Feature. Preferir entorno desechable autorizado; si es Diego, obtener Local Test Gate antes de modificar o conducir su sesión. La Skill por sí sola no autoriza pruebas visuales reales.
2. Registrar versiones, revisión/hash, tema, escala y entorno pertinentes. Preparar retorno al baseline; no reutilizar capturas históricas como prueba de una transformación nueva.
3. Ejercitar y capturar estados relevantes. Inspeccionar realmente clipping, solapamientos, spacing, contraste, foco, teclado y hover/selected/pressed cuando apliquen. Comparar referencia y propuesta; no dar PASS por generar un PNG.
4. Para animaciones/transiciones, grabar y revisar vídeo corto cuando imágenes estáticas no demuestren continuidad, tiempo o estado final. Usar sólo herramientas comprobadas en ese entorno, no asumir comandos futuros.
5. Guardar evidencia sin datos privados, anotar revisor y defectos. Restaurar estado y cerrar sólo procesos abiertos por la prueba. Si falla restauración, documentar y detener más cambios.

Salida: VISUAL PASS/FAIL vinculado al resultado observado, o NOT_RUN con causa. VISUAL en una VM no es LOCAL en Diego; ninguna acredita TARGET/Rafa.
