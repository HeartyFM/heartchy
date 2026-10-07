# Trabajar en Heartchy

- Leer `STATUS.md`, `docs/architecture.md` y el documento de trabajo pertinente. Diego / Hearty_FM decide producto; el agente resuelve detalles internos reversibles dentro del alcance autorizado. Autoridad, estados y gates: [desarrollo](docs/development.md).
- Una tarea coherente por cambio, un responsable y un escritor por subsistema. Investigación paralela y revisión independiente de sólo lectura son útiles; escrituras independientes usan ramas/worktrees separados. No llamar independiente a una segunda lectura propia.
- Editar fuentes del repositorio; nunca capturar `~/.config` como siguiente versión. Preservar preferencias según [ARQ-002](docs/architecture.md#politica-arq-002); no ampliar Core ni saltar contratos bloqueados.
- No modificar el escritorio, `/etc` o `/usr/share`, leer secretos, instalar dependencias ni introducir efectos privilegiados sin el gate y alcance pertinentes. Una Skill no concede autorización. No usar `omarchy dev link` ni refresh como atajo de desarrollo.
- Lógica comprobable fuera de la sesión; interfaces públicas verificadas, sin fallbacks silenciosos. Respetar el lenguaje (Python convencional; Lua con dos espacios), comentarios por intención, ayuda y errores sin efectos.
- Leer sólo las Skills aplicables antes de trabajar; son procedimientos locales enlazados, no Skills instaladas globalmente:

| Trabajo | Skill |
|---|---|
| Función nueva o cambio importante | [feature-development](agents/skills/feature-development.md) |
| Core, Hyprland, tokens, theming | [core-config](agents/skills/core-config.md) |
| Comando `heartchy-*` o herramienta CLI | [cli-command](agents/skills/cli-command.md) |
| Interfaz Omarchy/Quickshell | [shell-ui](agents/skills/shell-ui.md) |
| Proceso persistente | [service-development](agents/skills/service-development.md) |
| Operaciones privilegiadas | [privileged-integration](agents/skills/privileged-integration.md) |
| Transformación de estado existente | [migration](agents/skills/migration.md) |
| Escribir/ejecutar pruebas | [testing](agents/skills/testing.md) |
| Cualquier cambio visible | [visual-verification](agents/skills/visual-verification.md) |
| Cambio de contrato/versión upstream | [upstream-compatibility](agents/skills/upstream-compatibility.md) |
| Preparar un candidato para publicación futura | [release-preparation](agents/skills/release-preparation.md) |

- Ejecutar `./tools/heartchy-dev check` y `./test/all` para cambios de herramientas/contratos; pruebas enfocadas según Skill. No quitar aislamiento para conseguir PASS. Reportar PASS, FAIL, SKIP y NOT_RUN; evidencia automática no acredita UI ni Rafa.
- Procedimientos en Skills, razones/contratos en docs, aceptación/evidencia de la tarea en work, estado breve en STATUS. No copiar el mismo contrato entre ellos.
- No crear infraestructura futura vacía. Commits locales sólo con autorización e identidad real; no implican permiso para remotos, push, tags, publicación, apply/install/update, plugins ni cambios de sesión. My Omarchy y OmaPacks quedan fuera.
