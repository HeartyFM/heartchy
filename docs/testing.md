# Modelo de pruebas

Una prueba acredita una revisión y un alcance, no toda Heartchy. El procedimiento operativo vive en [testing](../agents/skills/testing.md); las Skills de cada subsistema eligen niveles obligatorios según aceptación y efectos.

| Nivel | Qué acredita | Cuándo corresponde |
|---|---|---|
| STATIC | Formato, rutas, manifiestos, enlaces y contratos declarados | Cambios de fuentes/configuración/documentación/herramientas |
| UNIT | Decisiones de lógica pura | Nueva lógica o bug de decisión/transformación |
| ISOLATED_INTEGRATION | Componentes reales interactuando con fixtures/stubs/namespaces | IO, comandos, estado, contratos y herramientas |
| VISUAL | UI observada e inspeccionada realmente | Cualquier cambio visible; guía [visual](../agents/skills/visual-verification.md) |
| LOCAL | Ejecución real de la revisión en Diego autorizada | Aceptación que depende de su instalación; Local Test Gate |
| TARGET | Ejecución real en un equipo objetivo identificado | Afirmar soporte/prueba en ese equipo; Rafa requiere evidencia propia |

No todo cambio necesita todos. Una misma sesión puede acreditar VISUAL y LOCAL sólo si ambas evidencias existen. Un screenshot histórico, mock o compilación no demuestra VISUAL. Una prueba en VM no demuestra LOCAL. Un runner verde no demuestra TARGET.

Resultados por prueba/nivel: **PASS** = comprobación ejecutada y satisfecha; **FAIL** = comprobación ejecutada que falló; **SKIP** = caso deliberadamente excluido por no aplicar o por guard de recursión, con motivo; **NOT_RUN** = prueba requerida/prevista sin ejecutar, por entorno/dependencia/autorización ausente. N/A explica un nivel no aplicable, no es PASS. Ausencia de entorno gráfico es NOT_RUN. Reportar separados; no ocultar fallos detrás de skips.

## Runner actual

`./test/all` usa Bubblewrap: proyecto de sólo lectura, temporal explícito en `/sandbox`, red/IPC/PID separados, entorno limpio, HOME/sockets y sesión real ocultos. `/usr` y bibliotecas sólo aportan runtimes de lectura. No basta cambiar HOME. Una auditoría de procesos en las herramientas probadas rechaza mutadores; comparación de archivos detecta escrituras fuera del ámbito dentro del temporal. Fixtures y copia portátil no requieren la evidencia privada original.

`./test/all --only <nombre-del-test>` permite una prueba enfocada dentro del mismo aislamiento. La suite completa sigue siendo el cierre para contratos/herramientas compartidas; un filtro desconocido falla. El runner no instala dependencias ni hace fallback al host. Devuelve 1 si existe FAIL, 2 si no puede iniciar por falta de requisitos, 0 si las comprobaciones ejecutadas pasan aunque haya NOT_RUN explícitos (no equivale a todos los niveles probados).

La suite mantiene ARQ-001/002/003, rutas/symlinks, conservación y planes caducados. ARQ-004 añade aplicación/retirada por propiedad, journal, fallos de preparación/commit, muerte de proceso, recovery, permisos posteriores y descriptor local en un HOME simulado. DEV-001 añade generación de documentos, ausencia de efectos, errores y routing/enlaces de Skills. La prueba portátil ejecuta el mismo runner desde copia temporal; sólo omite su recursión con SKIP, sin quitar sandbox. `check` valida fuentes y contratos documentales; no evalúa si una recomendación recibió aprobación ni si una Skill garantiza decisiones humanas correctas.

## Evidencia y prueba gráfica pendiente

Registrar junto a la Feature: revisión/hash, versiones/contexto, comando o pasos, resultado por nivel, quién inspeccionó, artefactos/hashes y limitaciones. Resultados generados en build o temporal explícito; resumen durable en work. Evitar secretos y logs privados. Mantener evidencia anterior identificada cuando cambie la revisión; no atribuirla al código nuevo.

Para Cristal siguen pendientes un entorno desechable autorizado y nueva inspección de barra/menú, controles, opacidad, temas y slidevert/dwindle con capturas y vídeo. Procedimiento en [visual-verification](../agents/skills/visual-verification.md); nueva prueba personal requiere [Local Test Gate](development.md#gates). Esta entrega no toca la sesión de Diego.

## Actualizador de prueba

`test/update_tests.py` amplía la suite: entregas A/B acumulativas firmadas con claves efímeras, primera escritura stock de los cuatro archivos, preferencias/conflictos, firma/inventario/archivo hostil, transporte HTTP loopback, canal/paginación/cache, TUI Gum/Fzf real por PTY, runtime extraído, concurrencia y recuperación. La revisión B de laboratorio cambia bytes del módulo sin cambiar los valores Cristal; no acredita una evolución visual. Publicación usa stub: eso no es GitHub real.

`test/release-artifact --delivery RUTA --trust RUTA` es el runner para una descarga publicada: la monta sólo lectura, verifica antes de ejecutar su runtime extraído y prueba first-write stock/validate/no-op/rollback sin compositor. OpenSSH obtiene sólo passwd sintético; red, IPC y HOME siguen aislados. Resultado gráfico, Diego y Rafa permanecen NOT_RUN. Evidencia de API/descarga real y rendering se registra separada en la Feature.
