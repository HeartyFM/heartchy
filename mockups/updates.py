"""Fake update model and native Gum/Fzf UI; no configuration writes or updater."""
import argparse
import os
import shutil
import subprocess
import select
import signal
import termios
from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
import re
import sys
import textwrap
import time
import tomllib
import ctypes
import struct
import threading

SIMULATION_SECONDS = 8.0
CATALOG = Path(__file__).with_name("updates.json")
ASSETS = Path(__file__).with_name("assets")
PINK = "#ff87af"
WIPE_SECONDS = .45
WIPE_FRAMES = 16
THEMES = Path("/usr/share/omarchy/themes")
SIMULATION = "SIMULACIÓN · Datos ficticios · Ningún cambio real"
THEME_KEYS = {"FOREGROUND", "BACKGROUND", "BORDER_FOREGROUND", "BORDER_BACKGROUND"} | {
    "GUM_" + component + "_" + role + "_" + color
    for component, roles in {"CONFIRM": ("PROMPT", "SELECTED", "UNSELECTED"),
                             "CHOOSE": ("CURSOR", "HEADER", "ITEM", "SELECTED"),
                             "SPIN": ("SPINNER", "TITLE")}.items()
    for role in roles for color in ("FOREGROUND", "BACKGROUND")}

# Fields shared by the installed modern palette and gum_env.lua.tpl. This is
# a consistency check of generated data, not a template interpreter.
THEME_EXPORTS = {"FOREGROUND": "foreground", "BACKGROUND": "background",
                 "BORDER_FOREGROUND": "accent", "BORDER_BACKGROUND": "background"}
for _component, _roles in {"CONFIRM": ("PROMPT", "SELECTED", "UNSELECTED"),
                           "CHOOSE": ("CURSOR", "HEADER", "ITEM", "SELECTED"),
                           "SPIN": ("SPINNER", "TITLE")}.items():
    for _role in _roles:
        THEME_EXPORTS[f"GUM_{_component}_{_role}_FOREGROUND"] = (
            "selection_foreground" if _role == "SELECTED" else "accent" if _role in
            ("PROMPT", "CURSOR", "SPINNER") else "foreground")
        THEME_EXPORTS[f"GUM_{_component}_{_role}_BACKGROUND"] = (
            "selection_background" if _role == "SELECTED" else "background")


def theme_colors(raw):
    """Read only stock color exports, never source/execute the generated Lua."""
    values = {}
    for line in raw.splitlines():
        match = re.fullmatch(r'hl\.env\("([A-Z_]+)", "(#[0-9a-fA-F]{6}|[0-9]{1,3})"\)', line.strip())
        if match and match[1] in THEME_KEYS:
            if match[1] in values:
                raise ValueError("exportación de color Gum duplicada")
            if match[2].isdigit() and int(match[2]) > 255:
                raise ValueError("color Gum fuera del rango ANSI")
            values[match[1]] = match[2]
        elif any('"' + key + '"' in line for key in THEME_KEYS) and not line.lstrip().startswith("--"):
            raise ValueError("exportación de color Gum no reconocida")
    return values


def current_theme():
    directory = os.environ.get("XDG_STATE_HOME")
    if not directory and os.environ.get("HOME"):
        directory = str(Path(os.environ["HOME"]) / ".local/state")
    if not directory:
        return {}
    state = Path(directory)
    source = state / "omarchy/current/theme/gum_env.lua"
    return theme_colors(source.read_text(encoding="utf-8")) if source.is_file() else {}


def theme_directory():
    state = os.environ.get("XDG_STATE_HOME")
    if not state and os.environ.get("HOME"):
        state = str(Path(os.environ["HOME"]) / ".local/state")
    return Path(state) / "omarchy/current/theme" if state else None


def theme_snapshot(directory):
    """A complete generation, read as data, including overrides in generated files."""
    names = ("gum_env.lua", "alacritty.toml", "colors.toml")
    before = [directory.stat(), *((directory / name).stat() for name in names)]
    raw = [(directory / name).read_text(encoding="utf-8") for name in names]
    after = [directory.stat(), *((directory / name).stat() for name in names)]
    stamp = lambda stats: [(s.st_dev, s.st_ino, s.st_mtime_ns, s.st_size) for s in stats]
    if stamp(before) != stamp(after):
        raise ValueError("paleta cambiando durante la lectura")
    colors = theme_colors(raw[0])
    terminal = tomllib.loads(raw[1])["colors"]
    palette = tomllib.loads(raw[2])
    palette.setdefault("selection_background", palette.get("selection"))
    palette.setdefault("selection_foreground", palette.get("bright_foreground"))
    if set(colors) != THEME_KEYS:
        raise ValueError("paleta Gum incompleta")
    green = terminal["normal"]["green"]
    common = tuple((colors[key], palette[value]) for key, value in THEME_EXPORTS.items()) + (
              (terminal["primary"]["foreground"], palette["foreground"]),
              (terminal["primary"]["background"], palette["background"]),
              (green, palette["green"]))
    if any(not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value)
           for pair in common for value in pair):
        raise ValueError("tipo/valor de color no compatible")
    if any(left.lower() != right.lower() for left, right in common):
        raise ValueError("colores de generaciones distintas o override no compatible")
    # Numeric/legacy exports cannot promise this true-color surface contract.
    if any(not re.fullmatch(r"#[0-9a-fA-F]{6}", value) for value in (*colors.values(), green)):
        raise ValueError("paleta en vivo requiere colores hexadecimales")
    return colors, green, (stamp(after), raw)


class ThemeWatch:
    """One inotify FD; watch ancestors as well as the replaceable theme directory."""
    def __init__(self, directory):
        self.directory = directory
        self.libc = ctypes.CDLL(None, use_errno=True)
        self.libc.inotify_init1.argtypes = [ctypes.c_int]
        self.libc.inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
        self.fd = self.libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
        if self.fd < 0:
            raise OSError(ctypes.get_errno(), "inotify no disponible")
        self.watches = {}
        self.pending = True
        self.deadline = time.monotonic() + .12
        self.last = None
        self.probe = None
        self.problem = None
        self.rearm()

    def rearm(self):
        # The surviving parent reports delete/move/create of theme and current.
        # Ancestor watches also cover a source that starts temporarily absent.
        desired = {self.directory, *self.directory.parents}
        desired.discard(Path("/"))
        active = set()
        for path in desired:
            if path.is_dir():
                wd = self.libc.inotify_add_watch(self.fd, os.fsencode(path),
                    0x00000002 | 0x00000008 | 0x00000040 | 0x00000080 |
                    0x00000100 | 0x00000200 | 0x00000400 | 0x00000800)
                if wd >= 0:
                    self.watches[wd] = path
                    active.add(wd)
        for wd in set(self.watches) - active:
            self.libc.inotify_rm_watch(self.fd, wd)
            self.watches.pop(wd, None)

    def ready(self, timeout):
        delay = max(0, self.deadline - time.monotonic()) if self.pending else timeout
        readable = select.select([self.fd], [], [], min(timeout, delay))[0]
        if readable:
            data = os.read(self.fd, 65536)
            changed = False
            offset = 0
            while offset < len(data):
                wd, mask, _, length = struct.unpack_from("iIII", data, offset)
                name = os.fsdecode(data[offset+16:offset+16+length].split(b"\0", 1)[0])
                path = self.watches.get(wd)
                offset += 16 + length
                if mask & 0x8000:  # IN_IGNORED: stale inode; not a permanent watch.
                    self.watches.pop(wd, None)
                if mask & 0x4000 or (path and (not name or path / name in
                        {self.directory, *self.directory.parents,
                         self.directory / "gum_env.lua", self.directory / "alacritty.toml",
                         self.directory / "colors.toml"})):
                    changed = True
            if changed:
                self.rearm()
                self.pending, self.probe = True, None
                self.deadline = time.monotonic() + .12
        if not self.pending or time.monotonic() < self.deadline:
            return None
        try:
            result = theme_snapshot(self.directory)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            # No timer loop on a missing/invalid file: next filesystem event retries.
            self.problem = str(exc)
            self.pending, self.probe = False, None
            return None
        if self.probe != result[2]:
            self.probe = result[2]
            self.deadline = time.monotonic() + .08
            return None
        self.pending, self.problem = False, None
        if result[2] == self.last:
            return None
        self.last = result[2]
        return result[:2]

    def close(self):
        os.close(self.fd)


