"""Read-only planning over explicit synthetic targets; never an application API."""
import json
import re
from pathlib import Path
from types import SimpleNamespace


CONTRACTS = {
    "shell_intent": "omarchy-shell-json-v1",
    "shell_tokens": "omarchy-shell-toml-key-merge-v1",
    "hypr_module": "heartchy-lua-module-bytes-v1",
    "hypr_connection": "omarchy-lua-prefix-v1",
}
FILES = {
    "shell_intent": ["config/omarchy/shell.json"],
    "shell_tokens": ["config/omarchy/shell.toml"],
}
DECISIONS = ("NO_CHANGE", "MANAGED_CHANGE", "LOCAL_PRESERVED", "CONFLICT_PENDING",
             "REPLACEMENT_REQUESTED", "BLOCKED")


def present(value):
    return {"state": "present", "value": value}


def same(left, right):
    # JSON true must not compare equal to the number 1.
    if left.get("state") != right.get("state"):
        return False
    a, b = left.get("value"), right.get("value")
    return isinstance(a, bool) == isinstance(b, bool) and a == b


def decide(base, current, proposed, prefer=False, keep=False):
    """Return policy decisions without configuration IO or effects."""
    if same(current, proposed):
        return "NO_CHANGE", "ALREADY_PROPOSED", current
    if keep:
        return "LOCAL_PRESERVED", "EXPLICIT_KEEP_LOCAL", current
    if prefer:
        return "REPLACEMENT_REQUESTED", "EXPLICIT_HEARTCHY_PENDING_APPROVAL", proposed
    if base["state"] == "unmanaged":
        if current["state"] == "absent":
            return "MANAGED_CHANGE", "INITIAL_EXPLICIT_KEY_ADDITION", proposed
        return "LOCAL_PRESERVED", "FIRST_ADOPTION_HAS_NO_OWNERSHIP", current
    if same(current, base):
        return "MANAGED_CHANGE", "CURRENT_MATCHES_APPLIED_BASE", proposed
    if same(proposed, base):
        return "LOCAL_PRESERVED", "ONLY_LOCAL_CHANGED", current
    return "CONFLICT_PENDING", "BOTH_CHANGED_KEEP_CURRENT_PENDING_RESOLUTION", current


