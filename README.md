# Heartchy Development Foundation

Baseline de desarrollo local para una capa propia sobre Omarchy, inicialmente Cristal. Diego / Hearty_FM dirige alcance, experiencia y rumbo. Incluye Core, check/stage/plan, política de conflictos, planificación Lua, Skills, flujo de Features y pruebas aisladas: **PRUEBA / PRE-RELEASE — NO INSTALADO PERMANENTEMENTE**. El LOCAL TEST Core de c22ac62 pasó y se retiró mediante rollback; no hay instalación permanente. La integración gráfica en entorno desechable sigue NOT_RUN; Rafa no está probado. Incluye primitivas explícitas apply/validate/rollback/recover para el Core. Añade un actualizador **de prueba** con GitHub Releases, firma y runtime portátil: [contrato y comandos](docs/updater.md). No incluye instalación permanente, autoactualización del cliente, plugins, servicios ni Power Manager.

Las únicas fuentes del Core están en `core/`: un módulo Lua, tokens Cristal y una intención JSON de transparencia. No contiene el layout, los plugins, el fondo, la fuente, el hardware ni las aplicaciones del escritorio de Diego. Los componentes integrados de Omarchy siguen siendo consumidores necesarios.

Desde la raíz del checkout:

```sh
./tools/heartchy-dev --help
./tools/heartchy-dev check
./test/all
./tools/heartchy-dev stage --output build/review-001
```

`check` lee y valida; `stage` crea un destino nuevo bajo `build/` y copia recursos con un inventario reproducible. Ninguno aplica configuración. El nombre de candidato debe ser nuevo cada vez. Las rutas relativas de `--output` se interpretan desde el repositorio, aunque se invoque desde otro directorio. Para un temporal aislado, usar una copia del proyecto y su propio `build/`.

`./tools/heartchy-dev plan --help` presenta el planificador de ARQ-002 para destinos simulados explícitos. Su [política aprobada y formatos](docs/architecture.md#politica-arq-002) tienen una única definición; los [ejemplos de desarrollo](docs/development.md) usan fixtures del proyecto. La implementación está en [heartchy-plan.py](tools/heartchy-plan.py). Aplicación controlada: [contrato ARQ-004](docs/architecture.md#aplicacion-arq-004) y [procedimiento](docs/core-application.md). La prueba personal temporal terminó con configuración PRE/POST idéntica; no hay instalación permanente.

ARQ-003 añade [planificación Lua acotada](docs/architecture.md#lua-arq-003): módulo completo y bloque de conexión como recursos distintos, con reconocimiento léxico en [heartchy-lua-plan.py](tools/heartchy-lua-plan.py). `--resource hypr` selecciona ambos. Ninguno ejecuta Lua del destinatario ni acredita integración gráfica.

Requisitos de desarrollo: Linux, Python 3.11+, Lua 5.4/5.5 y, para pruebas, Bubblewrap con namespaces habilitados. Git permite registrar identidad del checkout; no hace falta historial para trabajar. No se instalan dependencias. El runner se niega a ejecutar sin aislamiento; no basta con cambiar HOME ni vaciar algunas variables.

- [Arquitectura y contratos](docs/architecture.md): propiedad, precedencia, conflictos y límites.
- [Desarrollo y pruebas](docs/development.md): recorrido de trabajo, comandos y prueba gráfica futura.
- [Investigación upstream](docs/upstream.md): referencias fijadas, comparación con lo instalado y prácticas adaptadas.
- [Procedencia](docs/provenance.json): hashes de importación y alcance de la evidencia histórica.
- [Estado vigente](STATUS.md) y [atribuciones](NOTICE.md).

GitHub Releases público y firma exclusiva de Heartchy están autorizados para prerelease; licencia del código propio y distribución estable siguen pendientes. Un candidato con hashes no es una release, y una prueba aislada no acredita instalación personal ni funcionamiento en Rafa.

Para empezar trabajo importante: `./tools/heartchy-dev feature new <slug>` crea únicamente su documento en `work/features/`. Leer la [Skill principal](agents/skills/feature-development.md) y los [estados/gates](docs/development.md). La plantilla no autoriza implementar, probar en Diego ni publicar. Routing en [AGENTS](AGENTS.md); [niveles de prueba](docs/testing.md) y [contratos consumidos](docs/upstream-contracts.md).

Mockup UX independiente de Updates (datos ficticios, Gum/Fzf): `./bin/heartchy-updates-mockup --window` (ventana TUI stock). [Ejecución y límites](docs/updates-mockup.md); [Feature y evidencia](work/features/updates-mockup.md). No invoca el actualizador ni se integra en el menú real.
