"""Byte ownership and a deliberately small Lua connection recognizer.

No Lua interpreter, AST rewriting, destination IO or runtime claims live here.
The lexer separates comments/strings from instructions; the grammar accepts
only literal declarations, not arbitrary Lua whose semantics need guessing.
"""
import base64
import difflib
import hashlib
import re


MODULE = "hypr.heartchy"
LOAD_BLOCK = b'-- BEGIN HEARTCHY: hypr.heartchy v1\nrequire("hypr.heartchy")\n-- END HEARTCHY: hypr.heartchy v1\n'
ENTRYPOINT_SHA256 = "39974ad22f150e7b47f407a808ed60299dbec53a80f7908425e5b153ace3fe8d"
# This is the consumed stock instruction order, not a personal file snapshot.
ENTRYPOINT_PREFIX = '''dofile((os.getenv("OMARCHY_PATH") or "/usr/share/omarchy") .. "/default/hypr/bootstrap.lua")
require("default.hypr.omarchy")
require("hypr.monitors")
require("hypr.input")
require("hypr.bindings")
require("hypr.looknfeel")
require("hypr.autostart")
require("default.hypr.toggles")'''
HYPRMONCFG_TAIL = '''do local path = os.getenv("HOME") .. "/.config/hypr/hyprmoncfg-monitors.lua"; local file = io.open(path, "r"); if file then file:close(); dofile(path) end end'''
LIMIT = 65536
CALLS = {"hl.config", "hl.animation", "hl.bezier", "hl.layer_rule", "hl.window_rule", "o.window"}


class Unsupported(ValueError):
    pass


def fail(reason):
    raise Unsupported(reason)


