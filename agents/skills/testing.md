---
name: testing
description: Elegir y ejecutar pruebas enfocadas con aislamiento y evidencia por nivel, sin confundir mocks con escritorio real.
---
# Pruebas

1. Mapear aceptación a [niveles](../../docs/testing.md). STATIC para formatos/contratos; UNIT para decisiones puras; ISOLATED_INTEGRATION para interacción/IO. Añadir niveles reales sólo cuando prueben comportamiento relevante; N/A razonado para los demás.
2. Ejecutar pruebas enfocadas tras editar; suite completa para herramientas/contratos compartidos y antes de cerrar esta entrega. Punto de entrada `./test/all`; `./tools/heartchy-dev check` valida fuentes y documentación. No instalar dependencias desde el runner.
3. Fixtures, stubs y namespaces apropiados. El runner debe ocultar IPC, sockets y entorno de sesión; cambiar HOME no aísla D-Bus ni servicios. No ejecutar lógica instalada con efectos suponiendo que el nombre «test» la vuelve segura.
4. Cubrir errores, repetición, ámbito de rutas, preferencias ajenas y copia independiente cuando la lógica los afecte. Verificar efectos observables; una frase literal o existencia de archivo no demuestra el contrato.
5. Registrar por nivel revisión/hash, entorno, comando, resultado, artefactos y límite. PASS, FAIL, SKIP y NOT_RUN según [definición única](../../docs/testing.md); dependencia ausente no produce PASS. Investigar fallos sin rebajar protecciones.
6. Para entregas usar laboratorio A/B y HTTP loopback con confianza efímera separada. Firma/archivo hostil nunca se publica. Tras publicación autorizada, `./test/release-artifact --delivery RUTA --trust RUTA` verifica y prueba el artefacto descargado en namespaces. No cambiar HOME como único aislamiento ni confundir UI demo con aplicación funcional.
7. Cambios visibles derivan a [visual-verification](visual-verification.md). Pruebas sobre Diego necesitan Local Test Gate, aunque el comando sea una prueba. Sin entorno adecuado, NOT_RUN para el nivel requerido; no acreditar LOCAL/VISUAL ni estados que los requieran. Esto no impide acreditar las pruebas aisladas realizadas.

Salida: resultados reproducibles y cobertura pendiente concreta, sin prometer producción, publicación ni Rafa.
