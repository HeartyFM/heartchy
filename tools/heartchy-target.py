"""Explicit local descriptor: map four virtual resources, never a user's HOME tree."""
import os
from pathlib import Path
import stat

LOADERS = {
    "config/hypr/hyprland.lua": "39974ad22f150e7b47f407a808ed60299dbec53a80f7908425e5b153ace3fe8d",
    "default/hypr/bootstrap.lua": "ee16813516877df26984a78baf389f153af302e0d11736582cfbd0e002f2d531",
    "default/hypr/omarchy.lua": "e566ebf77176b0253f07fc1d57085116fe370f527601d22597748136d0f3f2e5",
}


def safe_absolute(a, raw, writable=False):
    a.require(isinstance(raw, str) and raw.startswith("/") and "\\" not in raw and
              all(p not in ("", ".", "..") for p in raw.split("/")[1:]), "invalid absolute target root")
    path = Path(raw)
    allowed = any(path.is_relative_to(p) and path != Path(p) for p in ("/home", "/tmp", "/sandbox"))
    a.require(allowed if writable else (allowed or raw == "/usr/share/omarchy"), "forbidden target/root")
    return path


def parent(a, absolute):
    parts = Path(absolute).parts[1:]
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | a.NOFOLLOW)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | a.NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd, parts[-1]
    except BaseException:
        os.close(fd)
        raise


def read(a, absolute, optional=False):
    fd = None
    try:
        fd, name = parent(a, absolute)
        source = os.open(name, os.O_RDONLY | os.O_NONBLOCK | a.NOFOLLOW, dir_fd=fd)
        with os.fdopen(source, "rb") as stream:
            info = os.fstat(stream.fileno())
            a.require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= 2_000_000,
                      "unsafe local target file: " + str(absolute))
            return stream.read()
    except FileNotFoundError:
        if optional:
            return None
        raise a.Invalid("missing local target file: " + str(absolute))
    except OSError as exc:
        raise a.Invalid("cannot safely read local target file: " + str(absolute) + ": " + exc.strerror) from exc
    finally:
        if fd is not None:
            os.close(fd)


class Binding:
    def __init__(self, a, target, marker, contracts):
        a.require(isinstance(marker, dict) and set(marker) == {"schema_version", "kind", "contracts", "config_root", "shadow_root", "stock_root"}
                  and marker["schema_version"] == 1 and type(marker["schema_version"]) is int
                  and marker["kind"] == "heartchy-local-target" and marker["contracts"] == contracts,
                  "invalid explicit local target descriptor")
        self.a, self.target = a, target
        self.config = safe_absolute(a, marker["config_root"], writable=True)
        self.shadow = safe_absolute(a, marker["shadow_root"], writable=True)
        self.stock = safe_absolute(a, marker["stock_root"])
        a.require(self.config.name == ".config" and self.shadow == self.config.parent / ".local/state",
                  "loader paths require explicit HOME/.config and the same HOME/.local/state")
        a.require(not (self.shadow.is_relative_to(self.config) or self.config.is_relative_to(self.shadow)), "overlapping config/shadow roots")
        fd, name = parent(a, self.config / "probe")
        try:
            info = os.fstat(fd)
            a.require(info.st_uid == os.getuid(), "target root is not owned by the caller")
        finally:
            os.close(fd)

    def physical(self, logical):
        prefix = self.target + "/"
        if not logical.startswith(prefix):
            return None
        suffix = logical[len(prefix):]
        if suffix.startswith("config/"):
            relative = suffix[len("config/"):]
            self.a.require(relative in ("hypr/heartchy.lua", "hypr/looknfeel.lua", "hypr/hyprland.lua", "omarchy/shell.json", "omarchy/shell.toml"), "unmanaged local file")
            return self.config / relative
        if suffix in ("state/hypr/heartchy.lua", "state/hypr/looknfeel.lua"):
            return self.shadow / suffix[len("state/"):]
        if suffix.startswith("runtime/"):
            relative = suffix[len("runtime/"):]
            self.a.require(relative in LOADERS, "unknown installed loader")
            return self.stock / relative
        return None