def fingerprint(data):
    return {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def digest_value(data):
    return {"state": "absent"} if data is None else {"state": "present", "value": fingerprint(data)}


def difference(before, after, path, insertion=False):
    if before == after:
        return {"format": "unified", "text": ""}
    try:
        old = (before or b"").decode("utf-8").splitlines(keepends=True)
        new = after.decode("utf-8").splitlines(keepends=True)
    except UnicodeError:
        return {"format": "base64-replacement", "before": base64.b64encode(before or b"").decode(),
                "after": base64.b64encode(after).decode()}
    # No personal context is exported for a connection insertion.
    lines = difflib.unified_diff(old, new, fromfile=path if before is not None else "/dev/null",
                                tofile=path, n=0 if insertion else 3)
    # difflib leaves a final unterminated source line unterminated in its
    # output too. Preserve that distinction instead of joining -old+new.
    result = "".join(line if line.endswith("\n") else line + "\n\\ No newline at end of file\n" for line in lines)
    return {"format": "unified", "text": result}


def lex(text):
    tokens, comments = [], []
    i = 0
    while i < len(text):
        if text[i] in " \t\r\n\v\f":
            i += 1
            continue
        start = i
        comment = text.startswith("--", i)
        if comment:
            i += 2
        long = re.match(r"\[(=*)\[", text[i:])
        if long:
            opening = long.group(0)
            closing = "]" + long.group(1) + "]"
            end = text.find(closing, i + len(opening))
            if end < 0:
                fail("LUA_UNTERMINATED_LONG_COMMENT" if comment else "LUA_UNTERMINATED_LONG_STRING")
            value = text[i + len(opening):end]
            # Lua removes one initial newline from long strings.
            if value.startswith("\r\n"):
                value = value[2:]
            elif value.startswith(("\n", "\r")):
                value = value[1:]
            i = end + len(closing)
            if not comment:
                tokens.append(("string", value, start, i))
            continue
        if comment:
            end = text.find("\n", i)
            i = len(text) if end < 0 else end
            comments.append((text[start + 2:i].strip(), start, i))
            continue
        char = text[i]
        if char in "\"'":
            quote = char
            value = ""
            i += 1
            while i < len(text) and text[i] != quote:
                if text[i] in "\r\n":
                    fail("LUA_NEWLINE_IN_QUOTED_STRING")
                if text[i] == "\\":
                    i += 1
                    escapes = {"a": "\a", "b": "\b", "f": "\f", "n": "\n", "r": "\r",
                               "t": "\t", "v": "\v", "\\": "\\", "\"": "\"", "'": "'"}
                    if i == len(text) or text[i] not in escapes:
                        fail("LUA_UNSUPPORTED_STRING_ESCAPE")
                    value += escapes[text[i]]
                else:
                    value += text[i]
                i += 1
            if i == len(text):
                fail("LUA_UNTERMINATED_STRING")
            i += 1
            tokens.append(("string", value, start, i))
            continue
        name = re.match(r"[A-Za-z_][A-Za-z0-9_]*", text[i:])
        number = re.match(r"(?:[0-9]+(?:\.[0-9]+)?)(?:[eE][+-]?[0-9]+)?", text[i:])
        match = name or number
        if match:
            i += len(match.group(0))
            tokens.append(("name" if name else "number", match.group(0), start, i))
        elif text.startswith("..", i):
            i += 2
            tokens.append(("..", "..", start, i))
        elif char in "{}[](),;=.-:":
            i += 1
            tokens.append((char, char, start, i))
        else:
            fail("LUA_UNSUPPORTED_TOKEN")
        if len(tokens) > 10000:
            fail("LUA_TOO_MANY_TOKENS")
    return tokens, comments


def entrypoint(data):
    """Verify a closed stock prefix and supported later extensions, without IO.

    Token comparison ignores spelling/comments, never strings masquerading as
    code. Unknown suffix statements remain blocked rather than guessed safe.
    The personal entrypoint is examined only; insertion remains in looknfeel.
    """
    if data is None or len(data) > LIMIT:
        fail("ENTRYPOINT_ORDER_UNVERIFIED: missing or oversized entrypoint")
    try:
        text = data.decode("utf-8")
    except UnicodeError:
        fail("ENTRYPOINT_ORDER_UNVERIFIED: entrypoint is not UTF-8")
    if text.startswith("\ufeff") or "\x00" in text or "\r" in text.replace("\r\n", ""):
        fail("ENTRYPOINT_ORDER_UNVERIFIED: unsupported encoding/newlines")
    normalize = lambda code: [(t[0], t[1]) for t in lex(code)[0]]
    tokens, prefix = normalize(text), normalize(ENTRYPOINT_PREFIX)
    if tokens[:len(prefix)] != prefix:
        fail("ENTRYPOINT_ORDER_UNVERIFIED: stock bootstrap/default/personal load order differs")
    tail = tokens[len(prefix):]
    monitor_tail = normalize(HYPRMONCFG_TAIL)
    protected = {MODULE, "hypr.monitors", "hypr.input", "hypr.bindings", "hypr.looknfeel", "hypr.autostart"}
    seen = set()
    while tail:
        if tail == monitor_tail:
            return
        if tail[0] == (";", ";"):
            tail = tail[1:]
            continue
        if tail[0] != ("name", "require"):
            fail("ENTRYPOINT_SUFFIX_UNSUPPORTED: only literal later requires or the known final Hyprmoncfg guard")
        if len(tail) >= 4 and tail[1] == ("(", "(") and tail[2][0] == "string" and tail[3] == (")", ")"):
            name, tail = tail[2][1], tail[4:]
        elif len(tail) >= 2 and tail[1][0] == "string":
            name, tail = tail[1][1], tail[2:]
        else:
            fail("ENTRYPOINT_SUFFIX_UNSUPPORTED: nonliteral module load")
        if name in protected or name in seen:
            fail("ENTRYPOINT_DUPLICATE_OR_CORE_LOAD: " + name)
        if not re.fullmatch(r"hypr\.[A-Za-z_][A-Za-z0-9_]*", name):
            fail("ENTRYPOINT_SUFFIX_UNSUPPORTED: module outside supported personal namespace")
        seen.add(name)


class Declarations:
    def __init__(self, tokens):
        self.tokens = tokens + [("eof", "", -1, -1)]
        self.i = 0

    def is_kind(self, kind, offset=0):
        index = self.i + offset
        return index < len(self.tokens) and self.tokens[index][0] == kind

    def take(self, kind):
        if not self.is_kind(kind):
            fail("LUA_UNSUPPORTED_DECLARATION")
        token = self.tokens[self.i]
        self.i += 1
        return token

    def value(self, depth=0):
        if depth > 32:
            fail("LUA_TABLE_TOO_DEEP")
        if self.is_kind("string") or self.is_kind("number"):
            self.i += 1
        elif self.is_kind("name") and self.tokens[self.i][1] in ("true", "false", "nil"):
            self.i += 1
        elif self.is_kind("-"):
            self.i += 1
            self.take("number")
        elif self.is_kind("{"):
            self.i += 1
            while not self.is_kind("}"):
                if self.is_kind("name") and self.is_kind("=", 1):
                    if self.tokens[self.i][1] in {"and", "break", "do", "else", "elseif", "end", "false", "for", "function", "goto", "if", "in", "local", "nil", "not", "or", "repeat", "return", "then", "true", "until", "while"}:
                        fail("LUA_RESERVED_FIELD_NAME")
                    self.i += 2
                elif self.is_kind("["):
                    self.i += 1
                    if not (self.is_kind("string") or self.is_kind("number")):
                        fail("LUA_COMPUTED_TABLE_KEY")
                    self.i += 1
                    self.take("]")
                    self.take("=")
                self.value(depth + 1)
                if self.is_kind(",") or self.is_kind(";"):
                    self.i += 1
                elif not self.is_kind("}"):
                    fail("LUA_UNSUPPORTED_TABLE_EXPRESSION")
            self.take("}")
        else:
            fail("LUA_NON_LITERAL_VALUE")

    def scan(self):
        calls, loads = [], []
        while not self.is_kind("eof"):
            if self.is_kind(";"):
                self.i += 1
                continue
            start_token = self.take("name")
            name = start_token[1]
            if name == "require":
                parenthesized = self.is_kind("(")
                if parenthesized:
                    self.i += 1
                arg = self.take("string")
                if arg[1] != MODULE:
                    fail("LUA_INDIRECT_OR_OTHER_MODULE_LOAD")
                if parenthesized:
                    self.take(")")
                loads.append((len(calls), start_token[2], self.tokens[self.i - 1][3]))
            else:
                self.take(".")
                name += "." + self.take("name")[1]
                if name not in CALLS:
                    fail("LUA_UNSUPPORTED_TOP_LEVEL_CALL")
                self.take("(")
                self.value()
                while self.is_kind(","):
                    self.i += 1
                    self.value()
                self.take(")")
            calls.append(name)
        return loads


def connection(data, base):
    """Describe an insertion or a recognized existing load; never edit a file."""
    if data is None:
        fail("LOOKNFEEL_MISSING: no personal file seed is owned")
    if len(data) > LIMIT:
        fail("LOOKNFEEL_TOO_LARGE")
    try:
        text = data.decode("utf-8")
    except UnicodeError:
        fail("LOOKNFEEL_NOT_UTF8")
    if text.startswith("\ufeff") or "\x00" in text:
        fail("LOOKNFEEL_UNSUPPORTED_ENCODING")
    if "\r" in text.replace("\r\n", ""):
        fail("LOOKNFEEL_UNSUPPORTED_NEWLINES")
    tokens, comments = lex(text)
    markers = [c for c in comments if c[0].startswith(("BEGIN HEARTCHY", "END HEARTCHY"))]
    if markers and (len(markers) != 2 or not data.startswith(LOAD_BLOCK)
                    or markers[0][0] != "BEGIN HEARTCHY: hypr.heartchy v1"
                    or markers[1][0] != "END HEARTCHY: hypr.heartchy v1"):
        fail("LOAD_MARKERS_DAMAGED_DUPLICATED_OR_MOVED")
    loads = Declarations(tokens).scan()
    if len(loads) > 1:
        fail("DUPLICATE_EXECUTABLE_LOAD")
    if loads and loads[0][0] != 0:
        fail("LOAD_AFTER_PERSONAL_STATEMENTS: no reordering permitted")
    owned = base.get("state") == "present"
    if owned and base["value"] != fingerprint(LOAD_BLOCK):
        fail("UNKNOWN_MANAGED_LOAD_BASE")
    if markers:
        if not loads:
            fail("LOAD_MARKERS_WITHOUT_EXECUTABLE_LOAD")
        return {"current": digest_value(LOAD_BLOCK), "proposed": digest_value(LOAD_BLOCK),
                "proposed_file": data, "form": "managed-block" if owned else "unowned-marked-block"}
    if loads:
        if owned:
            fail("MANAGED_LOAD_MARKERS_REMOVED")
        _, start, end = loads[0]
        observed = text[start:end].encode()
        # Preserve an equivalent unowned spelling; do not canonicalize/adopt it.
        return {"current": digest_value(observed), "proposed": digest_value(observed),
                "proposed_file": data, "form": "unowned-equivalent-load"}
    return {"current": {"state": "absent"}, "proposed": digest_value(LOAD_BLOCK),
            "proposed_file": LOAD_BLOCK + data, "form": "missing-load"}


def row(resource, key, base, current, proposed, decision, reason, planned, path, requested):
    return {"resource": resource, "key": key, "base": base, "current": current,
            "proposed": proposed, "decision": decision, "reason": reason, "planned": planned,
            "replacement_selected": requested, "file": path, "operation": "none",
            "approval_required_at_application": decision == "REPLACEMENT_REQUESTED",
            "backup_required_at_application": decision in ("MANAGED_CHANGE", "REPLACEMENT_REQUESTED"),
            "functional_validation": "NOT_RUN", "warnings": [], "difference": {"format": "unified", "text": ""}}


def plan(planner, values, state, marker, resources, prefer, keep, global_error, decide):
    """Plan two dependent resources using the caller's scoped read-only IO."""
    a, target = planner.a, planner.args_target
    result = []
    module_path = target + "/config/hypr/heartchy.lua"
    look_path = target + "/config/hypr/looknfeel.lua"
    proposal_bytes = planner.module_bytes
    previous = state["resources"] if state else {}

    def base_for(resource, key):
        return ({"state": "unknown"} if global_error else
                previous.get(resource, {}).get("values", {}).get(key, {"state": "unmanaged"}))

    def check_contract(resource):
        a.require(not global_error, global_error)
        a.require(marker["contracts"].get(resource) == planner.contracts[resource], "UNSUPPORTED_TARGET_CONTRACT")

    errors = (a.Invalid, ValueError, TypeError, KeyError, AttributeError)
    module_raw, module_problem = None, None
    try:
        check_contract("hypr_module")
        module_raw = planner.read(module_path, optional=True)
        a.require(module_raw is None or len(module_raw) <= LIMIT, "MODULE_TOO_LARGE")
    except errors as exc:
        module_problem = str(exc)
    actual = {"state": "unknown"} if module_problem else digest_value(module_raw)
    proposed = digest_value(proposal_bytes)
    dependency = {"resource": "hypr_module", "key": "content", "file": module_path,
                  "required": proposed, "scope": "current-only", "satisfied": False}
    if "hypr_module" in resources:
        requested = ("hypr_module", "content") in prefer
        base = base_for("hypr_module", "content")
        if module_problem:
            decision, reason, planned = "BLOCKED", module_problem, actual
        else:
            decision, reason, planned = decide(base, actual, proposed, requested, ("hypr_module", "content") in keep)
        module = row("hypr_module", "content", base, actual, proposed, decision, reason, planned, module_path, requested)
        module["ownership_evidence"] = "applied-file-hash" if base["state"] == "present" else "none"
        if not module_problem:
            module["difference"] = difference(module_raw, proposal_bytes, module_path)
            if decision in ("MANAGED_CHANGE", "REPLACEMENT_REQUESTED"):
                module["operation"] = "create-file" if module_raw is None else "replace-file"
            if planned != proposed:
                module["warnings"].append("LOCAL_MODULE_PRESERVED_WITHOUT_FUNCTIONAL_VALIDATION")
        result.append(module)
        dependency.update(scope="planned-module", decision=decision,
                          satisfied=decision not in ("BLOCKED", "CONFLICT_PENDING") and planned == proposed,
                          approval_pending=module["approval_required_at_application"])
    else:
        dependency["satisfied"] = actual == proposed
    if "hypr_connection" not in resources:
        return result

    base = base_for("hypr_connection", "load")
    requested = ("hypr_connection", "load") in prefer
    look_raw, recognized = None, None
    current = {"state": "unknown"}
    wanted = digest_value(LOAD_BLOCK)
    try:
        check_contract("hypr_connection")
        look_raw = planner.read(look_path, optional=True)
        entrypoint_raw = planner.read(target + "/config/hypr/hyprland.lua", optional=True)
        entrypoint(entrypoint_raw)
        # Bootstrap's state path precedes user configuration for these modules.
        for name in ("heartchy", "looknfeel"):
            shadow = planner.read(target + "/state/hypr/" + name + ".lua", optional=True)
            a.require(shadow is None, "STATE_MODULE_SHADOW: " + name)
        recognized = connection(look_raw, base)
        current, wanted = recognized["current"], recognized["proposed"]
        a.require(dependency["satisfied"], "MODULE_DEPENDENCY_UNSATISFIED: missing, blocked or preserved non-proposal bytes")
        decision, reason, planned = decide(base, current, wanted, requested, ("hypr_connection", "load") in keep)
        if recognized["form"] != "missing-load":
            decision, reason, planned = "NO_CHANGE", recognized["form"].upper().replace("-", "_"), current
    except errors as exc:
        decision, reason, planned = "BLOCKED", str(exc), current
    link = row("hypr_connection", "load", base, current, wanted, decision, reason, planned, look_path, requested)
    link["depends_on"] = [dependency]
    link["examined_file"] = digest_value(look_raw) if look_path in planner.inputs else {"state": "unknown"}
    link["warnings"] = ["PERSONAL_DECLARATIONS_REMAIN_AFTER_LOAD; SEMANTIC_RULE_CONFLICTS_NOT_CHECKED"]
    if recognized:
        link["form"] = recognized["form"]
        link["ownership"] = "managed-block" if recognized["form"] == "managed-block" else "not-established"
        link["proposed_file"] = digest_value(recognized["proposed_file"])
        link["difference"] = difference(look_raw, recognized["proposed_file"], look_path, insertion=True)
        if decision in ("MANAGED_CHANGE", "REPLACEMENT_REQUESTED"):
            link["operation"] = "insert-prefix"
            link["insertion"] = {"byte_offset": 0, "text": LOAD_BLOCK.decode()}
            link["approval_required_at_application"] |= dependency.get("approval_pending", False)
    result.append(link)
    return result