class Planner:
    def __init__(self, api, args):
        self.a = SimpleNamespace(**api)
        self.args = args
        self.inputs = {}
        self.binding = None
        self.target_helpers = {"__name__": "heartchy_target"}
        exec(compile(self.read("tools/heartchy-target.py"), "tools/heartchy-target.py", "exec"), self.target_helpers)
        self.contracts = CONTRACTS
        self.lua = {"__name__": "heartchy_lua_plan"}
        exec(compile(self.read("tools/heartchy-lua-plan.py"), "tools/heartchy-lua-plan.py", "exec"), self.lua)

    def location(self, raw, kind):
        self.a.require(".." not in Path(raw).parts and "\\" not in raw, "plan: parent escapes forbidden")
        path = Path(raw)
        if path.is_absolute():
            self.a.require(path.is_relative_to(self.a.ROOT), "plan: input must be inside this checkout")
            path = path.relative_to(self.a.ROOT)
        parts = self.a.relative_parts(path.as_posix())
        if getattr(self.a, "RUNTIME_MODE", False):
            valid = {"target": path.as_posix() == "target", "state": path.as_posix() == "managed",
                     "candidate": bool(re.fullmatch(r"candidates/[0-9a-f]{64}", path.as_posix())),
                     "previous plan": bool(re.fullmatch(r"plans/[0-9a-f]{64}\.json", path.as_posix()))}.get(kind, False)
            self.a.require(valid, "runtime: path outside explicit operation workspace")
            return path.as_posix()
        if kind == "candidate":
            valid = len(parts) == 2 and parts[0] == "build"
        elif kind == "target":
            valid = ((len(parts) == 3 and parts[:2] == ["build", "simulations"])
                     or (len(parts) == 3 and parts[:2] == ["build", "local-targets"])
                     or (len(parts) == 4 and parts[:3] == ["test", "fixtures", "planner"]))
        else:
            valid = len(parts) >= 2 and parts[0] == "build"
        self.a.require(valid, f"plan: unsupported {kind} location; see plan --help")
        return path.as_posix()

    def read(self, path, optional=False):
        physical = self.binding.physical(path) if self.binding else None
        data = (self.target_helpers["read"](self.a, physical, optional) if physical is not None
                else self.a.read_project(path, missing_ok=optional))
        self.inputs[path] = {"exists": data is not None,
                             "sha256": self.a.digest(data) if data is not None else None}
        if data is not None:
            actual = physical if physical is not None else self.a.source_path(path)
            self.inputs[path]["mode"] = actual.stat(follow_symlinks=False).st_mode & 0o777
        return data

    def configure_target(self, target):
        if target.startswith("build/local-targets/") or (getattr(self.a, "RUNTIME_MODE", False) and target == "target"):
            marker = self.a.parse_json(self.read(target + "/target.json"), "local target descriptor")
            self.binding = self.target_helpers["Binding"](self.a, target, marker, CONTRACTS)
            for relative, expected in self.target_helpers["LOADERS"].items():
                raw = self.read(target + "/runtime/" + relative)
                self.a.require(self.a.digest(raw) == expected, "INSTALLED_LOADER_CONTRACT_UNVERIFIED: " + relative)
            return {"schema_version": 1, "kind": "heartchy-simulated-target", "contracts": CONTRACTS}
        return None

    def candidate(self, directory):
        inventory = self.a.parse_json(self.read(directory + "/inventory.json"), "candidate inventory")
        self.a.require(isinstance(inventory, dict) and type(inventory.get("schema_version")) is int
                       and inventory["schema_version"] == 1
                       and inventory.get("kind") == "heartchy-local-candidate", "unsupported candidate inventory")
        files = inventory.get("files")
        self.a.require(isinstance(files, list), "candidate inventory files must be a list")
        allowed = set(self.a.SUPPORT) | {p for p, _ in self.a.SOURCES.values()}
        self.a.require(len(files) == len(allowed) and all(isinstance(f, dict) for f in files)
                       and {f.get("path") for f in files} == allowed, "candidate inventory outside managed payload")
        payload = {}
        for entry in files:
            data = self.read(directory + "/" + entry["path"])
            self.a.require(self.a.digest(data) == entry.get("sha256") and len(data) == entry.get("bytes")
                           and entry.get("mode") == "0644", f"candidate hash/size/mode mismatch: {entry['path']}")
            payload[entry["path"]] = data
        self.a.validate(reader=payload.__getitem__, development=False)
        manifest = self.a.parse_json(payload[self.a.MANIFEST], "candidate manifest")
        self.module_bytes = payload[self.a.SOURCES["hypr"][0]]
        values = {
            "hypr_module": {"content": self.lua["fingerprint"](self.module_bytes)},
            "hypr_connection": {"load": self.lua["fingerprint"](self.lua["LOAD_BLOCK"])},
            "shell_tokens": self.a.flat(self.a.parse_stock_toml(payload[self.a.SOURCES["shell_tokens"][0]])),
            "shell_intent": self.a.flat(self.a.parse_json(payload[self.a.SOURCES["shell_intent"][0]], "candidate intent")),
        }
        return manifest, values

    def selectors(self, arguments, values, resources):
        selected = set()
        for selector in arguments:
            resource, delimiter, key = selector.partition(":")
            if resource == "hypr" and not delimiter:
                for name, item in (("hypr_module", "content"), ("hypr_connection", "load")):
                    self.a.require(name in resources, "plan: hypr alias extends outside requested scope")
                    selected.add((name, item))
                continue
            self.a.require(resource in resources, f"plan: selector resource outside requested scope: {resource}")
            keys = [key] if delimiter else values[resource]
            for name in keys:
                self.a.require(name in values[resource], f"plan: selector is not managed: {selector}")
                selected.add((resource, name))
        return selected

    def applied_state(self, target, values):
        root = getattr(self.args, "state_root", None)
        if root:
            root = self.location(root, "state")
            self.a.require(re.fullmatch(r"build/state/[a-zA-Z0-9_-]+", root) or
                           (getattr(self.a, "RUNTIME_MODE", False) and root == "managed"), "invalid state root")
        raw = self.read(root + "/managed.json" if root else target + "/state.json", optional=True)
        if raw is None:
            return None
        state = self.a.parse_json(raw, "simulated managed state")
        self.a.require(isinstance(state, dict) and set(state) ==
                       {"schema_version", "kind", "successful", "application_id", "resources"}
                       and type(state["schema_version"]) is int and state["schema_version"] == 1
                       and state["kind"] == "heartchy-managed-state" and state["successful"] is True
                       and isinstance(state["application_id"], str) and bool(state["application_id"]),
                       "invalid/incomplete managed state; cannot assume first application")
        resources = state["resources"]
        self.a.require(isinstance(resources, dict) and set(resources) <= set(values), "state has unmanaged resources")
        for resource, record in resources.items():
            self.a.require(isinstance(record, dict) and set(record) in ({"contract", "values"}, {"contract", "values", "accepted"})
                           and record["contract"] == CONTRACTS[resource] and isinstance(record["values"], dict)
                           and set(record["values"]) <= set(values[resource]), "state contract or keys outside scope")
            accepted = record.get("accepted", [])
            self.a.require(isinstance(accepted, list) and all(isinstance(key, str) for key in accepted)
                           and len(accepted) == len(set(accepted)) and set(accepted) <= set(record["values"])
                           and (not accepted or resource in FILES), "state: invalid matching-state acceptance")
            for key, value in record["values"].items():
                self.a.require(isinstance(value, dict) and
                               (value == {"state": "absent"} or
                                (set(value) == {"state", "value"} and value["state"] == "present")),
                               "state: values must explicitly distinguish absence and presence")
                self.a.require(key not in accepted or value["state"] == "present", "state: accepted reference must exist")
                if value["state"] == "present":
                    self.check_type(value["value"], values[resource][key])
                    if resource.startswith("hypr_"):
                        identity = value["value"]
                        self.a.require(re.fullmatch(r"[0-9a-f]{64}", identity["sha256"])
                                       and type(identity["bytes"]) is int and identity["bytes"] >= 0,
                                       "state: invalid Lua byte fingerprint")
        return state

    def check_type(self, value, proposed):
        numeric = type(proposed) in (int, float)
        self.a.require((numeric and type(value) in (int, float)) or type(value) is type(proposed),
                       "managed value type is incompatible")
        if isinstance(proposed, dict):
            self.a.require(set(value) == set(proposed), "managed structured value has unknown fields")
            for key in proposed:
                self.check_type(value[key], proposed[key])
        self.a.json_bytes(value)  # Reject non-finite numbers, including 1e999.

    def current(self, target, resource, values):
        raw = [self.read(target + "/" + path, optional=True) for path in FILES[resource]]
        if resource == "shell_intent":
            self.a.require(raw[0] is not None, "JSON_SEED_REQUIRED: recipient stock seed is unavailable; no full-file replacement")
            document = self.a.parse_json(raw[0], "recipient shell.json")
            self.a.require(isinstance(document, dict) and type(document.get("version")) is int
                           and document["version"] == 1, "JSON_CONTRACT_INCOMPATIBLE: requires version 1")
            bar = document.get("bar", {})
            self.a.require(isinstance(bar, dict) and bar.get("id", "omarchy.bar") == "omarchy.bar",
                           "BAR_CONTRACT_INCOMPATIBLE: stock bar required")
            current = {"bar.transparent": present(bar["transparent"]) if "transparent" in bar else {"state": "absent"}}
        else:
            tokens = self.a.recipient_toml_values(raw[0] or b"")
            current = {key: present(tokens[key]) if key in tokens else {"state": "absent"} for key in values}
        for key, record in current.items():
            if record["state"] == "present":
                self.check_type(record["value"], values[key])
        return current

    def run(self):
        args = self.args
        candidate = self.location(args.candidate, "candidate")
        target = self.location(args.target, "target")
        self.args_target = target
        previous_path = self.location(args.recheck, "previous plan") if args.recheck else None
        plan = {"schema_version": 1, "kind": "heartchy-change-plan", "policy": "HEARTCHY-ARQ-002",
                "mode": "simulation", "target": target, "candidate": candidate, "phase": "unknown",
                "application_authorized": False, "writes_performed": False, "entries": [], "blocks": [],
                "inputs": self.inputs, "freshness": {"status": "NOT_RECHECKED"}}
        plan["state_root"] = self.location(args.state_root, "state") if getattr(args, "state_root", None) else None
        errors = (self.a.Invalid, ValueError, TypeError, KeyError, AttributeError)
        for path in ("tools/heartchy-dev", "tools/heartchy-plan.py", "tools/lua-contract.lua"):
            self.read(path)
        if getattr(args, "state_root", None):
            self.read("tools/heartchy-apply.py")
            self.read(plan["state_root"] + "/ledger.json", optional=True)
        try:
            local_marker = self.configure_target(target)
            plan["mode"] = "local-descriptor" if local_marker else "simulation"
            _, values = self.candidate(candidate)
        except errors as exc:
            plan["blocks"].append({"reason": "CANDIDATE_INVALID", "detail": str(exc)})
            return self.finish(plan)
        requested_resources = set(args.resource or values)
        if "hypr" in requested_resources:
            requested_resources.remove("hypr")
            requested_resources.update(("hypr_module", "hypr_connection"))
        resources = sorted(requested_resources)
        prefer = self.selectors(args.prefer_heartchy, values, resources)
        keep = self.selectors(args.keep_local, values, resources)
        self.a.require(not prefer & keep, "plan: contradictory selectors for the same key")
        plan["selection"] = {"resources": resources,
                             "prefer_heartchy": sorted(f"{r}:{k}" for r, k in prefer),
                             "keep_local": sorted(f"{r}:{k}" for r, k in keep)}
        marker_error = None
        marker = {}
        try:
            marker = local_marker or self.a.parse_json(self.read(target + "/target.json"), "simulated target marker")
            self.a.require(isinstance(marker, dict) and set(marker) == {"schema_version", "kind", "contracts"}
                           and type(marker["schema_version"]) is int and marker["schema_version"] == 1
                           and marker["kind"] == "heartchy-simulated-target"
                           and isinstance(marker["contracts"], dict), "explicit simulated target marker required")
        except errors as exc:
            marker_error = str(exc)
        state = None
        state_error = None
        if not marker_error:
            try:
                state = self.applied_state(target, values)
                plan["phase"] = "first_application" if state is None else "subsequent_application"
            except errors as exc:
                state_error = str(exc)
        for resource in resources:
            if resource.startswith("hypr_"):
                continue
            block = marker_error or state_error
            current = {}
            if not block:
                try:
                    self.a.require(marker["contracts"].get(resource) == CONTRACTS[resource], "UNSUPPORTED_TARGET_CONTRACT")
                    current = self.current(target, resource, values[resource])
                except errors as exc:
                    block = str(exc)
            base_record = state["resources"].get(resource, {}) if state else {}
            base_values = base_record.get("values", {})
            for key, value in sorted(values[resource].items()):
                base = base_values.get(key, {"state": "unmanaged"}) if not (marker_error or state_error) else {"state": "unknown"}
                actual = current.get(key, {"state": "unknown"})
                proposal = present(value)
                requested = (resource, key) in prefer
                if block:
                    decision, reason, effective = "BLOCKED", block, actual
                else:
                    decision, reason, effective = decide(base, actual, proposal, requested, (resource, key) in keep)
                accept = decision == "NO_CHANGE" and base["state"] == "unmanaged" and same(actual, proposal) and (resource, key) not in keep
                if accept:
                    reason = "ALREADY_MATCHES"
                plan["entries"].append({"resource": resource, "key": key, "base": base,
                                        "current": actual, "proposed": proposal, "decision": decision,
                                        "reason": reason, "planned": effective, "replacement_selected": requested,
                                        "base_origin": "matching-preexisting" if key in base_record.get("accepted", []) else
                                                       "heartchy-written" if base["state"] in ("present", "absent") else "unmanaged",
                                        "state_operation": "accept-matching-reference" if accept else "none",
                                        "approval_required_at_application": decision == "REPLACEMENT_REQUESTED" or accept,
                                        "backup_required_at_application": decision in ("MANAGED_CHANGE", "REPLACEMENT_REQUESTED")})
        if any(resource.startswith("hypr_") for resource in resources):
            plan["entries"].extend(self.lua["plan"](self, values, state, marker, resources, prefer, keep,
                                                    marker_error or state_error, decide))
        if previous_path:
            # A saved plan is evidence, never authority. Compare all examined
            # bytes, missing-file sentinels and the exact requested selection.
            previous_data = self.a.read_project(previous_path)
            previous = self.a.parse_json(previous_data, "previous plan")
            self.a.require(isinstance(previous, dict) and previous.get("kind") == "heartchy-change-plan"
                           and previous.get("schema_version") == 1 and isinstance(previous.get("inputs"), dict),
                           "invalid previous plan")
            changed = sorted(p for p in set(previous["inputs"]) | set(self.inputs)
                             if previous["inputs"].get(p) != self.inputs.get(p))
            same_context = all(previous.get(k) == plan.get(k) for k in ("target", "candidate", "selection", "policy", "state_root"))
            stale = bool(changed) or not same_context
            plan["freshness"] = {"status": "STALE" if stale else "MATCH", "changed_inputs": changed,
                                 "same_context": same_context,
                                 "previous_plan_sha256": self.a.digest(previous_data)}
            if stale:
                plan["blocks"].append({"reason": "STALE_PLAN", "detail": "Regenerate and review; previous approval cannot transfer."})
                for row in plan["entries"]:
                    row.update(decision="BLOCKED", reason="STALE_PLAN", planned=row["current"],
                               approval_required_at_application=False, backup_required_at_application=False)
                    if "state_operation" in row:
                        row["state_operation"] = "none"
                    if "operation" in row:
                        row["operation"] = "none"
                        row.pop("insertion", None)
                        for dependency in row.get("depends_on", []):
                            dependency.update(satisfied=False, decision="BLOCKED", reason="STALE_PLAN", approval_pending=False)
        return self.finish(plan)

    def finish(self, plan):
        plan["summary"] = {name: sum(row["decision"] == name for row in plan["entries"]) for name in DECISIONS}
        plan["blocked"] = bool(plan["blocks"]) or bool(plan["summary"]["BLOCKED"])
        plan["pending_conflicts"] = plan["summary"]["CONFLICT_PENDING"]
        return plan


