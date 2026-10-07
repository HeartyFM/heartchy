"""Shared native logo frames and optional development comparator. No TTY engine.

Uses ttfx 0.3.2's *internal* parity harness (pinned, not a public stable API).
No engine code copied. Provenance/limitations: docs/updates-mockup.md.
"""
import re
import select
import shutil
import subprocess
import termios
import time
import unicodedata

WIDTH, HEIGHT, FPS = 97, 10, 30
ENGINE = "/usr/bin/ttfx"
ENGINE_VERSION = "ttfx 0.3.2"
EFFECTS = (
    ("wipe", "Barrido anterior", "Referencia Heartchy anterior · sólo para comparar."),
    ("slice", "Slice", "ttfx · dos mitades entran desde extremos opuestos."),
    ("middleout", "Middleout", "Predeterminada elegida por Diego · expansión desde el centro."),
    ("beams", "Beams", "ttfx · haces revelan el texto. Muestra larga; poco apta para menú."),
    ("decrypt", "Decrypt", "ttfx · descifrado real. Muestra muy larga; Esc permite omitirla."),
    ("none", "Sin animación", "Referencia instantánea · logo estático exacto."),
)
PARAMETERS = {
    "slice": ("--movement-speed", "1.5"),
    "middleout": ("--center-movement-speed", "6", "--full-movement-speed", "1.2"),
    "beams": ("--beam-delay", "1", "--beam-row-speed-range", "400-400",
              "--beam-column-speed-range", "100-100", "--beam-gradient-frames", "1",
              "--beam-gradient-steps", "1", "--beam-gradient-stops", "ffffff",
              "--final-gradient-frames", "1", "--final-gradient-steps", "1",
              "--final-gradient-stops", "ffffff", "--final-wipe-speed", "100"),
    "decrypt": ("--typing-speed", "1000"),
}
ENGINE_ENV = {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "LC_ALL": "C.UTF-8"}


def command(effect, height=HEIGHT):
    if effect not in PARAMETERS or height not in (9, 10):
        raise ValueError("efecto ttfx no autorizado")
    return [ENGINE, "--parity-dump", "--max-frames", "1200", "--seed", "7", "--no-color",
            "--ignore-terminal-dimensions", "--canvas-width", str(WIDTH),
            "--canvas-height", str(height), "--anchor-text", "nw", effect, *PARAMETERS[effect]]


def static_rows(rows):
    if len(rows) != HEIGHT or any(len(r) > WIDTH for r in rows):
        raise ValueError("logo fuera del contrato 97 × 10; no se recorta")
    return tuple(r.ljust(WIDTH) for r in rows)


def decode_frames(data, expected):
    """Only length-prefixed UTF-8 rectangles, with no ANSI/control interpreter."""
    if len(data) > 4_000_000:
        raise ValueError("salida ttfx excesiva")
    offset = int(not expected[0].strip())
    frames, count = [], 0
    while data:
        length, sep, rest = data.partition(b"\n")
        if not sep or not re.fullmatch(rb"[0-9]{1,4}", length):
            raise ValueError("cabecera de cuadro ttfx no compatible")
        size = int(length)
        if not 1 <= size <= 4000 or rest[size:size + 1] != b"\n":
            raise ValueError("cuadro ttfx truncado")
        try:
            rows = rest[:size].decode("utf-8").split("\n")
        except UnicodeDecodeError as exc:
            raise ValueError("UTF-8 ttfx inválido") from exc
        if len(rows) != HEIGHT - offset or any(len(r) != WIDTH for r in rows):
            raise ValueError("rectángulo ttfx fuera del logo")
        if any(not c.isprintable() or unicodedata.combining(c) or
               unicodedata.east_asian_width(c) in "WF" for r in rows for c in r):
            raise ValueError("control/caracter ancho ttfx no permitido")
        frame = (" " * WIDTH,) * offset + tuple(rows)
        # Ignore repeated monochrome frames: color-only fades have no visible
        # change after --no-color. Never drop a distinct geometry/glyph frame.
        if not frames or frame != frames[-1]:
            frames.append(frame)
        count += 1
        if count >= 1200:
            raise ValueError("efecto truncado por límite de cuadros")
        data = rest[size + 1:]
    if not frames or frames[-1] != expected:
        raise ValueError("ttfx no terminó en el logo original exacto")
    return tuple(frames)


