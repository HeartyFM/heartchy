---
name: service-development
description: Evaluar y desarrollar procesos persistentes cuando una necesidad real no se resuelve con comando, hook o evento.
---
# Servicios

1. Justificar persistencia con un requisito observable. Comparar comando puntual y hook/evento comprobado; no convertir automáticamente una Feature en daemon. Diego decide dependencias/arquitectura relevantes por los [gates](../../docs/development.md#gates).
2. Definir ciclo de vida, propietario, datos/configuración, fallos, límites de recursos y retirada. Usuario normal por defecto; no habilitar una unidad para validar su sintaxis.
3. Si hay UI, separar backend ↔ contrato/IPC ↔ UI. Documentar mensajes, errores y compatibilidad; el backend no depende de widgets, geometría ni procesos privados de Shell.
4. Crear `services/` sólo con trabajo autorizado real. Reutilizar eventos públicos; no registrar hooks que reimpongan Heartchy tras cada update. Para privilegios, [privileged-integration](privileged-integration.md).
5. Probar con [testing](testing.md) inicio/parada, repetición, fallo/reintento acotado, cliente ausente, persistencia y limpieza en aislamiento. Stubs y namespaces; ninguna llamada al systemd del usuario real desde la suite normal.

Salida: justificación, contrato, pruebas de ciclo de vida y plan reversible para Local Test Gate. Un mock de IPC no acredita servicio instalado.