# These 256-color slots belong only to the terminal running this prototype.
# OSC 4 recolors existing indexed cells, even those owned by a running Gum/Fzf.
# No child restart, network listener, fake input or model transition is needed.
COLOR_SLOTS = {key: index for index, key in enumerate(sorted(THEME_KEYS), 16)}
COLOR_SLOTS.update({"pink": 38, "muted-pink": 39, "logo": 40, "surface": 41,
                    "text": 42, "help": 43, "loose-pink": 44, "loose-muted": 45})


def indexed(key, background=False):
    return f"\033[{48 if background else 38};5;{COLOR_SLOTS[key]}m"


def palette_slots(colors, green=None):
    background = colors.get("BACKGROUND", "#101315")
    foreground = colors.get("FOREGROUND", "#eeeeee")
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", background + ""):
        background = "#101315"
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", foreground + ""):
        foreground = "#eeeeee"
    # Explicit cell backgrounds are opaque with stock Alacritty settings.
    # A distinct shade also avoids the terminal's default-background opacity.
    surface = mix_color(background, foreground, .02)
    if surface == background:
        surface = mix_color(background, foreground, .05)
    pink, muted = identity_colors(surface)
    fallback = {key: foreground if key.endswith("FOREGROUND") else surface for key in THEME_KEYS}
    fallback["GUM_CONFIRM_SELECTED_BACKGROUND"] = mix_color(surface, foreground, .25)
    fallback.update(colors)
    slots = {COLOR_SLOTS[k]: v for k, v in fallback.items() if k in COLOR_SLOTS}
    for k in colors:
        if k.endswith("BACKGROUND") or k in ("BACKGROUND", "BORDER_BACKGROUND"):
            # Preserve selected-button contrast from the theme; neutral surfaces
            # get the opaque shade. Do not recolor every control Heartchy pink.
            if k != "GUM_CONFIRM_SELECTED_BACKGROUND":
                slots[COLOR_SLOTS[k]] = surface
    slots.update({COLOR_SLOTS["pink"]: pink, COLOR_SLOTS["muted-pink"]: muted,
                  COLOR_SLOTS["logo"]: green or colors.get("GUM_CHOOSE_CURSOR_FOREGROUND", foreground),
                  COLOR_SLOTS["surface"]: surface, COLOR_SLOTS["text"]: foreground,
                  COLOR_SLOTS["help"]: mix_color(foreground, surface, .15),
                  COLOR_SLOTS["loose-pink"]: PINK,
                  COLOR_SLOTS["loose-muted"]: mix_color(PINK, "#888888", .42)})
    return slots


def palette_sequence(slots):
    if any(not re.fullmatch(r"#[0-9a-fA-F]{6}", value) for value in slots.values()):
        raise ValueError("no se puede publicar una paleta terminal incompleta")
    # Terminal parsers bound OSC parameter counts; one pair per sequence works
    # even when the entire private allocation exceeds that bound.
    return ("\033[?2026h" + "".join(f"\033]4;{index};{value}\033\\" for index, value in sorted(slots.items())) +
            "\033[?2026l").encode()


def save_terminal_palette(indices):
    """Query only allocated slots; do not erase an invoker's dynamic colors."""
    original = termios.tcgetattr(0)
    attributes = original[:]; attributes[3] &= ~(termios.ECHO | termios.ICANON)
    termios.tcsetattr(0, termios.TCSANOW, attributes)
    saved, pending, keys = {}, b"", b""
    pattern = rb"\x1b]4;([0-9]+);(rgb:[0-9a-fA-F]{1,4}/[0-9a-fA-F]{1,4}/[0-9a-fA-F]{1,4})(?:\x07|\x1b\\)"
    try:
        os.write(1, "".join(f"\033]4;{i};?\033\\" for i in sorted(indices)).encode())
        deadline = time.monotonic() + .5
        while set(saved) != set(indices) and time.monotonic() < deadline:
            if not select.select([0], [], [], .025)[0]:
                continue
            pending += os.read(0, 8192)
            while pending:
                match = re.match(pattern, pending)
                if match:
                    index = int(match[1])
                    if index in indices:
                        saved[index] = match[2].decode("ascii")
                    pending = pending[match.end():]
                elif pending == b"\x1b" or (pending.startswith(b"\x1b]") and
                        len(pending) < 512 and not re.search(rb"\x07|\x1b\\", pending)):
                    break
                else:
                    keys += pending[:1]; pending = pending[1:]
        if set(saved) != set(indices):
            raise ValueError("terminal no respondió a OSC 4; no se cambió su paleta (usar --window con Alacritty)")
        return saved, keys + pending
    finally:
        termios.tcsetattr(0, termios.TCSANOW, original)


def preview_theme(name, themes=THEMES):
    """Render only installed color templates as data; never activate a theme."""
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
        raise ValueError("nombre de theme inválido")
    source = themes / name / "colors.toml"
    if not source.resolve().is_relative_to(themes.resolve()):
        raise ValueError("theme fuera del directorio instalado")
    palette = tomllib.loads(source.read_text(encoding="utf-8"))
    # These aliases are the modern-palette contract of omarchy-theme-color.
    # Legacy palettes/derived shades are intentionally not a second theme engine.
    palette.setdefault("selection_background", palette.get("selection"))
    palette.setdefault("selection_foreground", palette.get("bright_foreground"))
    def render(path):
        def replace(match):
            value = palette.get(match[1])
            if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
                raise ValueError("preview requiere color hexadecimal explícito: " + match[1])
            return value
        raw = path.read_text(encoding="utf-8")
        result = re.sub(r"\{\{ ([a-z_]+) \}\}", replace, raw)
        if "{{" in result:
            raise ValueError("template de preview no soportado")
        return result
    templates = themes.parent / "default/themed"
    colors = theme_colors(render(templates / "gum_env.lua.tpl"))
    terminal = tomllib.loads(render(templates / "alacritty.toml.tpl"))
    overrides = []
    def flatten(value, prefix):
        if isinstance(value, dict):
            for key, child in sorted(value.items()):
                if not re.fullmatch(r"[a-z_]+", key):
                    raise ValueError("clave de color Alacritty no soportada")
                flatten(child, prefix + "." + key)
        elif isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            overrides.append(prefix + "=" + json.dumps(value))
        else:
            raise ValueError("valor de color Alacritty no soportado")
    if set(terminal) != {"colors"} or not colors.get("BACKGROUND"):
        raise ValueError("preview sólo permite colores, no configuración de terminal")
    flatten(terminal["colors"], "colors")
    return colors, overrides


