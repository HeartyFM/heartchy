# Heartchy Development Foundation

main @ 28b0e6c no se ha integrado. Rama actual `feature/updates-first-test`: UI previa conservada en a6b2b21 y Core endurecido en ced2ddf.

- Core Cristal y contratos ARQ-001/002/003/004/DEV-001 conservados. Local Test histórico c22ac62 pasó con rollback exacto; Shell ya coincidía, no demuestra primera escritura gráfica stock.
- Actualizador de prueba implementado: GitHub público, firma OpenSSH, runtime portátil, TUI reutilizada y mismas primitivas Core. Contrato/comandos: [updater](docs/updater.md); aceptación/evidencia: [Feature](work/features/updates-first-test.md). Sin updater Omarchy, menú real, paquetes ni autoactualización del cliente.
- Check PASS; cierre aislado `full-03.log`: **102 PASS / 0 FAIL / 0 SKIP / 1 NOT_RUN**, incluidos HTTP loopback, A→B por TUI, preferencias y recuperación. Revisión independiente de lectura cerró sus hallazgos. El NOT_RUN corresponde a Core gráfico desechable; cambio global de tema sigue separado y no probado.
- Repositorio público HeartyFM/heartchy y clave exclusiva elegidos por delegación expresa. Confianza pública en `trust/heartchy-test.json`; privada fuera de Git. Licencia propia, estable, instalación permanente y Rafa pendientes de autorización separada.
- Siguiente paso de esta tarea: preparar artefacto desde commit limpio, publicación prerelease autorizada tras resumen exacto, descarga anónima y prueba del mismo artefacto. Todavía no se atribuye GitHub real ni rendering funcional a las pruebas de laboratorio.
- Updater en Diego, Core gráfico desechable y Rafa **NOT_RUN**. Ninguna configuración personal se aplicó en este encargo; no instalación permanente.