class NativeFrames:
    def __init__(self):
        self.checked = False
        self.cache = {}

    def get(self, effect, rows):
        expected = static_rows(rows)
        key = effect, expected
        if key in self.cache:
            return self.cache[key]
        if not self.checked:
            version = subprocess.run([ENGINE, "--version"], env=ENGINE_ENV, capture_output=True, timeout=2, check=True)
            if version.stdout.decode().strip() != ENGINE_VERSION:
                raise ValueError("animación nativa requiere ttfx 0.3.2; contrato interno no verificado en otra versión")
            self.checked = True
        # Piped stdin/stdout/stderr, finite frames, no terminal inheritance.
        # subprocess.run kills/waits on timeout or interruption, no idle engine.
        offset = int(not rows[0].strip())
        result = subprocess.run(command(effect, HEIGHT - offset), input="\n".join(rows[offset:]).encode(),
                                env=ENGINE_ENV, capture_output=True, timeout=2, check=False)
        if result.returncode:
            raise ValueError("ttfx rechazó la muestra: " + repr(result.stderr.decode(errors="replace")[:200]))
        frames = decode_frames(result.stdout, expected)
        self.cache[key] = frames
        return frames


def transition_frames(before, after_frames):
    """Own exit, native reveal: explicitly not a native two-logo morph."""
    before = static_rows(before)
    for cut in (WIDTH // 3, WIDTH * 2 // 3, WIDTH):
        yield tuple(" " * cut + r[cut:] for r in before), False
    for rows in after_frames:
        yield rows, True


def frame_output(rows, color):
    if len(rows) != HEIGHT or any(len(r) != WIDTH for r in rows):
        raise ValueError("cuadro fuera de la región del logo")
    return "\033[?2026h" + "".join(f"\033[{i+2};2H\033[49m{color}{row}\033[0m"
                                    for i, row in enumerate(rows)) + "\033[?2026l"


def compare(ui, logo, keys, heading, banner, indexed, color_escape):
    """Small developer mode; return to the unchanged mockup without saving."""
    original = termios.tcgetattr(0)
    attributes = original[:]; attributes[3] &= ~(termios.ECHO | termios.ICANON)
    termios.tcsetattr(0, termios.TCSANOW, attributes)
    engine = NativeFrames()
    selected, target, shown = 0, "HEARTCHY", "OMARCHY"
    pending, queued, since = b"", [], time.monotonic()
    status = "Elegir no cambia la animación predeterminada."
    size = shutil.get_terminal_size()

    def poll(timeout):
        nonlocal pending, since
        data = b""
        if select.select([0], [], [], timeout)[0]:
            import os
            data = os.read(0, 1024)
            if not data:
                return ["quit"]
            since = time.monotonic()
        events, pending = keys(pending, data, time.monotonic() - since > .08,
            {b"\x1b[D": "omarchy", b"\x1b[C": "heartchy"})
        return events

    def draw(refresh_logo=False):
        if refresh_logo:
            ui.brand(shown)
        top = len(banner("OMARCHY", size.columns - 1, size.lines, ui.pink).split("\n")) + 3
        lines = ["Comparador de logos · sin guardar elección", ""]
        lines += [("> " if i == selected else "  ") + name for i, (_, name, _) in enumerate(EFFECTS)]
        lines += ["", EFFECTS[selected][2], "← Heartchy → Omarchy    |    → Omarchy → Heartchy",
                  "Enter repetir dirección · ↑/↓ elegir · Esc volver", status]
        width = max(1, size.columns - 2)
        for i, line in enumerate(lines[:max(0, size.lines - top)]):
            role = "pink" if i == selected + 2 else "help"
            print(f"\033[{top+i};2H\033[0K" + ui.surface(line[:width], role), end="")
        print("\033[?25l", end="", flush=True)

    def paint(rows, name):
        color = (indexed("loose-pink" if name == "HEARTCHY" else "logo") if ui.indexed_colors else
                 color_escape(ui.pink) if name == "HEARTCHY" else "\033[32m")
        print(frame_output(rows, color), end="", flush=True)

    try:
        if ui.startup_input:
            queued, pending = keys(pending, ui.startup_input, False,
                                   {b"\x1b[D": "omarchy", b"\x1b[C": "heartchy"})
            ui.startup_input = b""
        draw(True)
        while not ui.model.closed:
            if ui.theme_error:
                raise OSError("watcher de paleta: " + ui.theme_error)
            queued.extend(poll(.04 if not queued else 0))
            new_size = shutil.get_terminal_size()
            if size != new_size:
                size = new_size; draw(True)
            if not queued:
                continue
            # Reduce a burst without playing intermediate selections.
            play = False
            for key in queued:
                if key == "quit":
                    ui.model.closed = True; return
                if key == "back":
                    return
                if key in ("prev", "next"):
                    selected = (selected + (1 if key == "next" else -1)) % len(EFFECTS)
                    play = False
                elif key in ("heartchy", "omarchy", "enter"):
                    if key != "enter":
                        target = key.upper()
                    play = True
            queued.clear()
            if not play:
                draw(); continue
            before = "OMARCHY" if target == "HEARTCHY" else "HEARTCHY"
            effect = EFFECTS[selected][0]
            full = all("cabecera compacta" not in heading(n, size.columns - 1, size.lines) for n in (before, target))
            status = "Reproduciendo " + EFFECTS[selected][1] + " · " + before + " → " + target
            draw()
            frames = None
            try:
                if effect in PARAMETERS and ui.animation and full:
                    frames = tuple(transition_frames(logo(before), engine.get(effect, logo(target))))
            except (ValueError, OSError, subprocess.SubprocessError) as exc:
                status = "NO DISPONIBLE: " + str(exc)
                draw(); continue
            # Generation uses pipes but may overlap a resize/input. Recheck
            # before the first write, not only after the first native frame.
            queued.extend(poll(0))
            resized_before = shutil.get_terminal_size() != size
            if resized_before:
                size = shutil.get_terminal_size()
                full = False
            started, revision = time.monotonic(), ui.revision
            interrupted = bool(queued or resized_before)
            if ui.animation and full and effect != "none" and not interrupted:
                paint(static_rows(logo(before)), before)
                count = len(frames) if frames is not None else 16
                interval = 1 / FPS if frames is not None else .45 / count
                for i in range(count):
                    if shutil.get_terminal_size() != size:
                        interrupted = True; break
                    if frames is None:
                        ui.paint_wipe(before, target, (i + 1) / count)
                    else:
                        rows, incoming = frames[i]
                        paint(rows, target if incoming else before)
                    queued.extend(poll(max(0, started + (i + 1) * interval - time.monotonic())))
                    if queued or ui.revision != revision or shutil.get_terminal_size() != size:
                        interrupted = True; break
            elapsed = time.monotonic() - started
            shown = target
            resized = shutil.get_terminal_size() != size
            size = shutil.get_terminal_size()
            if full and not resized:
                paint(static_rows(logo(target)), target)
            status = ("Interrumpida; logo final restaurado" if interrupted else "Última muestra") + f" · {elapsed * 1000:.0f} ms"
            if not ui.animation or not full:
                status += " · omitida (--no-animation / cabecera compacta)"
            draw(resized or not full)
    finally:
        termios.tcsetattr(0, termios.TCSANOW, original)
        print("\033[0m\033[?25h", end="", flush=True)