def mix_color(start, end, amount):
    rgb = [round(int(start[i:i+2], 16) * (1 - amount) + int(end[i:i+2], 16) * amount)
           for i in (1, 3, 5)]
    return "#" + "".join(f"{x:02x}" for x in rgb)


def contrast(a, b):
    def luminance(color):
        rgb = [int(color[i:i+2], 16) / 255 for i in (1, 3, 5)]
        linear = [x / 12.92 if x <= .04045 else ((x + .055) / 1.055) ** 2.4 for x in rgb]
        return sum(x * y for x, y in zip(linear, (.2126, .7152, .0722)))
    left, right = sorted((luminance(a), luminance(b)))
    return (right + .05) / (left + .05)


def identity_colors(background):
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", background):
        background = "#101315"  # Only the identity shade; native Gum defaults remain.
    active = PINK
    if contrast(active, background) < 4.5:
        endpoint = max(("#000000", "#ffffff"), key=lambda c: contrast(c, background))
        threshold = min(6, contrast(endpoint, background))
        active = next(mix_color(PINK, endpoint, n / 100) for n in range(101)
                      if contrast(mix_color(PINK, endpoint, n / 100), background) >= threshold)
    muted = active
    for n in range(1, 41):
        shade = mix_color(active, background, n / 100)
        if contrast(shade, background) >= 4.5:
            muted = shade
    return active, muted


def color_escape(color):
    return "\033[38;2;" + ";".join(str(int(color[i:i+2], 16)) for i in (1, 3, 5)) + "m"


def version_key(value):
    if not isinstance(value, str) or not re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", value):
        raise ValueError("versión ficticia inválida")
    return tuple(map(int, value.split(".")))


