---
name: privileged-integration
description: Delimitar operaciones futuras que requieran root y su autorización, sin introducir privilegios implícitos.
---
# Integración privilegiada

1. Precisar operación, recurso y razón por la que una API de usuario no basta. Investigar sin privilegio y preparar alternativa mínima; no elevar todo el proceso/UI por una operación.
2. Antes de introducir una operación privilegiada nueva, obtener Privilege Gate de Diego para ese límite concreto. Aprobar una Feature no lo implica salvo que ya nombre expresamente esa operación; ver [gates](../../docs/development.md#gates).
3. Entrada validada y acotada en el límite privilegiado. Usuario normal por defecto; no sudo oculto, passwords guardadas, secretos en argumentos/logs ni helpers privilegiados arbitrarios. Revisar abuso de rutas/enlaces y autoridad del llamador.
4. Diseñar rollback y comportamiento al cancelar autorización o fallar a mitad. Si sustituye estado significativo, aplicar también [migration](migration.md).
5. Exigir UNIT de validación e ISOLATED_INTEGRATION con stubs de autorización, negativas, fallo parcial y retirada. Prueba privilegiada real sólo en entorno explícitamente autorizado; Local Test Gate para Diego, nunca desde tests normales.

Salida: superficie de privilegio revisada, autorización referenciada, pruebas negativas y recuperación. Esta Skill no implementa ni concede privilegios.
