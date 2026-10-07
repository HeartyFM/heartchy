"""Scoped Core effects. A private journal is recovery evidence, not an installer DSL."""
import base64
import copy
import datetime
import difflib
import fcntl
import json
import math
import os
from pathlib import Path
import re
import stat
from types import SimpleNamespace
import uuid

PATHS = {"hypr_module": "config/hypr/heartchy.lua", "hypr_connection": "config/hypr/looknfeel.lua",
         "shell_intent": "config/omarchy/shell.json", "shell_tokens": "config/omarchy/shell.toml"}
CHANGES = {"MANAGED_CHANGE", "REPLACEMENT_REQUESTED"}
TERMINAL = {"SUCCESS", "RECOVERED"}


def stamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def blob(data):
    return None if data is None else base64.b64encode(data).decode()


def unblob(value):
    return None if value is None else base64.b64decode(value, validate=True)


def stored(value):
    return {"state": "absent"} if value is None else {"state": "present", "value": value}


def same_toml(left, right):
    """Compare foreign parsed data, including TOML's legitimate NaN values."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(same_toml(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(same_toml(a, b) for a, b in zip(left, right))
    if isinstance(left, float) and math.isnan(left):
        return math.isnan(right)
    return left == right


def toml_edit(a, data, changes):
    """Edit only simple key lines accepted by the installed Shell line walker."""
    text = (data or b"").decode()
    _, lines, headings, seen, boundaries = a.recipient_toml_index(data or b"")
    newline = "\r\n" if "\r\n" in text else "\n"
    pending = {}
    for path, record in changes.items():
        section, key = path.split(".")
        value = record.get("value")
        if record["state"] == "present":
            a.require(type(value) in (str, int, float), "BLOCKED: unsupported TOML value")
            rendered = json.dumps(value, ensure_ascii=False, allow_nan=False)
            # The candidate uses no escapes; a rollback origin may contain one
            # only if parse_stock_toml accepted it (which excludes escapes).
        else:
            rendered = None
        index = seen.get((section, key))
        if index is not None:
            if rendered is None:
                # A later inline comment belongs to the user even when the
                # managed key itself was an addition now being removed.
                raw = lines[index]
                tail = re.fullmatch(r'''\s*[A-Za-z0-9_-]+\s*=\s*(?:"[^"'\\]+"|'[^'"\\]+'|-?[0-9]+(?:\.[0-9]+)?)(\s*(?:#.*)?)(\r?\n)?''', raw)
                a.require(tail is not None, "BLOCKED: ambiguous TOML managed line")
                lines[index] = tail[1].lstrip() + (tail[2] or "") if "#" in tail[1] else ""
            else:
                raw = lines[index]
                match = re.fullmatch(r'''(\s*[A-Za-z0-9_-]+\s*=\s*)(?:"[^"'\\]+"|'[^'"\\]+'|-?[0-9]+(?:\.[0-9]+)?)(\s*(?:#.*)?)(\r?\n)?''', raw)
                a.require(match is not None, "BLOCKED: ambiguous TOML managed line")
                lines[index] = match[1] + rendered + match[2] + (match[3] or "")
        elif rendered is not None:
            pending.setdefault(section, []).append(f"{key} = {rendered}{newline}")
    # Insert at the end of the exact section, without moving personal lines.
    positions = sorted((index, name) for name, index in headings.items())
    for j in range(len(positions) - 1, -1, -1):
        index, section = positions[j]
        if section in pending:
            end = next((n for n in boundaries if n > index), len(lines))
            if end and lines[end - 1] and not lines[end - 1].endswith("\n"):
                lines[end - 1] += newline
            lines[end:end] = pending.pop(section)
    for section, added in sorted(pending.items()):
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += newline
        lines += [f"[{section}]{newline}", *added]
    result = "".join(lines).encode()
    a.parse_recipient_toml(result)
    return result


class Operations:
    def __init__(self, api, args, fault=None):
        self.a = SimpleNamespace(**api)
        self.args, self.fault = args, fault or (lambda phase, index: None)
        self.ns = {"__name__": "heartchy_plan"}
        exec(compile(self.a.read_project("tools/heartchy-plan.py"), "tools/heartchy-plan.py", "exec"), self.ns)
        self.planner = self.ns["Planner"](api, SimpleNamespace())
        self.target = self.planner.location(args.target, "target")
        self.root = self.planner.location(args.state_root, "state")
        self.planner.configure_target(self.target)
        self.planner.args.state_root = self.root
        self.target_identity = self.identity(self.planner.read(self.target + "/target.json"))
        self.a.require(re.fullmatch(r"build/state/[a-zA-Z0-9_-]+", self.root) or
                       (getattr(self.a, "RUNTIME_MODE", False) and self.root == "managed"), "invalid state root")
        self.paths = {r: self.target + "/" + p for r, p in PATHS.items()}
        self.lock = None
        self.target_lock = None

    def read(self, path, optional=True):
        physical = self.planner.binding.physical(path) if self.planner.binding else None
        return (self.planner.target_helpers["read"](self.a, physical, optional) if physical is not None
                else self.a.read_project(path, missing_ok=optional))

    def json(self, path):
        raw = self.read(path)
        return self.a.parse_json(raw, path) if raw is not None else None

    def identity(self, data):
        return {"exists": data is not None, "sha256": self.a.digest(data) if data is not None else None}

    def parent(self, path, create=False):
        physical = self.planner.binding.physical(path) if self.planner.binding else None
        if physical is not None:
            return self.planner.target_helpers["parent"](self.a, physical)
        parts = self.a.relative_parts(path)
        fd = os.open(self.a.ROOT, os.O_RDONLY | os.O_DIRECTORY | self.a.NOFOLLOW)
        try:
            for part in parts[:-1]:
                if create:
                    try:
                        os.mkdir(part, 0o700, dir_fd=fd)
                    except FileExistsError:
                        pass
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | self.a.NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = child
            return fd, parts[-1]
        except BaseException:
            os.close(fd)
            raise

    def atomic(self, path, data, expected, mode=0o600):
        """CAS immediately before a per-file replace; never follow a path link."""
        fd, name = self.parent(path, create=path.startswith(self.root + "/"))
        temp = ".heartchy-" + uuid.uuid4().hex
        try:
            self.a.require(self.identity(self.read(path)) == expected, "changed before write: " + path)
            if data is None:
                if expected["exists"]:
                    os.unlink(name, dir_fd=fd)
            else:
                output = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | self.a.NOFOLLOW, mode, dir_fd=fd)
                with os.fdopen(output, "wb") as stream:
                    os.fchmod(stream.fileno(), mode)
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                self.a.require(self.identity(self.read(path)) == expected, "changed during write: " + path)
                os.replace(temp, name, src_dir_fd=fd, dst_dir_fd=fd)
            os.fsync(fd)
        finally:
            try:
                os.unlink(temp, dir_fd=fd)
            except FileNotFoundError:
                pass
            os.close(fd)

    def write_metadata(self, path, value):
        self.atomic(path, self.a.json_bytes(value), self.identity(self.read(path)))

    def acquire(self):
        config = (self.planner.binding.config if self.planner.binding else self.a.ROOT / self.target / "config")
        fd, name = self.planner.target_helpers["parent"](self.a, config / "probe")
        self.target_lock = fd
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise self.a.Invalid("operation already in progress on this target") from exc
        # One persistent authority for this target, shared across checkouts and
        # state roots. It lives in Heartchy's state, never in personal config.
        if self.planner.binding:
            authority = self.planner.binding.shadow / "heartchy/core-authority.json"
        else:
            info = os.fstat(fd)
            authority = config.parent.parent / ".heartchy-authorities" / f"{info.st_dev}-{info.st_ino}.json"
        self.authority = authority
        expected = self.a.json_bytes({"schema_version": 1, "state_root": str(self.a.ROOT / self.root)})
        current = self.planner.target_helpers["read"](self.a, authority, optional=True)
        self.a.require(current in (None, expected),
                       "TARGET_STATE_AUTHORITY_MISMATCH: use the original state root; never remove its authority blindly")
        fd, name = self.parent(self.root + "/lock", create=True)
        try:
            self.lock = os.open(name, os.O_RDWR | os.O_CREAT | self.a.NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=fd)
            info = os.fstat(self.lock)
            self.a.require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "unsafe state lock")
            try:
                fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise self.a.Invalid("operation already in progress") from exc
        finally:
            os.close(fd)

    def claim_authority(self):
        # Called only after an approved plan/rollback has prepared its changes.
        # Publish a complete claim atomically while the physical target is locked.
        authority = self.authority
        expected = self.a.json_bytes({"schema_version": 1, "state_root": str(self.a.ROOT / self.root)})
        current = self.planner.target_helpers["read"](self.a, authority, optional=True)
        self.a.require(current in (None, expected), "TARGET_STATE_AUTHORITY_MISMATCH")
        if current is not None:
            return
        directory = os.open("/", os.O_RDONLY | os.O_DIRECTORY | self.a.NOFOLLOW)
        temp = ".claim-" + uuid.uuid4().hex
        try:
            for part in authority.parent.parts[1:]:
                try:
                    os.mkdir(part, 0o700, dir_fd=directory)
                except FileExistsError:
                    pass
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | self.a.NOFOLLOW, dir_fd=directory)
                os.close(directory)
                directory = child
            claim = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | self.a.NOFOLLOW, 0o600, dir_fd=directory)
            with os.fdopen(claim, "wb") as stream:
                stream.write(expected)
                stream.flush()
                os.fsync(stream.fileno())
            self.fault("authority_prepared", 0)
            os.replace(temp, authority.name, src_dir_fd=directory, dst_dir_fd=directory)
            os.fsync(directory)
        finally:
            try:
                os.unlink(temp, dir_fd=directory)
            except FileNotFoundError:
                pass
            os.close(directory)

    def journals(self):
        directory = self.a.ROOT / self.root / "operations"
        if not directory.exists():
            return []
        fd, _ = self.parent(self.root + "/operations/probe")
        try:
            names = os.listdir(fd)
        finally:
            os.close(fd)
        result = []
        for name in sorted(names):
            self.a.require(re.fullmatch(r"[0-9a-f]{32}", name), "corrupt operation directory")
            path = f"{self.root}/operations/{name}/journal.json"
            journal = self.json(path)
            self.check_journal(journal, name)
            result.append((path, journal))
        return result

    def check_journal(self, j, name):
        self.a.require(isinstance(j, dict) and j.get("kind") == "heartchy-operation" and j.get("id") == name
                       and type(j.get("schema_version")) is int and j["schema_version"] == 1
                       and j.get("operation") in ("apply", "rollback")
                       and j.get("target") == self.target and j.get("state_root") == self.root
                       and j.get("target_identity") == self.target_identity
                       and j.get("status") in TERMINAL | {"PREPARING", "PREPARED", "COMMITTING", "RECOVERY_REQUIRED"}
                       and isinstance(j.get("files"), list), "corrupt journal / target mismatch; RECOVERY_REQUIRED")
        allowed = set(self.paths.values()) | {self.root + "/managed.json", self.root + "/ledger.json"}
        paths = [f.get("path") for f in j["files"] if isinstance(f, dict)]
        self.a.require(len(paths) == len(j["files"]) and len(set(paths)) == len(paths) and set(paths) <= allowed,
                       "journal outside owned file scope; RECOVERY_REQUIRED")
        for record in j["files"]:
            self.a.require(type(record.get("committed")) is bool and type(record.get("restored")) is bool,
                           "corrupt journal progress; RECOVERY_REQUIRED")
            for side in ("before", "after"):
                identity = record.get(side)
                self.a.require(isinstance(identity, dict) and set(identity) == {"exists", "sha256"}
                               and type(identity["exists"]) is bool and
                               (re.fullmatch(r"[0-9a-f]{64}", identity["sha256"] or "") if identity["exists"]
                                else identity["sha256"] is None), "corrupt journal hash; RECOVERY_REQUIRED")
            self.a.require(type(record.get("mode")) is int and record["mode"] in (0o600, 0o640, 0o644),
                           "unsupported journal file permissions; RECOVERY_REQUIRED")

    def clean(self):
        pending = [(p, j) for p, j in self.journals() if j["status"] not in TERMINAL]
        self.a.require(not pending, "RECOVERY_REQUIRED: " + ", ".join(j["id"] for _, j in pending))

    def ledger(self):
        state, ledger = self.json(self.root + "/managed.json"), self.json(self.root + "/ledger.json")
        self.a.require((state is None) == (ledger is None), "partial managed state; RECOVERY_REQUIRED")
        if ledger is not None:
            self.a.require(isinstance(ledger, dict) and ledger.get("kind") == "heartchy-ownership"
                           and ledger.get("schema_version") == 1 and ledger.get("target") == self.target
                           and ledger.get("target_identity") == self.target_identity
                           and isinstance(ledger.get("owned"), dict) and isinstance(ledger.get("files"), dict)
                           and ledger.get("managed_sha256") == self.a.digest(self.read(self.root + "/managed.json")),
                           "corrupt state/ledger; RECOVERY_REQUIRED")
            try:
                self.planner.applied_state(self.target, self.reference_values())
            except self.a.Invalid as exc:
                raise self.a.Invalid("corrupt managed state; RECOVERY_REQUIRED: " + str(exc)) from exc
            op = ledger.get("operation_id")
            self.a.require(isinstance(op, str) and re.fullmatch(r"[0-9a-f]{32}", op)
                           and state["application_id"] == op, "incoherent state operation; RECOVERY_REQUIRED")
            last = self.json(f"{self.root}/operations/{op}/journal.json")
            self.check_journal(last, op)
            self.a.require(last["status"] == "SUCCESS", "state lacks successful operation; RECOVERY_REQUIRED")
            recorded = {f["path"]: f["after"] for f in last["files"]}
            for path in (self.root + "/managed.json", self.root + "/ledger.json"):
                self.a.require(recorded.get(path) == self.identity(self.read(path)),
                               "corrupt managed metadata postimage; RECOVERY_REQUIRED")
            reference = self.reference_values()
            accepted = ledger.get("accepted", {})
            self.a.require(isinstance(accepted, dict) and not set(accepted) & set(ledger["owned"]),
                           "corrupt acceptance/ownership; RECOVERY_REQUIRED")
            recorded_acceptance = {resource + ":" + key for resource, r in state["resources"].items()
                                   for key in r.get("accepted", [])}
            self.a.require(recorded_acceptance == set(accepted), "incoherent matching acceptance; RECOVERY_REQUIRED")
            for selector, value in accepted.items():
                resource, key = selector.split(":", 1)
                self.a.require(resource in ("shell_intent", "shell_tokens")
                               and value == state["resources"][resource]["values"][key],
                               "corrupt accepted reference; RECOVERY_REQUIRED")
            for selector, item in ledger["owned"].items():
                self.a.require(isinstance(selector, str) and ":" in selector and isinstance(item, dict)
                               and set(item) == {"original", "applied", "original_bytes"}, "corrupt ownership record")
                resource, key = selector.split(":", 1)
                self.a.require(resource in PATHS and item["applied"] == state["resources"].get(resource, {}).get("values", {}).get(key),
                               "incoherent ownership record; RECOVERY_REQUIRED")
                self.a.require(key in reference[resource], "unknown owned key; RECOVERY_REQUIRED")
                original = item["original"]
                self.a.require(isinstance(original, dict) and (original == {"state": "absent"} or
                               (set(original) == {"state", "value"} and original["state"] == "present")), "corrupt original; RECOVERY_REQUIRED")
                if original["state"] == "present":
                    self.planner.check_type(original["value"], reference[resource][key])
                if resource == "hypr_module":
                    self.a.require(self.planner.lua["digest_value"](unblob(item["original_bytes"])) == original,
                                   "corrupt module origin; RECOVERY_REQUIRED")
                else:
                    self.a.require(item["original_bytes"] is None, "unexpected original bytes")
            self.a.require(set(ledger["files"]) <= set(self.paths.values()), "state has unexpected files")
            for resource, record in state["resources"].items():
                if set(record["values"]) <= set(record.get("accepted", [])):
                    continue
                info = ledger["files"].get(self.paths[resource])
                self.a.require(isinstance(info, dict) and type(info.get("existed")) is bool, "corrupt file ownership; RECOVERY_REQUIRED")
            self.a.require(sum(len(r["values"]) for r in state["resources"].values()) == len(ledger["owned"]) + len(accepted),
                           "state has unaccounted keys; RECOVERY_REQUIRED")
        return state, ledger

    def plan(self):
        raw = self.read(self.planner.location(self.args.plan, "previous plan"), False)
        self.a.require(self.args.approve == self.a.digest(raw), "approval must equal the SHA-256 of the reviewed plan")
        saved = self.a.parse_json(raw, "approved plan")
        self.a.require(saved.get("state_root") == self.root, "plan must use this explicit state root")
        selection = saved.get("selection", {})
        arguments = SimpleNamespace(candidate=self.args.candidate, target=self.target, state_root=self.root,
                                    resource=selection.get("resources"), prefer_heartchy=selection.get("prefer_heartchy", []),
                                    keep_local=selection.get("keep_local", []), recheck=None, format="json")
        planner = self.ns["Planner"](vars(self.a), arguments)
        current = planner.run()
        # Compare decisions as well as hashes. Editing a saved plan is not a way
        # to invent operations that the real planner never authorized.
        comparable = lambda p: {k: v for k, v in p.items() if k != "freshness"}
        self.a.require(comparable(saved) == comparable(current), "STALE_OR_INVALID_PLAN: regenerate and review")
        self.a.require(not current["blocked"] and not current["pending_conflicts"], "unresolved or BLOCKED plan")
        self.a.require(all(row["decision"] in CHANGES | {"NO_CHANGE", "LOCAL_PRESERVED"} for row in current["entries"]),
                       "invalid plan decisions")
        self.a.require(bool(current["entries"]), "empty plan")
        return current, planner, self.a.digest(raw)

    def transform(self, resource, before, changes, module=None, removing=False):
        if resource == "hypr_module":
            return module
        if resource == "hypr_connection":
            block = self.planner.lua["LOAD_BLOCK"]
            if removing:
                self.a.require(before is not None and before.startswith(block), "BLOCKED: owned load block damaged")
                # Lexer verifies no duplicate/ambiguous markers; no Lua execution.
                self.planner.lua["connection"](before, stored(self.planner.lua["fingerprint"](block)))
                return before[len(block):]
            self.a.require(before is not None, "BLOCKED: looknfeel absent")
            recognized = self.planner.lua["connection"](before, {"state": "unmanaged"})
            self.a.require(recognized["form"] == "missing-load", "BLOCKED: cannot adopt an existing load")
            return block + before
        if resource == "shell_tokens":
            return toml_edit(self.a, before, changes)
        document = self.a.parse_json(before, "shell.json")
        self.a.require(document.get("version") == 1 and isinstance(document.get("bar", {}), dict)
                       and document.get("bar", {}).get("id", "omarchy.bar") == "omarchy.bar", "BLOCKED: JSON stock bar contract")
        other = copy.deepcopy(document)
        for key, value in changes.items():
            self.a.require(key == "bar.transparent", "JSON key outside managed scope")
            if value["state"] == "present":
                document.setdefault("bar", {})["transparent"] = value["value"]
            else:
                document.get("bar", {}).pop("transparent", None)
                if "bar" not in other and not document.get("bar"):
                    document.pop("bar", None)
        return self.a.json_bytes(document)

    def values(self, resource, data):
        if resource == "hypr_module":
            return {"content": self.planner.lua["digest_value"](data)}
        if resource == "hypr_connection":
            # Rollback requires canonical owned prefix, regardless of personal
            # declarations appended afterwards; lexer still rejects ambiguity.
            r = self.planner.lua["connection"](data, {"state": "unmanaged"})
            return {"load": r["current"]}
        if resource == "shell_intent":
            doc = self.a.parse_json(data, "shell.json")
            self.a.require(type(doc.get("version")) is int and doc["version"] == 1
                           and isinstance(doc.get("bar", {}), dict)
                           and doc.get("bar", {}).get("id", "omarchy.bar") == "omarchy.bar", "BLOCKED: JSON contract changed")
            bar = doc.get("bar", {})
            return {"bar.transparent": stored(bar["transparent"]) if "transparent" in bar else stored(None)}
        return {k: stored(v) for k, v in self.a.recipient_toml_values(data or b"").items()}

    def preservation(self, resource, before, after, changes, removing=False):
        if resource == "hypr_connection":
            block = self.planner.lua["LOAD_BLOCK"]
            self.a.require((before == block + after) if removing else (after == block + before), "personal Lua bytes changed")
        elif resource in ("shell_intent", "shell_tokens"):
            def outside(data):
                if resource == "shell_intent":
                    doc = self.a.parse_json(data, "JSON preservation")
                    doc.get("bar", {}).pop("transparent", None)
                    if doc.get("bar") == {}:
                        doc.pop("bar")
                    return doc
                doc = self.a.parse_recipient_toml(data or b"")
                for path in changes:
                    section, key = path.split(".")
                    if section in doc:
                        doc[section].pop(key, None)
                        if not doc[section]:
                            del doc[section]
                return doc
            left, right = outside(before), outside(after)
            self.a.require(same_toml(left, right) if resource == "shell_tokens" else left == right,
                           "unmanaged values changed")

    def resource_file(self, resource, before, after):
        path = self.paths[resource]
        fd, name = self.parent(path)
        try:
            mode = os.stat(name, dir_fd=fd, follow_symlinks=False).st_mode & 0o777 if before is not None else 0o644
        finally:
            os.close(fd)
        self.a.require(mode in (0o600, 0o640, 0o644), "BLOCKED: unsupported file permissions")
        return {"path": path, "before": self.identity(before), "after": self.identity(after), "mode": mode,
                "before_bytes": before, "after_bytes": after, "committed": False, "restored": False}

    def mode_matches(self, record):
        if self.read(record["path"]) is None:
            return True
        fd, name = self.parent(record["path"])
        try:
            return os.stat(name, dir_fd=fd, follow_symlinks=False).st_mode & 0o777 == record["mode"]
        finally:
            os.close(fd)

    def apply(self):
        self.clean()
        previous, old = self.ledger()
        plan, planner, approval = self.plan()
        self.planner = planner
        ledger = copy.deepcopy(old) if old else {"schema_version": 1, "kind": "heartchy-ownership", "target": self.target,
                                               "target_identity": self.target_identity, "owned": {}, "files": {}}
        accepted = ledger.setdefault("accepted", {})
        adopted = []
        groups = {}
        for row in plan["entries"]:
            selector = row["resource"] + ":" + row["key"]
            if row.get("state_operation") == "accept-matching-reference":
                self.a.require(row["resource"] in ("shell_intent", "shell_tokens") and row["decision"] == "NO_CHANGE"
                               and row["base"]["state"] == "unmanaged" and row["current"] == row["proposed"],
                               "invalid matching-state acceptance")
                accepted[selector] = row["current"]
                adopted.append(selector)
            if row["decision"] not in CHANGES:
                continue
            # A reference becomes a written change only now. Its original is
            # the actual pre-write value, not a fabricated pre-adoption value.
            accepted.pop(selector, None)
            original = ledger["owned"].get(selector)
            before = self.read(self.paths[row["resource"]])
            # A newly approved replacement of a local edit must remain
            # recoverable. Normal managed updates keep the adoption origin;
            # replacing a later preference makes that preference the origin.
            if original and row["decision"] == "REPLACEMENT_REQUESTED" and row["current"] != original["applied"]:
                original = None
            ledger["files"].setdefault(self.paths[row["resource"]], {"existed": before is not None})
            if row["resource"] == "shell_intent":
                ledger["files"][self.paths[row["resource"]]].setdefault("bar_created", "bar" not in self.a.parse_json(before, "original JSON"))
            if row["resource"] == "shell_tokens":
                sections = self.a.parse_recipient_toml(before or b"")
                section = row["key"].split(".")[0]
                created = ledger["files"][self.paths[row["resource"]]].setdefault("created_sections", [])
                if section not in sections and section not in created:
                    created.append(section)
            ledger["owned"][selector] = {"original": original["original"] if original else row["current"],
                "original_bytes": original["original_bytes"] if original else (blob(before) if row["resource"] == "hypr_module" else None),
                "applied": row["planned"]}
            groups.setdefault(row["resource"], {})[row["key"]] = row["planned"]
        if not groups and not adopted:
            return {"result": "NO_CHANGE", "operation_id": None, "local_preserved": [r["resource"] + ":" + r["key"] for r in plan["entries"] if r["decision"] == "LOCAL_PRESERVED"], "structural_validation": "PASS", "functional_validation": "NOT_RUN"}
        files = []
        # Respect the known load dependency even though the filesystem cannot
        # make the complete operation atomic to watchers.
        order = {"hypr_module": 0, "hypr_connection": 1, "shell_intent": 2, "shell_tokens": 3}
        for resource, changes in sorted(groups.items(), key=lambda item: order[item[0]]):
            before = self.read(self.paths[resource])
            after = self.transform(resource, before, changes, planner.module_bytes)
            self.preservation(resource, before, after, changes)
            observed = self.values(resource, after)
            self.a.require(all(observed.get(k, stored(None)) == v for k, v in changes.items()), "prepared managed value mismatch")
            files.append(self.resource_file(resource, before, after))
        result = self.transaction("apply", files, ledger, plan["inputs"], {"plan_sha256": approval,
                                  "inventory_sha256": plan["inputs"][plan["candidate"] + "/inventory.json"]["sha256"]})
        result["local_preserved"] = [r["resource"] + ":" + r["key"] for r in plan["entries"] if r["decision"] == "LOCAL_PRESERVED"]
        result["accepted_matching"] = adopted
        return result

    def rollback(self):
        self.a.require(self.args.approve == "rollback", "--approve rollback required")
        self.clean()
        state, ledger = self.ledger()
        if state is None or not (ledger["owned"] or ledger.get("accepted")):
            return {"result": "NO_CHANGE", "reason": "ALREADY_REMOVED", "operation_id": None}
        # Validate base schema/types via the same planner validator, not just the ledger hash.
        values = self.reference_values()
        self.planner.args.state_root = self.root
        self.planner.applied_state(self.target, values)
        requested = set(self.args.replace)
        self.a.require(requested <= set(ledger["owned"]), "replacement selector outside owned scope")
        groups, conflicts, files, already_restored = {}, [], [], []
        remaining = copy.deepcopy(ledger)
        released = sorted(remaining.pop("accepted", {}))
        inputs = {self.root + "/managed.json": self.identity(self.read(self.root + "/managed.json")),
                  self.root + "/ledger.json": self.identity(self.read(self.root + "/ledger.json"))}
        observed = {}
        for resource in PATHS:
            if any(s.startswith(resource + ":") for s in ledger["owned"]):
                before = self.read(self.paths[resource])
                inputs[self.paths[resource]] = self.identity(before)
                observed[resource] = self.values(resource, before)
        for selector, item in ledger["owned"].items():
            resource, key = selector.split(":", 1)
            current = observed[resource].get(key, stored(None))
            if current == item["original"]:
                # The user already restored/removed our own change. Release
                # its record without inserting or rewriting anything.
                del remaining["owned"][selector]
                already_restored.append(selector)
                continue
            if current != item["applied"] and selector not in requested:
                conflicts.append({"resource": resource, "key": key, "decision": "LOCAL_PRESERVED",
                                  "current": current, "applied": item["applied"], "original": item["original"]})
                continue
            groups.setdefault(resource, {})[key] = item["original"]
            del remaining["owned"][selector]
        # Never remove/restore the module while a retained owned load needs it.
        if "hypr_module" in groups and "hypr_connection:load" in remaining["owned"]:
            raise self.a.Invalid("BLOCKED: module rollback has a retained managed connection")
        if "hypr_module" in groups and groups["hypr_module"]["content"]["state"] == "absent":
            look = self.read(self.paths["hypr_connection"])
            if "hypr_connection" not in groups and look is not None:
                connection = self.planner.lua["connection"](look, {"state": "unmanaged"})
                self.a.require(connection["current"]["state"] == "absent", "BLOCKED: unowned load still depends on module")
        for resource, changes in sorted(groups.items()):
            before = self.read(self.paths[resource])
            item = ledger["owned"].get(resource + ":content")
            module = unblob(item["original_bytes"]) if item else None
            if item:
                self.a.require(self.planner.lua["digest_value"](module) == item["original"], "corrupt module origin; RECOVERY_REQUIRED")
            after = self.transform(resource, before, changes, module, removing=True)
            if resource == "shell_intent" and ledger["files"][self.paths[resource]].get("bar_created"):
                document = self.a.parse_json(after, "rollback JSON")
                if document.get("bar") == {}:
                    document.pop("bar")
                    after = self.a.json_bytes(document)
            if resource == "shell_tokens":
                document, lines, headings, _, boundaries = self.a.recipient_toml_index(after)
                empty = {section for section in ledger["files"][self.paths[resource]].get("created_sections", [])
                         if not document.get(section)}
                # Do not remove an empty section carrying later personal comments.
                for section, start in sorted(headings.items(), key=lambda item: item[1], reverse=True):
                    end = next((n for n in boundaries if n > start), len(lines))
                    if section in empty and not "".join(lines[start + 1:end]).strip() and "#" not in lines[start]:
                        del lines[start:end]
                after = "".join(lines).encode()
            self.preservation(resource, before, after, changes, removing=True)
            observed_after = self.values(resource, after)
            self.a.require(all(observed_after.get(k, stored(None)) == v for k, v in changes.items()), "rollback prepared value mismatch")
            if resource == "shell_tokens" and not ledger["files"][self.paths[resource]]["existed"]:
                if not self.a.parse_recipient_toml(after) and not any(l.strip().startswith("#") for l in after.decode().splitlines()):
                    after = None
            files.append(self.resource_file(resource, before, after))
        if not files and remaining["owned"] == ledger["owned"] and not released:
            return {"result": "LOCAL_PRESERVED", "conflicts": conflicts, "operation_id": None}
        inputs.update(self.planner.inputs)
        inputs[self.target + "/target.json"] = self.target_identity
        result = self.transaction("rollback", files, remaining, inputs, ledger.get("candidate"))
        result["conflicts"] = conflicts
        result["already_restored"] = already_restored
        result["acceptance_released_without_writes"] = released
        result["result"] = "PARTIAL_ROLLBACK" if conflicts else "SUCCESS"
        return result

    def reference_values(self):
        tokens = self.a.read_project("core/shell/cristal.toml")
        self.a.inspect_tokens(tokens)
        values = {"hypr_module": {"content": self.planner.lua["fingerprint"](b"")},
                  "hypr_connection": {"load": self.planner.lua["fingerprint"](self.planner.lua["LOAD_BLOCK"])},
                  "shell_intent": {"bar.transparent": True},
                  "shell_tokens": self.a.flat(self.a.parse_stock_toml(tokens))}
        return values

    def transaction(self, kind, files, ledger, inputs, candidate):
        self.fault("before_prepare", 0)
        self.claim_authority()
        op = uuid.uuid4().hex
        # A completed withdrawal releases file/section creation metadata too.
        # A later user-created empty file must not inherit our old ownership.
        active_paths = {self.paths[s.split(":", 1)[0]] for s in ledger["owned"]}
        ledger["files"] = {p: v for p, v in ledger["files"].items() if p in active_paths}
        resources = {}
        for selector, item in ledger["owned"].items():
            resource, key = selector.split(":", 1)
            resources.setdefault(resource, {"contract": self.ns["CONTRACTS"][resource], "values": {}})["values"][key] = item["applied"]
        for selector, value in sorted(ledger.get("accepted", {}).items()):
            resource, key = selector.split(":", 1)
            record = resources.setdefault(resource, {"contract": self.ns["CONTRACTS"][resource], "values": {}})
            record["values"][key] = value
            record.setdefault("accepted", []).append(key)
        state = {"schema_version": 1, "kind": "heartchy-managed-state", "successful": True,
                 "application_id": op, "resources": resources}
        state_bytes = self.a.json_bytes(state)
        ledger.update(candidate=candidate, operation_id=op, applied_at=stamp(), result="SUCCESS",
                      managed_sha256=self.a.digest(state_bytes))
        ledger.setdefault("applied_files", {}).update({f["path"]: f["after"] for f in files})
        for path, after in ((self.root + "/managed.json", state_bytes), (self.root + "/ledger.json", self.a.json_bytes(ledger))):
            before = self.read(path)
            files.append({"path": path, "before": self.identity(before), "after": self.identity(after), "mode": 0o600,
                          "before_bytes": before, "after_bytes": after, "committed": False, "restored": False})
        journal_path = f"{self.root}/operations/{op}/journal.json"
        # All complete pre/post images stay PRIVATE and outside observed config.
        # They are emergency recovery data, not the normal rollback mechanism.
        journal = {"schema_version": 1, "kind": "heartchy-operation", "id": op, "operation": kind,
                   "target": self.target, "state_root": self.root, "created_at": stamp(), "status": "PREPARING",
                   "target_identity": self.target_identity,
                   "files": [{k: v for k, v in f.items() if not k.endswith("_bytes")} for f in files],
                   "candidate": candidate, "structural_validation": "NOT_RUN"}
        # A kill while creating the first journal must not expose an operation
        # directory without its journal. No target write can precede publication.
        pending_path = f"{self.root}/preparing/{op}/journal.json"
        self.write_metadata(pending_path, journal)
        self.fault("initial_journal_prepared", 0)
        source_fd, source_name = self.parent(f"{self.root}/preparing/{op}")
        dest_fd, dest_name = self.parent(f"{self.root}/operations/{op}", create=True)
        try:
            os.rename(source_name, dest_name, src_dir_fd=source_fd, dst_dir_fd=dest_fd)
            os.fsync(dest_fd)
            os.fsync(source_fd)
        finally:
            os.close(source_fd)
            os.close(dest_fd)
        try:
            for i, f in enumerate(files):
                self.fault("prepare_image", i)
                for side in ("before", "after"):
                    data = f[side + "_bytes"]
                    if data is not None:
                        path = f"{self.root}/operations/{op}/{side}/{i}"
                        self.atomic(path, data, {"exists": False, "sha256": None})
                        self.a.require(self.identity(self.read(path)) == f[side], "prepared image mismatch")
            journal["status"] = "PREPARED"
            self.write_metadata(journal_path, journal)
            self.fault("prepared", 0)
            for path, identity in inputs.items():
                raw = self.planner.read(path, optional=True)
                current = self.planner.inputs[path] if "mode" in identity else self.identity(raw)
                self.a.require(current == identity, "STALE_PLAN before commit: " + path)
            for f in files:
                self.a.require(self.identity(self.read(f["path"])) == f["before"], "STALE_STATE before commit")
                self.a.require(self.mode_matches(f), "STALE_STATE file mode changed")
            journal["status"] = "COMMITTING"
            self.write_metadata(journal_path, journal)
            for i, f in enumerate(files):
                self.fault("before_commit", i)
                self.a.require(self.mode_matches(f), "file mode changed before commit")
                self.atomic(f["path"], f["after_bytes"], f["before"], f["mode"])
                self.fault("after_replace", i)
                journal["files"][i]["committed"] = True
                self.write_metadata(journal_path, journal)
            # Exact prepared-file equality proves structural values and foreign
            # data preservation checked in prepare. No compositor was invoked.
            for f in files:
                self.a.require(self.identity(self.read(f["path"])) == f["after"], "post-apply readback mismatch")
            journal.update(status="SUCCESS", structural_validation="PASS", finished_at=stamp())
            self.write_metadata(journal_path, journal)
            self.prune_images(journal)
            return {"result": "SUCCESS", "operation_id": op, "journal": journal_path,
                    "changed_files": [f["path"] for f in files if not f["path"].startswith(self.root + "/")],
                    "structural_validation": "PASS", "functional_validation": "NOT_RUN"}
        except Exception as exc:
            if journal["status"] == "SUCCESS":
                raise self.a.Invalid(f"operation {op} committed/validated; journal cleanup failed: {exc}; do not reapply blindly") from exc
            try:
                self.recover_one(journal_path, journal)
                raise self.a.Invalid(f"operation {op} failed: {exc}; RECOVERED pre-operation state") from exc
            except self.a.Invalid as recovery:
                if journal["status"] == "RECOVERED":
                    raise
                raise self.a.Invalid(f"operation {op} failed: {exc}; RECOVERY_REQUIRED: {recovery}") from exc

    def prune_images(self, journal):
        for i, f in enumerate(journal["files"]):
            for side in ("before", "after"):
                path = f"{self.root}/operations/{journal['id']}/{side}/{i}"
                current = self.read(path)
                if current is not None:
                    self.atomic(path, None, self.identity(current))

    def recover_one(self, path, journal):
        self.check_journal(journal, journal["id"])
        images = []
        for i, record in enumerate(journal["files"]):
            current = self.identity(self.read(record["path"]))
            self.a.require(current in (record["before"], record["after"]), "recovery refuses a third-party change: " + record["path"])
            self.a.require(self.mode_matches(record), "recovery refuses a file mode change: " + record["path"])
            before = self.read(f"{self.root}/operations/{journal['id']}/before/{i}")
            if current != record["before"]:
                self.a.require(self.identity(before) == record["before"], "missing/corrupt recovery preimage")
            images.append((record, before, current))
        journal["status"] = "RECOVERY_REQUIRED"
        self.write_metadata(path, journal)
        for record, before, current in reversed(images):
            if current != record["before"]:
                self.atomic(record["path"], before, current, record["mode"])
            record["restored"] = True
            self.write_metadata(path, journal)
        self.a.require(all(self.identity(self.read(r["path"])) == r["before"] for r in journal["files"]), "recovery incomplete")
        journal.update(status="RECOVERED", finished_at=stamp())
        self.write_metadata(path, journal)
        self.prune_images(journal)

    def recover(self):
        self.a.require(self.args.approve == "recover", "--approve recover required")
        recovered = []
        for path, journal in self.journals():
            if journal["status"] not in TERMINAL:
                self.recover_one(path, journal)
                recovered.append(journal["id"])
        return {"result": "RECOVERED" if recovered else "NO_CHANGE", "operations": recovered}

    def validate(self):
        self.clean()
        state, ledger = self.ledger()
        self.a.require(state is not None, "no managed application to validate")
        self.planner.args.state_root = self.root
        self.planner.applied_state(self.target, self.reference_values())
        mismatches, hashes = [], {}
        for resource, record in state["resources"].items():
            actual = self.values(resource, self.read(self.paths[resource]))
            hashes[self.paths[resource]] = {"current": self.identity(self.read(self.paths[resource])),
                                            "last_applied": ledger.get("applied_files", {}).get(self.paths[resource]),
                                            "foreign_changes_may_be_preserved": True}
            mismatches += [resource + ":" + key for key, value in record["values"].items() if actual.get(key, stored(None)) != value]
        return {"result": "FAIL" if mismatches else "PASS", "mismatches": mismatches,
                "structural_validation": "FAIL" if mismatches else "PASS", "functional_validation": "NOT_RUN",
                "candidate": ledger["candidate"], "examined_hashes": hashes}


def run(api, args, fault=None):
    op = Operations(api, args, fault)
    try:
        if args.command != "validate":
            op.acquire()
        result = getattr(op, args.command)()
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) if args.format == "json"
              else "HEARTCHY " + args.command.upper() + " — " + json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 3 if result["result"] in ("FAIL", "LOCAL_PRESERVED", "PARTIAL_ROLLBACK") else 0
    finally:
        if op.lock is not None:
            os.close(op.lock)
        if op.target_lock is not None:
            os.close(op.target_lock)