def label(value, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or not value.isprintable():
        raise ValueError("texto inválido en el catálogo")
    return value


@dataclass(frozen=True)
class Release:
    name: str
    version: str
    kind: str
    date: str
    summary: str = ""
    description: str = ""
    changes: tuple = ()
    apps: tuple = ()
    components: tuple = ()
    fixes: tuple = ()
    notes: tuple = ()

    @property
    def height(self):
        return 6 if self.kind == "major" else 4


def parse_catalog(raw):
    def unique(pairs):
        result = {}
        for k, v in pairs:
            if k in result:
                raise ValueError("clave JSON duplicada")
            result[k] = v
        return result
    data = json.loads(raw, object_pairs_hook=unique)
    if not isinstance(data, dict) or set(data) != {"schema_version", "fictional", "installed", "releases"}:
        raise ValueError("estructura de catálogo inválida")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1 or data["fictional"] is not True:
        raise ValueError("se requieren datos ficticios schema 1")
    if not isinstance(data["releases"], list) or not 2 <= len(data["releases"]) <= 30:
        raise ValueError("se requiere una lista acotada de versiones")
    releases = []
    for item in data["releases"]:
        if not isinstance(item, dict) or item.get("kind") not in ("major", "minor"):
            raise ValueError("tipo de tarjeta inválido")
        fields = {"name", "version", "kind", "date", "report"} | ({"summary"} if item["kind"] == "major" else set())
        if set(item) != fields:
            raise ValueError("campos de tarjeta inválidos; sólo hitos llevan resumen")
        key = version_key(item["version"])
        if (key[2] == 0) != (item["kind"] == "major"):
            raise ValueError("hito y mejora no corresponden a la versión")
        day = date.fromisoformat(item["date"])
        if day.isoformat() != item["date"]:
            raise ValueError("fecha no canónica")
        report = item["report"]
        groups = ("changes", "apps", "components", "fixes", "notes")
        if not isinstance(report, dict) or set(report) != {"description", *groups}:
            raise ValueError("reporte ficticio incompleto")
        description = label(report["description"], 240)
        for group in groups:
            if not isinstance(report[group], list) or len(report[group]) > 4:
                raise ValueError("lista de reporte inválida")
            for value in report[group]:
                label(value, 120)
        releases.append(Release(label(item["name"], 64), item["version"], item["kind"], item["date"],
                                label(item["summary"], 240) if item["kind"] == "major" else "",
                                description, *(tuple(report[g]) for g in groups)))
    keys = [version_key(r.version) for r in releases]
    if len(set(keys)) != len(keys) or keys != sorted(keys, reverse=True):
        raise ValueError("versiones duplicadas o fuera de orden descendente")
    if [r.date for r in releases] != sorted((r.date for r in releases), reverse=True):
        raise ValueError("fechas fuera de orden descendente")
    if {r.kind for r in releases} != {"major", "minor"}:
        raise ValueError("faltan tarjetas grandes o pequeñas")
    if not isinstance(data["installed"], str) or sum(r.version == data["installed"] for r in releases) != 1:
        raise ValueError("debe existir exactamente una versión ficticia instalada")
    return tuple(releases), data["installed"]


class Model:
    """All decisions are pure in-memory events; tick accepts an explicit clock."""
    def __init__(self, releases, installed):
        self.releases, self.installed = releases, installed
        self.screen, self.selector, self.selected = "selector", 0, 0
        self.button, self.progress, self.started = 1, 0.0, 0.0
        self.closed, self.no_change = False, False
        self.query = ""

    @property
    def current(self):
        return self.releases[self.selected]

    @property
    def action(self):
        if self.current.version == self.installed:
            return "Sin cambios: ya está instalada"
        if not self.installed:
            return "Instalar Heartchy " + self.current.version
        if version_key(self.current.version) > version_key(self.installed):
            return "Actualizar de " + self.installed + " a " + self.current.version
        return "Cambiar a " + self.current.version + " · Versión anterior a " + self.installed

    def event(self, key, now=0.0):
        if key == "quit":
            self.closed = True
        elif key == "back":
            if self.screen == "selector":
                self.closed = True
            else:
                self.screen = "selector" if self.screen in ("releases", "omarchy") else "releases"
        elif key in ("next", "prev", "first", "last"):
            step = 1 if key == "next" else -1
            if self.screen == "selector":
                self.selector = (self.selector + step) % 2
            elif self.screen == "releases":
                self.selected = (0 if key == "first" else len(self.releases) - 1 if key == "last"
                                 else (self.selected + step) % len(self.releases))
            elif self.screen == "confirm":
                self.button = 1 - self.button
        elif key == "enter":
            if self.screen == "selector":
                self.screen = "releases" if self.selector == 1 else "omarchy"
            elif self.screen == "omarchy":
                self.screen = "selector"
            elif self.screen == "releases":
                self.screen = "report"
            elif self.screen == "report":
                self.screen, self.button = "confirm", 1
            elif self.screen == "confirm":
                if self.button == 1:
                    self.screen = "releases"
                elif self.current.version == self.installed:
                    self.screen, self.no_change = "result", True
                else:
                    self.screen, self.started, self.progress, self.no_change = "progress", now, 0.0, False
            elif self.screen == "result":
                self.screen = "releases"

    def tick(self, now):
        if self.screen == "progress":
            self.progress = min(1.0, max(0.0, (now - self.started) / SIMULATION_SECONDS))
            if self.progress == 1.0:
                self.installed, self.screen = self.current.version, "result"

def logo(word):
    if word not in ("OMARCHY", "HEARTCHY"):
        raise ValueError("logo desconocido")
    return (ASSETS / (word.lower() + ".txt")).read_text(encoding="utf-8").splitlines()


def heading(word, columns, rows):
    art = logo(word)
    if max(map(len, art)) > columns or rows < 26:
        return word + " · cabecera compacta"
    return "\n".join(art)


def banner(word, columns, rows, pink=PINK):
    # Both wordmarks share a ten-row canvas; widgets cannot move the logo.
    art = heading(word, columns, rows)
    if "cabecera compacta" not in art:
        art += "\n" * (10 - len(art.splitlines()))
    color = color_escape(pink) if word == "HEARTCHY" else "\033[32m"
    return color + art + "\033[0m\n\n" + SIMULATION


def window_command(theme=None, animation=True, animation_preview=False):
    # TUI.float is the installed stock floating-terminal contract (875×600).
    # Do not invoke Omarchy's presentation wrapper: it would print another logo.
    command = ["/usr/bin/alacritty", "--class", "TUI.float", "--title", "Heartchy · SIMULACIÓN"]
    if theme:
        _, overrides = preview_theme(theme)
        for value in overrides:
            command += ["--option", value]
    command += ["-e", str(Path(__file__).resolve().parents[1] / "bin/heartchy-updates-mockup")]
    if theme:
        command += ["--preview-theme", theme]
    if not animation:
        command += ["--no-animation"]
    if animation_preview:
        command += ["--animation-preview"]
    return command


REPLIES = (rb"\x1b\[\?[0-9]+u", rb"\x1b\[\?(?:2026|2027|2004);[0-4]\$y",
           rb"\x1b\[[0-9]+;[0-9]+R",
           rb"\x1b\]4;[0-9]+;rgb:[0-9a-fA-F]{1,4}/[0-9a-fA-F]{1,4}/[0-9a-fA-F]{1,4}(?:\x07|\x1b\\)",
           rb"\x1b\](?:10|11);rgb:[0-9a-fA-F]{1,4}/[0-9a-fA-F]{1,4}/[0-9a-fA-F]{1,4}(?:\x07|\x1b\\)")


def selector_keys(pending, data, escape_expired=False, extra_keys=None):
    """Bounded selector keys/protocol replies; never echo input into the UI."""
    pending += data
    events = []
    keys = {b"\x1b[A": "prev", b"\x1b[D": "prev", b"\x1b[B": "next", b"\x1b[C": "next",
            b"\x1bOA": "prev", b"\x1bOB": "next", b"\r": "enter", b"\n": "enter",
            b"\x03": "quit", b"\x04": "quit", b"j": "next", b"k": "prev", b"\t": "next"}
    keys.update(extra_keys or {})
    while pending:
        match = next((m for pattern in REPLIES if (m := re.match(pattern, pending))), None)
        if match:
            pending = pending[match.end():]
            continue
        unknown = re.match(rb"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\)|[PX^_][\s\S]*?\x1b\\)", pending)
        if unknown and not any(pending.startswith(k) for k in keys):
            pending = pending[unknown.end():]
            continue
        key = next((k for k in keys if pending.startswith(k)), None)
        if key:
            events.append(keys[key]); pending = pending[len(key):]
        elif pending == b"\x1b" and escape_expired:
            events.append("back"); pending = b""
        elif len(pending) < 80 and (any(k.startswith(pending) for k in keys)
                or re.fullmatch(rb"\x1b(?:\[(?:\??[0-9;]*\$?)?)?", pending)):
            break
        elif pending[:2] in (b"\x1b]", b"\x1bP", b"\x1bX", b"\x1b^", b"\x1b_"):
            # Control strings can contain printable j/k/Enter; none are keys.
            # Retain discard mode after overflow, until its terminator arrives.
            pending = pending if len(pending) < 512 else pending[:2] + b"\0"
            break
        else:
            # Unknown escape/control input is ignored, never a menu selection.
            pending = pending[1:]
    return events, pending


def wipe_rows(old, new, fraction):
    """Reconstruct half-block contours across a soft, eased sweep; no randomness."""
    before, after = logo(old), logo(new)
    width = max(max(map(len, before)), max(map(len, after)))
    before += [""] * (10 - len(before)); after += [""] * (10 - len(after))
    fraction = max(0, min(1, fraction))
    eased = fraction * fraction * (3 - 2 * fraction)
    band = 8
    front = eased * (width + band * 2) - band
    masks = {" ": 0, "▀": 1, "▄": 2, "█": 3}
    glyphs = " ▀▄█"
    rows = []
    for row, (a, b) in enumerate(zip(before, after)):
        cells = []
        for col, (old_char, new_char) in enumerate(zip(a.ljust(width), b.ljust(width))):
            weight = (0 if fraction == 0 else 1 if fraction == 1 else
                      max(0, min(1, (front - col + band + (row - 4.5) * .18) / (2 * band))))
            old_mask, new_mask = masks[old_char], masks[new_char]
            mask = 0
            for half, bit in enumerate((1, 2)):
                # Two continuous fronts reconstruct upper/lower halves. A
                # scattered dissolve looked noisy; shared strokes stay intact.
                threshold = .30 + half * .35 + row * .012
                mask |= (new_mask if weight >= threshold else old_mask) & bit
            cells.append((glyphs[mask], weight))
        rows.append(cells)
    return rows


def progress_keys(pending, data):
    """Consume known Gum/Fzf terminal replies, not arbitrary ANSI or stderr."""
    pending += data
    while pending:
        match = next((m for pattern in REPLIES if (m := re.match(pattern, pending))), None)
        if match:
            pending = pending[match.end():]
            continue
        if len(pending) < 80 and (re.fullmatch(rb"\x1b(?:\[(?:\??[0-9;]*\$?)?)?", pending)
                                 or re.fullmatch(rb"\x1b\](?:1[01]?(?:;(?:r(?:g(?:b(?::[0-9a-fA-F/]*)?)?)?)?)?)?\x1b?", pending)):
            return False, pending
        if pending[0] in (3, 27):
            return True, b""
        pending = pending[1:]
    return False, b""


class NativeUI:
    """Use the same terminal widgets as stock menus; no Omarchy commands."""
    def __init__(self, model, colors=None, animation=True, green=None):
        self.model = model
        self.env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C.UTF-8",
                    "TERM": os.environ.get("TERM", "xterm-256color"), "COLORTERM": "truecolor", "CLICOLOR_FORCE": "1",
                    "HOME": "/nonexistent", "XDG_CONFIG_HOME": "/nonexistent", "XDG_CACHE_HOME": "/nonexistent"}
        self.env.update(current_theme() if colors is None else colors)
        self.pink, self.muted_pink = identity_colors(self.env.get("BACKGROUND", ""))
        self.animation = animation
        self.child = None
        self.live_directory = theme_directory() if colors is None else None
        self.slots = palette_slots({k: v for k, v in self.env.items() if k in THEME_KEYS}, green)
        self.revision = 0
        self.theme_error = None
        self.theme_stop = threading.Event()
        self.theme_thread = None
        self.theme_watch = None
        self.indexed_colors = False
        self.saved_slots = {}
        self.startup_input = b""
        self._logo_tools = None
        self.middleout = {}

    def child_env(self):
        env = {**self.env}
        if self.indexed_colors:
            env.update({key: str(COLOR_SLOTS[key]) for key in THEME_KEYS})
        # Loose controls inherit the terminal background. Panels explicitly opt
        # into a surface; a theme background is not a capsule around every label.
        for key in THEME_KEYS:
            if key.endswith("BACKGROUND"):
                env[key] = ""
        for key in THEME_KEYS:
            if key.startswith("GUM_") and key.endswith("FOREGROUND"):
                env[key] = ""  # terminal foreground outside panels
        if self.model.screen not in ("selector", "omarchy"):
            pink = str(COLOR_SLOTS["loose-pink"]) if self.indexed_colors else PINK
            for key in ("GUM_CONFIRM_PROMPT_FOREGROUND", "GUM_CONFIRM_SELECTED_FOREGROUND",
                        "GUM_CHOOSE_CURSOR_FOREGROUND", "GUM_CHOOSE_SELECTED_FOREGROUND",
                        "GUM_CHOOSE_HEADER_FOREGROUND", "GUM_SPIN_SPINNER_FOREGROUND"):
                env[key] = pink
            env["GUM_CONFIRM_SELECTED_BACKGROUND"] = str(COLOR_SLOTS["pink"]) if self.indexed_colors else self.pink
            env["GUM_CONFIRM_SELECTED_FOREGROUND"] = str(COLOR_SLOTS["surface"]) if self.indexed_colors else self.env.get("BACKGROUND", "#101315")
        return env

    def start_theme(self):
        self.saved_slots, self.startup_input = save_terminal_palette(COLOR_SLOTS.values())
        self.indexed_colors = True
        if self.live_directory is not None:
            try:
                colors, green, _ = theme_snapshot(self.live_directory)
                self.env.update(colors)
                self.slots = palette_slots(colors, green)
            except (OSError, ValueError, KeyError, TypeError):
                pass  # Last usable startup palette remains until a complete event.
            self.theme_watch = ThemeWatch(self.live_directory)
        os.write(1, palette_sequence(self.slots))
        self.pink, self.muted_pink = (self.slots[COLOR_SLOTS[role]] for role in ("pink", "muted-pink"))
        if self.theme_watch:
            def changes():
                try:
                    while not self.theme_stop.is_set():
                        palette = self.theme_watch.ready(.2)
                        if palette is not None:
                            colors, green = palette
                            slots = palette_slots(colors, green)
                            if slots != self.slots:
                                self.env = {**self.env, **colors}
                                self.pink, self.muted_pink = identity_colors(slots[COLOR_SLOTS["surface"]])
                                self.slots = slots
                                # One bounded write; terminal marks existing cells
                                # damaged. Child input/state and work never change.
                                os.write(1, palette_sequence(slots))
                                self.revision += 1
                except OSError as exc:
                    self.theme_error = str(exc)
            self.theme_thread = threading.Thread(target=changes, name="mockup-theme", daemon=False)
            self.theme_thread.start()

    def stop_theme(self):
        self.theme_stop.set()
        if self.theme_thread:
            self.theme_thread.join(timeout=1)
            if self.theme_thread.is_alive():
                raise RuntimeError("watcher de paleta no terminó")
        if self.theme_watch:
            self.theme_watch.close()
        # Do not reset all ANSI colors, foreground/background or user settings.
        # Restore exactly the small private allocation observed at entry.
        if self.indexed_colors:
            # Remove indexed cells before restoring their colors. Do both in one
            # synchronized frame, after the watcher and child have stopped.
            restore = "".join(f"\033]4;{i};{v}\033\\" for i,v in sorted(self.saved_slots.items()))
            os.write(1, ("\033[?2026h\033[0m\033[2J\033[H" + restore + "\033[?2026l").encode())
        self.indexed_colors = False

    def surface(self, text, role="text"):
        if not self.indexed_colors:
            return text
        # Text outside panels uses the terminal's own foreground, so a light
        # preview palette does not paint dark text onto a transparent dark pane.
        color = indexed({"pink": "loose-pink", "muted-pink": "loose-muted"}.get(role, role)) if role in (
            "pink", "muted-pink", "logo") else "\033[39m"
        return color + "\033[49m" + text + "\033[0m"

    def live_banner(self, name, columns, rows):
        if not self.indexed_colors:
            return banner(name, columns, rows, self.pink)
        art = heading(name, columns, rows)
        if "cabecera compacta" not in art:
            width = max(map(len, logo("HEARTCHY")))
            art = "\n".join(line.ljust(width) for line in art.splitlines())
        return "\n".join(self.surface(line, "pink" if name == "HEARTCHY" else "logo")
                         for line in art.splitlines()) + "\n\n" + self.surface(SIMULATION, "help")

    def tool(self, arguments, payload=None, capture=False):
        # No shell, previews, execute bindings, history, listeners or user defaults.
        self.child = subprocess.Popen(arguments, stdin=subprocess.PIPE if payload is not None else None,
                                      text=True, env=self.child_env(), stdout=subprocess.PIPE if capture else None)
        try:
            output, _ = self.child.communicate(payload)
            return subprocess.CompletedProcess(arguments, self.child.returncode, output)
        finally:
            if self.child.poll() is None:
                self.child.terminate()
                try:
                    self.child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.child.kill()
                    self.child.wait(timeout=3)
            self.child = None

    def spin(self, arguments):
        # Gum 2 spin disables its input reader but still queries the Kitty
        # protocol. Consume that response with echo off; it is not a key.
        original = termios.tcgetattr(0)
        attributes = original[:]
        attributes[3] &= ~(termios.ECHO | termios.ICANON)
        termios.tcsetattr(0, termios.TCSANOW, attributes)
        # The parent owns input during progress; no child can consume Escape
        # or a protocol reply before that bounded reader handles it.
        # Gum 2 renders to stderr, but starts a separate PTY/session for its
        # command when stdout is a TTY. A pipe (sleep has no output) keeps that
        # literal child in our group, so cancellation also terminates it.
        with open("/dev/null", "rb") as no_input:
            self.child = subprocess.Popen(arguments, stdin=no_input, stdout=subprocess.PIPE,
                                          env=self.child_env(), start_new_session=True)
        pending, since, cancelled = b"", time.monotonic(), False
        def stop():
            os.killpg(self.child.pid, signal.SIGTERM)
            try:
                self.child.wait(timeout=.3)
            except subprocess.TimeoutExpired:
                # Gum can still be starting sleep when TERM arrives. End only
                # this simulation group, then undo its known terminal modes.
                os.killpg(self.child.pid, signal.SIGKILL)
                self.child.wait(timeout=3)
                print("\033[>4;0m\033[=0;1u\033[?2004l\033[?2026l\033[?2027l\033[0m\033[?25h", end="", flush=True)
        try:
            while self.child.poll() is None:
                if select.select([0], [], [], .04)[0]:
                    cancel, pending = progress_keys(pending, os.read(0, 1024))
                    since = time.monotonic()
                    if cancel:
                        cancelled = True
                        stop()
                        break
                elif pending == b"\x1b" and time.monotonic() - since > .08:
                    cancelled = True
                    stop()
                    break
            code = self.child.wait(timeout=3)
            return subprocess.CompletedProcess(arguments, 130 if cancelled else code)
        finally:
            try:
                if self.child.poll() is None:
                    stop()
            finally:
                self.child.stdout.close()
                self.child = None
                termios.tcsetattr(0, termios.TCSANOW, original)

    def clear(self):
        print("\033[2J\033[H\n", end="", flush=True)

    def brand(self, name="HEARTCHY"):
        self.clear()
        size = shutil.get_terminal_size()
        # Fzf reserves one column for its header. Give Gum the same margin.
        print("\n".join(" " + line for line in self.live_banner(name, size.columns - 1, size.lines).split("\n")) + "\n", flush=True)

    def logo_tools(self):
        if self._logo_tools is None:
            import runpy
            self._logo_tools = runpy.run_path(str(Path(__file__).with_name("animation_preview.py")))
        return self._logo_tools

    def prepare_middleout(self):
        # Prepare both directions once, before input. Navigation never spawns
        # an engine or waits for generation; the same tested frames serve the
        # development comparator and the normal selector.
        if self.middleout:
            return
        tools = self.logo_tools()
        engine = tools["NativeFrames"]()
        prepared = {}
        try:
            for before, after in (("OMARCHY", "HEARTCHY"), ("HEARTCHY", "OMARCHY")):
                prepared[after] = tuple(tools["transition_frames"](
                    logo(before), engine.get("middleout", logo(after))))
        except (ValueError, OSError, subprocess.SubprocessError) as exc:
            raise ValueError("Middleout no disponible: " + str(exc) +
                             ". Usa --no-animation para la alternativa instantánea; no se instala nada.") from exc
        self.middleout = prepared

    def paint_logo(self, rows, name):
        color = (indexed("loose-pink" if name == "HEARTCHY" else "logo") if self.indexed_colors else
                 color_escape(self.pink) if name == "HEARTCHY" else "\033[32m")
        print(self.logo_tools()["frame_output"](rows, color), end="", flush=True)

    def selector(self):
        if self.animation:
            self.prepare_middleout()
        # Gum choose has global styles and no focus callback. This adapter
        # handles only two choices; all rendered rows still use Gum style.
        styled = {}
        for selected in (0, 1):
            for item, name in enumerate(("Omarchy", "Heartchy")):
                focus = item == selected
                color = (self.pink if focus else self.muted_pink) if item else self.env.get(
                    "GUM_CHOOSE_CURSOR_FOREGROUND" if focus else "FOREGROUND", "7")
                if self.indexed_colors:
                    role = ("loose-pink" if focus else "loose-muted") if item else (
                        "GUM_CHOOSE_CURSOR_FOREGROUND" if focus else "text")
                    color = str(COLOR_SLOTS[role])
                if item == 0 and not focus:
                    color = ""  # unselected stock text inherits the transparent terminal
                args = ["/usr/bin/gum", "style", "--foreground", color]
                args += ["--background", ""]
                if focus:
                    args += ["--bold"]
                result = self.tool(args + [("> " if focus else "  ") + name], capture=True)
                if result.returncode:
                    raise ValueError("Gum no pudo dibujar el selector")
                styled[selected, item] = result.stdout.rstrip("\n")
        original = termios.tcgetattr(0)
        attributes = original[:]; attributes[3] &= ~(termios.ECHO | termios.ICANON)
        termios.tcsetattr(0, termios.TCSANOW, attributes)
        pending, queued, since = b"", [], time.monotonic()
        if self.startup_input:
            queued, pending = selector_keys(pending, self.startup_input)
            self.startup_input = b""
        size = shutil.get_terminal_size()
        self.brand(("OMARCHY", "HEARTCHY")[self.model.selector])
        def draw_choices():
            top = len(banner("OMARCHY", size.columns - 1, size.lines, self.pink).split("\n")) + 3
            lines = [self.surface("Updates / Omarchy · Heartchy"), styled[self.model.selector, 0],
                     styled[self.model.selector, 1], "", self.surface("↑/↓ navegar · Enter abrir · Esc salir", "help")]
            print("".join(f"\033[{top+i};1H\033[2K" + line for i, line in enumerate(lines)) + "\033[?25l", end="", flush=True)
        def poll(timeout):
            nonlocal pending, since
            if select.select([0], [], [], timeout)[0]:
                data = os.read(0, 1024)
                if not data:
                    return ["quit"]
                since = time.monotonic()
                events, pending = selector_keys(pending, data)
                return events
            events, pending = selector_keys(pending, b"", time.monotonic() - since > .08)
            return events
        try:
            draw_choices()
            while self.model.screen == "selector" and not self.model.closed:
                if not queued:
                    queued.extend(poll(.04))
                if not queued:
                    new_size = shutil.get_terminal_size()
                    if new_size != size:
                        size = new_size
                        self.brand(("OMARCHY", "HEARTCHY")[self.model.selector]); draw_choices()
                    continue
                key = queued.pop(0)
                old = self.model.selector
                self.model.event(key)
                if old != self.model.selector:
                    draw_choices()
                    before, after = ("OMARCHY", "HEARTCHY")[old], ("OMARCHY", "HEARTCHY")[self.model.selector]
                    full = all("cabecera compacta" not in heading(n, size.columns - 1, size.lines) for n in (before, after))
                    started = time.monotonic()
                    revision = self.revision
                    frames = self.middleout[after] if self.animation and full and not queued else ()
                    for i, (rows, incoming) in enumerate(frames):
                        new_size = shutil.get_terminal_size()
                        if new_size != size:
                            size = new_size; full = False
                            break
                        self.paint_logo(rows, after if incoming else before)
                        queued.extend(poll(max(0, started + (i + 1) / self.logo_tools()["FPS"] - time.monotonic())))
                        if queued or self.revision != revision:
                            break
                    new_size = shutil.get_terminal_size()
                    if new_size != size:
                        size = new_size; full = False
                    if full:
                        self.paint_logo(self.logo_tools()["static_rows"](logo(after)), after)
                    else:
                        self.brand(after); draw_choices()
        finally:
            termios.tcsetattr(0, termios.TCSANOW, original)
            print("\033[0m\033[?25h", end="", flush=True)

    def paint_wipe(self, before, after, fraction):
        colors = {"OMARCHY": indexed("logo") if self.indexed_colors else "\033[32m",
                  "HEARTCHY": indexed("loose-pink") if self.indexed_colors else color_escape(self.pink)}
        rows = wipe_rows(before, after, fraction)
        output = []
        for i, row in enumerate(rows):
            output.append(f"\033[{i+2};2H")
            output.append("\033[49m")
            previous = None
            for char, weight in row:
                color = (colors[before] if weight == 0 else colors[after] if weight == 1 else
                         color_escape(mix_color(self.muted_pink, self.pink,
                                                weight if after == "HEARTCHY" else 1 - weight)))
                if color != previous:
                    output.append(color); previous = color
                output.append(char)
            output.append("\033[0m")
        print("".join(output), end="", flush=True)

    def listing(self):
        self.clear()
        size = shutil.get_terminal_size()
        if size.columns < 42 or size.lines < 16:
            raise ValueError("terminal demasiado pequeña: se requieren 42 columnas y 16 filas")
        width = size.columns - 2
        header = self.live_banner("HEARTCHY", size.columns - 1, size.lines) + "\n"
        def card(release):
            text = card_text(release, self.model.installed, width)
            if self.indexed_colors:
                text = "\n".join(indexed("surface", True) + line + "\033[49m" for line in text.splitlines())
            return text
        records = "\0".join(r.version + "\x1f" + card(r) for r in self.model.releases) + "\0"
        filter_args = ["/usr/bin/fzf", "--read0", "--print0", "--no-sort", "--delimiter=\\x1f", "--accept-nth=1",
                       "--ansi", "--with-nth=2.."]
        filtered = self.tool(filter_args + ["--filter=" + self.model.query], payload=records, capture=True)
        if filtered.returncode not in (0, 1):
            raise ValueError("Fzf no pudo restaurar la búsqueda")
        identities = filtered.stdout.rstrip("\0").split("\0")
        position = identities.index(self.model.current.version) + 1 if self.model.current.version in identities else 1
        colors = ["fg+:" + self.pink, "hl+:" + self.pink, "bg+:-1", "prompt:" + self.pink]
        for role, key in (("fg", "FOREGROUND"), ("header", "FOREGROUND"), ("footer", "FOREGROUND")):
            if key in self.env:
                colors.append(role + ":" + self.env[key])
        if self.indexed_colors:
            colors = [role + ":" + str(COLOR_SLOTS[key]) for role, key in
                      (("fg+", "pink"), ("hl+", "pink"), ("hl", "pink"), ("prompt", "loose-pink"),
                       ("fg", "text"), ("border", "pink"), ("bg+", "surface"))]
            colors += ["bg:-1", "gutter:-1", "query:-1", "header:-1", "footer:-1", "info:-1",
                       "input-bg:-1", "footer-bg:-1"]
        result = self.tool(filter_args + ["--sync", "--print-query",
                            "--expect=enter,esc,ctrl-q,double-click", "--layout=reverse", "--margin=1,0,0,0", "--gap=1", "--gap-line=",
                            "--no-separator",
                            "--no-scrollbar", "--no-hscroll", "--pointer=", "--cycle", "--wrap=word",
                            "--header-first", "--header", header, "--prompt", "Buscar versión > ",
                            "--query", self.model.query, "--color", ",".join(colors),
                            "--footer", "↑/↓ versión · Enter ver reporte · Esc volver",
                            "--footer-border=none",
                            "--bind", f"load:pos({position})+offset-middle,focus:offset-middle,resize:print(RESIZE)+accept"],
                            payload=records, capture=True)
        if result.returncode == 130:
            self.model.closed = True
        elif result.returncode not in (0, 1):
            raise ValueError("Fzf no pudo abrir el listado")
        else:
            fields = result.stdout.split("\0")
            if fields[-1] != "" or len(fields) < 3:
                raise ValueError("salida Fzf no delimitada")
            query, key, *items = fields[:-1]
            if len(query) > 1024 or (query and not query.isprintable()):
                raise ValueError("búsqueda Fzf inválida")
            self.model.query = query
            resized = key == "" and items[:1] == ["RESIZE"]
            if resized:
                items = items[1:]
            if len(items) > 1 or key not in ("enter", "double-click", "esc", "ctrl-q", "") or (key == "" and not resized):
                raise ValueError("acción Fzf desconocida")
            if not items:
                if key in ("esc", "ctrl-q"):
                    self.model.event("back")
                return
            version = items[0]
            indices = [i for i, r in enumerate(self.model.releases) if r.version == version]
            if len(indices) != 1:
                raise ValueError("Fzf devolvió una versión desconocida")
            self.model.selected = indices[0]
            if key in ("esc", "ctrl-q"):
                self.model.event("back")
            elif not resized:
                self.model.event("enter")

    def panel(self, lines, padding="1 2"):
        color = lambda role: str(COLOR_SLOTS[role]) if self.indexed_colors else self.env.get(
            "BACKGROUND" if role == "surface" else "FOREGROUND", "")
        if self.indexed_colors:
            lines = [("\033[1m" + indexed("pink") + line + "\033[22m" + indexed("text"))
                     if i == 0 or line.startswith(("CAMBIOS PRINCIPALES", "APPS AÑADIDAS", "COMPONENTES", "FIXES / MEJORAS", "ACCIÓN ·"))
                     else line for i, line in enumerate(lines)]
        result = self.tool(["/usr/bin/gum", "style", "--border", "normal", "--padding", padding,
                           "--margin", "0 1", "--width", str(max(30, shutil.get_terminal_size().columns - 2)),
                           "--foreground", color("text"), "--background", color("surface"),
                           "--border-foreground", str(COLOR_SLOTS["pink"]) if self.indexed_colors else self.pink,
                           "--border-background", color("surface"), "--", *lines])
        if result.returncode:
            raise ValueError("Gum no pudo dibujar el panel")

    def report_content(self, width):
        return report_lines(self.model, width)

    def report(self):
        page = 0
        while self.model.screen == "report" and not self.model.closed:
            size = shutil.get_terminal_size()
            lines = self.report_content(max(26, size.columns - 8))
            # Recompute after every action, including resizing while Gum ran.
            capacity = max(1, size.lines - (14 if size.lines < 26 else 23))
            pages = [lines[i:i+capacity] for i in range(0, len(lines), capacity)]
            page = min(page, len(pages) - 1)
            self.brand()
            title = "Reporte de versión · " + self.model.current.version
            if len(pages) > 1:
                title += f" · {page+1}/{len(pages)}"
            self.panel([title, *pages[page]], padding="0 2")
            print("\n " + self.surface("↑/↓ elegir · Enter continuar · Esc volver", "help"), flush=True)
            options = (["Página siguiente"] if page + 1 < len(pages) else ["Revisar confirmación"])
            if page:
                options.append("Página anterior")
            options.append("Volver al listado")
            result = self.tool(["/usr/bin/gum", "choose", "--header", "", "--no-show-help", *options], capture=True)
            choice = result.stdout.strip()
            if result.returncode in (1, 130) or choice == "Volver al listado":
                self.model.event("back")
            elif result.returncode != 0 or choice not in options:
                raise ValueError("Gum devolvió una acción de reporte desconocida")
            elif choice == "Página siguiente":
                page += 1
            elif choice == "Página anterior":
                page -= 1
            else:
                self.model.event("enter")

    def confirm(self):
        self.brand()
        r = self.model.current
        self.panel(["Confirmar selección", "", r.name + "  " + r.version,
                    self.model.action, "", "Sólo cambia la versión ficticia dentro de esta maqueta."])
        print("\n " + self.surface("←/→ elegir · Enter confirmar · Esc volver", "help"), flush=True)
        result = self.tool(["/usr/bin/gum", "confirm", "¿Continuar con la simulación?", "--default=false",
                           "--affirmative", "Aceptar", "--negative", "Cancelar", "--no-show-help"])
        if result.returncode == 130:
            self.model.event("back")
        elif result.returncode in (0, 1):
            self.model.button = 0 if result.returncode == 0 else 1
            self.model.event("enter", time.monotonic())
        else:
            raise ValueError("Gum no pudo confirmar la selección")

    def progress(self):
        self.brand()
        print(self.surface(self.model.current.name + " " + self.model.current.version) + "\n", flush=True)
        if self.indexed_colors:
            print(self.surface("Esc / Ctrl+C interrumpir la simulación", "help") + "\n", flush=True)
        result = self.spin(["/usr/bin/gum", "spin", "--spinner", "line",
                           "--title", "Instalación SIMULADA · Sin descargas ni escrituras",
                           "--spinner.foreground", str(COLOR_SLOTS["loose-pink"]) if self.indexed_colors else self.pink,
                           "--", "/usr/bin/sleep", str(SIMULATION_SECONDS)])
        if result.returncode == 0:
            self.model.tick(self.model.started + SIMULATION_SECONDS)
        elif result.returncode in (1, 130, -signal.SIGTERM):
            self.model.closed = True
        else:
            raise ValueError("la espera simulada falló")

    def result(self):
        self.brand()
        r = self.model.current
        self.panel(["Simulación completada — ningún cambio real", "",
                    r.name + "  " + r.version, "● Versión ficticia instalada: " + self.model.installed,
                    "", "El recorrido terminó. No se descargaron ni aplicaron archivos.",
                    "Puedes explorar otra versión o salir de la maqueta."])
        print("\n " + self.surface("↑/↓ elegir · Enter continuar · Esc salir", "help"), flush=True)
        result = self.tool(["/usr/bin/gum", "choose", "--header", "Resultado simulado",
                           "--selected", "Volver al listado",
                           *(["--no-show-help"] if self.indexed_colors else []),
                           "Volver al listado", "Salir de la maqueta"], capture=True)
        if result.returncode in (1, 130) or result.stdout.strip() == "Salir de la maqueta":
            self.model.closed = True
        elif result.returncode == 0 and result.stdout.strip() == "Volver al listado":
            self.model.event("enter")
        else:
            raise ValueError("Gum devolvió una acción de resultado desconocida")

    def omarchy(self):
        self.brand("OMARCHY")
        self.tool(["/usr/bin/gum", "style", "--border", "normal", "--padding", "1 2",
                   "La ruta Omarchy queda fuera de esta maqueta.", "No se invoca ningún actualizador.",
                   *(["enter submit · Esc volver"] if self.indexed_colors else [])])
        result = self.tool(["/usr/bin/gum", "choose", "--header", "Esc volver",
                           *(["--no-show-help"] if self.indexed_colors else []), "Volver al selector"], capture=True)
        if result.returncode not in (0, 1, 130):
            raise ValueError("Gum no pudo mostrar la ruta de ejemplo")
        self.model.event("back")

    def run(self, animation_preview=False):
        original = termios.tcgetattr(0)
        attributes = original[:]
        attributes[3] &= ~termios.ECHO
        termios.tcsetattr(0, termios.TCSANOW, attributes)
        def interrupted(_signal, _frame):
            raise KeyboardInterrupt
        previous = {sig: signal.signal(sig, interrupted) for sig in (signal.SIGTERM, signal.SIGHUP)}
        try:
            self.start_theme()
            if animation_preview:
                preview = self.logo_tools()
                preview["compare"](self, logo, selector_keys, heading, banner, indexed, color_escape)
            while not self.model.closed:
                if self.theme_error:
                    raise OSError("watcher de paleta: " + self.theme_error)
                getattr(self, self.model.screen if self.model.screen != "releases" else "listing")()
        finally:
            try:
                self.stop_theme()
            finally:
                termios.tcsetattr(0, termios.TCSANOW, original)
                for sig, handler in previous.items():
                    signal.signal(sig, handler)
                print("\033[0m\033[?25h", end="", flush=True)