def render(plan):
    lines = ["HEARTCHY PLAN — " + plan["mode"].upper() + " — NO WRITES — NOT AN APPROVAL",
             f"Target: {plan['target']} | Candidate: {plan['candidate']} | Phase: {plan['phase']}"]
    for row in plan["entries"]:
        values = " | ".join(f"{name}={json.dumps(row[name], ensure_ascii=False, sort_keys=True)}"
                            for name in ("base", "current", "proposed", "planned"))
        lines.append(f"{row['resource']}:{row['key']} — {row['decision']} ({row['reason']})\n  {values}")
        if "state_operation" in row:
            detail = " (acceptance metadata only; no configuration write)" if row["state_operation"] == "accept-matching-reference" else ""
            lines.append(f"  base_origin={row['base_origin']} state_operation={row['state_operation']}{detail}")
        if "file" in row:
            lines.append(f"  file={row['file']} operation={row['operation']} functional_validation=NOT_RUN")
            if row.get("depends_on"):
                lines.append("  depends_on=" + json.dumps(row["depends_on"], sort_keys=True))
            if row.get("warnings"):
                lines.append("  warnings=" + json.dumps(row["warnings"]))
            delta = row["difference"]
            if delta["format"] == "unified" and delta["text"]:
                lines.append("  Proposal diff (not permission to apply):\n" + delta["text"])
            elif delta["format"] != "unified":
                lines.append("  Proposal diff: " + json.dumps(delta))
    lines += ["BLOCK: " + json.dumps(block, ensure_ascii=False) for block in plan["blocks"]]
    lines.append("Summary: " + json.dumps(plan["summary"], sort_keys=True))
    lines.append("Freshness: " + json.dumps(plan["freshness"], sort_keys=True))
    lines.append("Examined inputs (SHA-256; absent means known missing file):")
    lines += [f"  {path}: {record['sha256'] or 'ABSENT'}" for path, record in sorted(plan["inputs"].items())]
    lines.append("Future application must recheck hashes, show exact changes, obtain approval and prepare recoverable backups.")
    return "\n".join(lines)


def run(api, args):
    plan = Planner(api, args).run()
    print(json.dumps(plan, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
          if args.format == "json" else render(plan))
    return 3 if plan["blocked"] or plan["pending_conflicts"] else 0
