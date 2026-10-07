---
name: upstream-compatibility
description: Revisar cambios de Omarchy sólo en los contratos consumidos por Heartchy y registrar compatibilidad con evidencia.
---
# Compatibilidad upstream

1. Partir del [registro de contratos](../../docs/upstream-contracts.md) y alcance de la Feature. Registrar versión/paths/hashes instalados mediante lectura y commit upstream separado; no asumir igualdad por versión.
2. Comparar sólo consumidores afectados y sus callers necesarios: resolución, claves, fachadas y semántica. Consultar documentación fijada y código consumidor cuando el detalle determine compatibilidad. No recorrer/rebasar todo Omarchy.
3. Clasificar diferencia como compatible comprobada, no probada o incompatible con causa concreta según el registro. Una recomendación de adaptación sigue siendo propuesta; no autoeditar tras `omarchy update`.
4. Ejecutar tests de contrato y [testing](testing.md). Cambios visibles necesitan [visual-verification](visual-verification.md) antes de certificar ese alcance; mocks no amplían soporte real.
5. Registrar contratos cambiados, entorno, evidencia y límites. Si falta API, documentar contribución upstream o parche/fork acotado con base y pruebas; Diego decide arquitectura. No editar instalado ni añadir hook de reimposición.

Salida: comparación pequeña por contrato y clasificación explicada; la actualización oficial de Omarchy permanece independiente.