def report_lines(model, width):
    """A readable report, independent of Gum and never a real installation plan."""
    r = model.current
    status = "● Instalada" if r.version == model.installed else "○ No instalada"
    lines = [r.name + "  " + r.version + "  ·  " + status,
             "Actual simulada: " + (model.installed or "ninguna") + "    →    Elegida: " + r.version, ""]
    lines += textwrap.wrap(r.description or r.summary, width) + [""]
    groups = [("CAMBIOS PRINCIPALES", r.changes), ("COMPONENTES", r.components),
              ("APPS AÑADIDAS", r.apps or ("Ninguna en esta versión ficticia.",)), ("FIXES / MEJORAS", r.fixes)]
    def section(title, items, columns):
        out = [title]
        for item in items:
            out.extend(textwrap.wrap("• " + item, columns, subsequent_indent="  "))
        return out
    if width >= 86:
        half = (width - 4) // 2
        for a, b in zip(groups[::2], groups[1::2]):
            left, right = section(*a, half), section(*b, half)
            lines += [(left[i] if i < len(left) else "").ljust(half) + "    " +
                      (right[i] if i < len(right) else "") for i in range(max(len(left), len(right)))] + [""]
    else:
        for title, items in groups:
            lines += section(title, items, width) + [""]
    lines += textwrap.wrap("NOTAS · " + " ".join(r.notes), width)
    lines += ["", "ACCIÓN · " + model.action]
    return [part for line in lines for part in (textwrap.wrap(line, width) if len(line) > width else [line])]


