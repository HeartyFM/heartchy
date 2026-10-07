---
name: shell-ui
description: Investigar o cambiar interfaces Omarchy/Quickshell mediante contratos públicos y validación visual real.
---
# Interfaces Shell

1. Leer [límites de interfaces](../../docs/architecture.md) y [contratos upstream](../../docs/upstream-contracts.md). Contrastar documentación con consumidor instalado/fijado antes de elegir integración; registrar API soportada, API ausente o bug upstream.
2. Usar IPC oficial cuando exista, comprobando sus efectos. No depender de `bar.shell`, `_services`, geometría privada, recorrido de padres ni identidad first-party falsa. Una fachada ausente no autoriza eludirla.
3. Separar modelo/lógica de QML cuando permita probar estados y eventos sin compositor. Si existe backend, definir su contrato independientemente de la UI. No levantar Quickshell adicional por widget ni editar `/usr/share/omarchy`.
4. Una interfaz que necesite plugin es propuesta separada, fuera de Core, sujeta a Product Gate; esta Skill no autoriza crear ni activar plugins.
5. Probar modelo y contratos con [testing](testing.md); completar [visual-verification](visual-verification.md) para cambios visibles, incluyendo teclado, foco y estados. Sin entorno, VISUAL NOT_RUN impide declarar aceptación visual.

Salida: integración pública trazable, tests aislados y evidencia visual inspeccionada (o falta explícita). Cambios upstream necesarios se proponen como contribución o parche acotado con base conocida.

## TUI Omarchy

Para prototipos TUI, leer logo/show-logo, update-confirm, restart-gum, template gum_env y capacidades **instaladas** de Gum/Fzf. Qt/Quickshell no define estos controles. Reutilizar recursos originales y sólo exports de color comprobados en el proceso; no ejecutar wrappers/instaladores para obtener un preview ni modificar la terminal. Registros multilínea deben devolver IDs estables, restaurar navegación y probar termios/respuestas de protocolo. Inspeccionar pantalla amplia/reducida y el recorrido completo con [visual-verification](visual-verification.md). Ejemplo y límites concretos: [maqueta Updates](../../docs/updates-mockup.md).

Si el widget no expone un evento necesario, comprobar su consumidor y delimitar el adaptador antes de sustituirlo. Una preview con paletas/templates por proceso evita activar themes globales; acreditar ese alcance, no afirmar prueba de hooks/Shell/overrides. Respuestas de protocolo completas o fragmentadas no son teclas; animaciones deben poder omitirse/interrumpirse sin dejar la TTY alterada.

Para tema en vivo, comprobar generaciones completas y sustitución de directorios, conservar estado de widgets y restaurar cualquier paleta temporal. Separar PALETA SIMULADA, RENDERIZADO EN TERMINAL y CAMBIO REAL DE TEMA EN VIVO. Comprobar contraste sobre la composición real transparente, no sólo el fondo nominal; delimitar superficies propias si necesitan fondo sólido. Mecanismo y comprobación pendiente: [UX-004](../../docs/updates-mockup.md#tema-en-vivo--ux-004).