def card_text(release, installed, width):
    """A multiline Fzf item: only milestone cards have summary rows."""
    if not 36 <= width <= 1000:
        raise ValueError("ancho de tarjeta fuera del rango soportado")
    status = "● Instalada" if release.version == installed else "○ No instalada"
    title = release.name + "  " + release.version
    first_width = width - len(status) - 5
    title_rows = textwrap.wrap(title, first_width)
    rows = ["┌" + "─" * (width - 2) + "┐",
            "│ " + title_rows[0].ljust(first_width) + " " + status + " │"]
    rows.extend("│ " + line.ljust(width - 4) + " │" for line in title_rows[1:])
    if release.kind == "major":
        summary = textwrap.wrap(release.summary, width - 4)
        rows.extend("│ " + line.ljust(width - 4) + " │" for line in summary + [""] * max(0, 2 - len(summary)))
    rows.extend(["│ " + ("Publicada " + release.date).ljust(width - 4) + " │",
                 "└" + "─" * (width - 2) + "┘"])
    return "\n".join(rows)


def main():
    parser = argparse.ArgumentParser(prog="heartchy-updates-mockup",
        description="Mockup Gum/Fzf de Updates. Datos ficticios; sólo terminal y memoria, sin red ni cambios al sistema.")
    parser.add_argument("--window", action="store_true",
                        help="Abrir sólo la maqueta en Alacritty con la clase TUI.float: tamaño y centrado stock Omarchy; sin cambiar configuración.")
    parser.add_argument("--no-animation", action="store_true", help="Cambio instantáneo de logo; omitir Middleout sin invocar ttfx.")
    parser.add_argument("--preview-theme", metavar="NOMBRE", help="Preview de paleta stock instalada sólo en esta maqueta/ventana; no activa el theme del escritorio.")
    parser.add_argument("--animation-preview", action="store_true", help="Comparador sólo de desarrollo: ttfx 0.3.2, barrido y sin animación; no cambia Middleout ni guarda una elección.")
    options = parser.parse_args()
    if options.window:
        if not os.access("/usr/bin/alacritty", os.X_OK):
            parser.error("Alacritty no está disponible; no se instala ni usa fallback")
        try:
            return subprocess.run(window_command(options.preview_theme, not options.no_animation, options.animation_preview), check=False).returncode
        except (ValueError, OSError, tomllib.TOMLDecodeError) as exc:
            parser.error(str(exc))
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        parser.error("se requiere una terminal interactiva; no se ejecutó la simulación")
    missing = [p for p in ("/usr/bin/gum", "/usr/bin/fzf", "/usr/bin/sleep") if not os.access(p, os.X_OK)]
    if missing:
        print("Dependencia no disponible: " + ", ".join(missing) + "; no se instala ni usa fallback.", file=sys.stderr)
        return 1
    try:
        releases, installed = parse_catalog(CATALOG.read_text(encoding="utf-8"))
        colors, green = None, None
        if options.preview_theme:
            colors, overrides = preview_theme(options.preview_theme)
            green = next(json.loads(value.split("=", 1)[1]) for value in overrides
                         if value.startswith("colors.normal.green="))
        NativeUI(Model(releases, installed), colors, not options.no_animation, green).run(options.animation_preview)
    except KeyboardInterrupt:
        return 0
    except (ValueError, TypeError, KeyError, OSError) as exc:
        print("Mockup interrumpido: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
