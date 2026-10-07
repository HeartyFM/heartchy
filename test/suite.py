"""Behavior tests; runs only through test/all's isolated namespace."""
import sys

sys.dont_write_bytecode = True

import hashlib
import argparse
import json
import os
import re
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import runpy
import pty
import fcntl
import termios
import struct
import select
import time
import signal

ROOT = Path(__file__).resolve().parents[1]
SANDBOX = Path("/sandbox")
ENV = {"PATH": "/usr/bin:/bin", "LC_ALL": "C.UTF-8", "TMPDIR": "/sandbox"}
LUA_LOAD = b'-- BEGIN HEARTCHY: hypr.heartchy v1\nrequire("hypr.heartchy")\n-- END HEARTCHY: hypr.heartchy v1\n'

# Installed programs that mutate the desktop must never be invoked even in
# this filesystem/network sandbox. The hook checks before Popen executes.
AUDIT_BOOTSTRAP = r'''
import sys, os, runpy, json
sys.dont_write_bytecode = True
seen = []
def guard(event, args):
    if event == "subprocess.Popen":
        program, argv = args[0], args[1]
        seen.append(argv)
        if program not in ("/usr/bin/lua", "/usr/bin/git"):
            raise PermissionError("forbidden process: " + str(program))
        if program == "/usr/bin/lua" and (len(argv) != 2 or not argv[1].endswith("/tools/lua-contract.lua")):
            raise PermissionError("unexpected Lua invocation")
        if program == "/usr/bin/git" and not any(x in argv for x in ("status", "rev-parse")):
            raise PermissionError("unexpected Git operation")
sys.addaudithook(guard)
sys.argv = sys.argv[1:]
code = 0
try:
    runpy.run_path(sys.argv[0], run_name="__main__")
except SystemExit as exc:
    code = exc.code or 0
finally:
    print("HEARTCHY_EXEC_AUDIT=" + json.dumps(seen), file=sys.stderr)
sys.exit(code)
'''

# The prototype permits only native UI children; no file mutation or network IO.
MOCKUP_AUDIT = r'''
import sys, os, runpy, stat, re
sys.dont_write_bytecode = True
def guard(event, args):
    if event in ("subprocess.Popen", "os.posix_spawn"):
        if event == "subprocess.Popen":
            program, argv, cwd, env = args
        else:
            program, argv, env = args
        if program == "/usr/bin/gum":
            if argv[1] not in ("style", "choose", "confirm", "spin"):
                raise PermissionError("non-UI Gum command")
            if argv[1] == "spin" and argv[-3:] != ["--", "/usr/bin/sleep", "8.0"]:
                raise PermissionError("non-simulation command")
        elif program == "/usr/bin/ttfx":
            if argv != [program, "--version"]:
                prefix = [program, "--parity-dump", "--max-frames", "1200", "--seed", "7", "--no-color",
                          "--ignore-terminal-dimensions", "--canvas-width", "97", "--canvas-height", argv[11] if len(argv)>11 else "", "--anchor-text", "nw"]
                suffixes = {
                    "slice": ["--movement-speed", "1.5"],
                    "middleout": ["--center-movement-speed", "6", "--full-movement-speed", "1.2"],
                    "beams": ["--beam-delay", "1", "--beam-row-speed-range", "400-400", "--beam-column-speed-range", "100-100",
                              "--beam-gradient-frames", "1", "--beam-gradient-steps", "1", "--beam-gradient-stops", "ffffff",
                              "--final-gradient-frames", "1", "--final-gradient-steps", "1", "--final-gradient-stops", "ffffff", "--final-wipe-speed", "100"],
                    "decrypt": ["--typing-speed", "1000"]}
                if argv[:14] != prefix or argv[11] not in ("9", "10") or len(argv) < 15 or argv[14] not in suffixes or argv[15:] != suffixes[argv[14]]:
                    raise PermissionError("non-scoped ttfx invocation")
        elif program == "/usr/bin/fzf":
            if any(a.startswith(("--preview", "--listen", "--history")) for a in argv):
                raise PermissionError("Fzf external integration forbidden")
            if not any(a.startswith("--filter=") for a in argv):
                if "--bind" not in argv or not re.fullmatch(r"load:pos\([1-6]\)\+offset-middle,focus:offset-middle,resize:print\(RESIZE\)\+accept", argv[argv.index("--bind") + 1]):
                    raise PermissionError("Fzf command binding forbidden")
        else:
            raise PermissionError("prototype child forbidden: " + str(program))
        colors = {"FOREGROUND", "BACKGROUND", "BORDER_FOREGROUND", "BORDER_BACKGROUND"}
        safe_gum = re.compile(r"GUM_(CONFIRM_(PROMPT|SELECTED|UNSELECTED)|CHOOSE_(CURSOR|HEADER|ITEM|SELECTED)|SPIN_(SPINNER|TITLE))_(FOREGROUND|BACKGROUND)")
        if env.get("HOME") != "/nonexistent" or any(k.startswith("FZF_") for k in env):
            raise PermissionError("user tool defaults leaked")
        for k,v in env.items():
            if k in colors or k.startswith("GUM_"):
                if k not in colors and not safe_gum.fullmatch(k):
                    raise PermissionError("unexpected Gum default")
                if v != "" and not re.fullmatch(r"#[0-9a-fA-F]{6}|[0-9]{1,3}",v):
                    raise PermissionError("non-color theme value")
    if event in ("os.system", "os.exec", "socket.__new__",
                 "os.mkdir", "os.remove", "os.rename", "os.chmod"):
        raise PermissionError("prototype effect forbidden: " + event)
    if event == "open":
        path, mode, flags = args
        if (mode and any(c in mode for c in "wax+")) or flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC):
            # Native selector input uses Popen's anonymous stdin pipe, not a file.
            if not (isinstance(path, int) and stat.S_ISFIFO(os.fstat(path).st_mode)):
                raise PermissionError("prototype write forbidden: " + str(path))
        if isinstance(path, str) and path.startswith(os.environ["HOME"] + "/") and path not in {
                os.environ["HOME"] + "/.local/state/omarchy/current/theme/gum_env.lua",
                os.environ["HOME"] + "/.local/state/omarchy/current/theme/alacritty.toml",
                os.environ["HOME"] + "/.local/state/omarchy/current/theme/colors.toml"}:
            raise PermissionError("prototype HOME read forbidden")
sys.addaudithook(guard)
sys.argv = sys.argv[1:]
runpy.run_path(sys.argv[0], run_name="__main__")
'''


def sha(data):
    return hashlib.sha256(data).hexdigest()


def reply_palette_queries(master, data):
    # PTYs are not terminal emulators. Explicitly model Alacritty OSC 4 replies,
    # including preexisting non-default colors that the app must restore.
    for index in re.findall(rb"\x1b]4;([0-9]+);\?\x1b\\", data):
        os.write(master, b"\x1b]4;" + index + b";rgb:1111/2222/3333\x1b\\")


def read_mockup_pty(master):
    data = os.read(master, 65536)
    reply_palette_queries(master, data)
    return data


def tree(path, excluded=()):
    return {p.relative_to(path).as_posix(): (sha(p.read_bytes()), p.stat().st_mode & 0o777)
            for p in sorted(path.rglob("*")) if p.is_file() and not p.is_symlink()
            and not any(p.is_relative_to(x) for x in excluded)}


UpdatesMixin = runpy.run_path(str(ROOT / "test/update_tests.py"))["UpdatesMixin"]


class CoreTests(UpdatesMixin, unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="case-", dir=SANDBOX)
        self.area = Path(self.temporary.name)
        self.repo = self.area / "heartchy"
        shutil.copytree(ROOT, self.repo, ignore=shutil.ignore_patterns(".git", "build", "__pycache__"))

    def tearDown(self):
        self.temporary.cleanup()

    def cli(self, *arguments, cwd=None):
        return subprocess.run(["/usr/bin/python3", "-I", "-B", "-c", AUDIT_BOOTSTRAP,
                               str(self.repo / "tools/heartchy-dev"), *arguments],
                              cwd=cwd or self.area, env=ENV, capture_output=True, text=True, timeout=15)

    def expect_ok(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def expect_bad(self, result, diagnostic):
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(diagnostic, result.stdout + result.stderr)

    def rehash(self, relative):
        path = self.repo / "core/manifest.json"
        data = json.loads(path.read_text())
        for entry in data["resources"]:
            if entry["source"] == relative:
                entry["sha256"] = sha((self.repo / relative).read_bytes())
        path.write_text(json.dumps(data, indent=2) + "\n")

    def test_check_help_invalid_arguments_and_foreign_cwd(self):
        before = tree(self.repo)
        result = self.cli("check", cwd=Path("/"))
        self.expect_ok(result)
        self.assertIn("9 candidates", result.stdout)
        for args in [("--help",), ("check", "--help"), ("stage", "--help"), ("plan", "--help")]:
            result = self.cli(*args)
            self.expect_ok(result)
            self.assertIn("HEARTCHY_EXEC_AUDIT=[]", result.stderr)
        for args in [(), ("install",), ("update",), ("check", "--apply"), ("stage",), ("stage", "--output", "build/x", "--apply"), ("plan",), ("plan", "--force")]:
            result = self.cli(*args)
            self.assertEqual(result.returncode, 2)
            self.assertIn("HEARTCHY_EXEC_AUDIT=[]", result.stderr)
        self.assertEqual(before, tree(self.repo))

    def test_invalid_formats_missing_resources_and_hashes(self):
        cases = [("core/shell/settings-intent.json", '{"bar":'),
                 ("core/shell/settings-intent.json", '{"bar":{"transparent":true,"transparent":false}}'),
                 ("core/shell/cristal.toml", "[menu\nbackground-alpha=0.75"),
                 ("core/hypr/heartchy.lua", "hl.config({")]
        for path, broken in cases:
            with self.subTest(path=path, broken=broken):
                original = (self.repo / path).read_bytes()
                (self.repo / path).write_text(broken)
                self.rehash(path)
                self.expect_bad(self.cli("check"), "FAIL check")
                (self.repo / path).write_bytes(original)
                self.rehash(path)
        target = self.repo / "core/shell/cristal.toml"
        original = target.read_bytes()
        target.unlink()
        self.expect_bad(self.cli("check"), "cannot safely read")
        target.write_bytes(original + b"# changed\n")
        self.expect_bad(self.cli("check"), "SHA-256 mismatch")
        self.assertFalse((self.repo / "build").exists())

    def test_manifest_inventory_scope_and_references(self):
        path = self.repo / "core/manifest.json"
        original = path.read_bytes()
        variants = []
        d = json.loads(original); d["resources"][0]["source"] = "../outside.lua"; variants.append(d)
        d = json.loads(original); d["references"][0] = "/etc/passwd"; variants.append(d)
        d = json.loads(original); d["candidates"].pop(); variants.append(d)
        d = json.loads(original); d["resources"][1]["managed"].append("font.base-size"); variants.append(d)
        d = json.loads(original); d["execute"] = "omarchy update"; variants.append(d)
        d = json.loads(original); d["schema_version"] = True; variants.append(d)
        for variant in variants:
            path.write_text(json.dumps(variant))
            self.expect_bad(self.cli("check"), "manifest")
        path.write_bytes(original)
        doc = self.repo / "docs/development.md"
        doc.write_text(doc.read_text() + "\n[escape](../../outside.md)\n")
        self.expect_bad(self.cli("check"), "reference outside repo")

    def test_candidates_and_excluded_personalizations(self):
        mutations = [
            ("core/hypr/heartchy.lua", lambda s: s.replace("size = 6", "size = 7")),
            ("core/hypr/heartchy.lua", lambda s: s.replace("border_size = 1", "border_size = true")),
            ("core/hypr/heartchy.lua", lambda s: s + '\nhl.config({cursor={no_hardware_cursors=1}})\n'),
            ("core/hypr/heartchy.lua", lambda s: s + '\nhl.config({general={layout="scrolling"}})\n'),
            ("core/hypr/heartchy.lua", lambda s: s.replace("slidevert", "slide")),
            ("core/hypr/heartchy.lua", lambda s: s.replace("blur_popups = true", "blur_popups = 1")),
            ("core/hypr/heartchy.lua", lambda s: s.replace("enabled = true", "enabled = 1")),
            ("core/shell/cristal.toml", lambda s: s + "\n[font]\nbase-size = 11\n"),
            ("core/shell/cristal.toml", lambda s: s + "\n[diego-panels]\nbackground-alpha=0.5\n"),
            ("core/shell/cristal.toml", lambda s: s + "\n[glass]\nreflection-alpha=0\n"),
            ("core/shell/cristal.toml", lambda s: s.replace('selected-background = "accent"', 'selected-background = "#ffffff"')),
            ("core/shell/cristal.toml", lambda s: s.replace("#b8b8b8", "#ff0000")),
            ("core/shell/cristal.toml", lambda s: s.replace("background-alpha = 0.70", "background-alpha = 7e-1")),
            ("core/shell/cristal.toml", lambda s: s.replace("[controls]", '["controls"]')),
            ("core/shell/cristal.toml", lambda s: s.replace("normal-fill-alpha =", '"normal-fill-alpha" =')),
            ("core/shell/settings-intent.json", lambda s: '{"bar":{"transparent":true,"layout":{"left":[{"id":"external.widget"}]}}}'),
            ("core/shell/settings-intent.json", lambda s: '{"bar":{"transparent":true},"idle":{"lock":300}}'),
            ("core/shell/settings-intent.json", lambda s: '{"bar":{"transparent":1}}'),
        ]
        for path, mutate in mutations:
            with self.subTest(path=path):
                original = (self.repo / path).read_text()
                (self.repo / path).write_text(mutate(original)); self.rehash(path)
                self.expect_bad(self.cli("check"), "FAIL check")
                (self.repo / path).write_text(original); self.rehash(path)
        self.expect_ok(self.cli("check"))

    def test_lua_source_has_no_process_or_file_capabilities(self):
        path = self.repo / "core/hypr/heartchy.lua"
        original = path.read_text()
        for addition in ['os.execute("systemctl --user restart example")',
                         'io.open("/sandbox/forbidden-write", "w")',
                         'require("hypr.unknown")', 'while true do end']:
            path.write_text(original + "\n" + addition + "\n"); self.rehash("core/hypr/heartchy.lua")
            result = self.cli("check")
            self.expect_bad(result, "Lua inspection failed")
        self.assertFalse(Path("/sandbox/forbidden-write").exists())

    def test_staging_reproducible_inventory_and_preservation(self):
        before = tree(self.repo)
        self.expect_ok(self.cli("stage", "--output", "build/first"))
        self.expect_ok(self.cli("stage", "--output", str(self.repo / "build/second"), cwd=Path("/")))
        first, second = self.repo / "build/first", self.repo / "build/second"
        self.assertEqual(tree(first, [first / "local.json"]), tree(second, [second / "local.json"]))
        inventory = json.loads((first / "inventory.json").read_text())
        recorded = {r["path"] for r in inventory["files"]}
        self.assertEqual(recorded, set(tree(first)) - {"local.json", "inventory.json"})
        for entry in inventory["files"]:
            data = (first / entry["path"]).read_bytes()
            self.assertEqual(sha(data), entry["sha256"])
            self.assertEqual(len(data), entry["bytes"])
            self.assertEqual((first / entry["path"]).stat().st_mode & 0o777, int(entry["mode"], 8))
        self.assertFalse(any(p.startswith("test/") or p.startswith("tools/") for p in recorded))
        # Candidate-facing contracts must not acquire links to development-only
        # documents that are absent from the deliberately small stage payload.
        for relative in ("docs/architecture.md", "docs/upstream.md"):
            document = first / relative
            for target in re.findall(r"\]\(([^\s)]+)\)", document.read_text()):
                if target.startswith(("http://", "https://", "#")):
                    continue
                linked = (document.parent / target.split("#", 1)[0]).resolve()
                self.assertTrue(linked.is_relative_to(first) and linked.is_file(), (relative, target))
        self.assertEqual(before, tree(self.repo, [self.repo / "build"]))
        local = json.loads((first / "local.json").read_text())
        self.assertIsNone(local["git"]["commit"])
        self.assertEqual(local["git"]["worktree"], "not-a-git-checkout")
        self.assertFalse(local["installed"] or local["published"] or local["git"]["release"])

    def test_staging_rejects_escapes_symlinks_and_existing_content(self):
        for target in ["../escape", "build/../escape", "build/nested/out", "/etc/heartchy",
                       "/home/example/.config/omarchy", str(self.area / "escape"), "build/."]:
            self.expect_bad(self.cli("stage", "--output", target), "output")
        build = self.repo / "build"; build.mkdir()
        existing = build / "existing"; existing.mkdir(); (existing / "mine").write_text("local preference")
        self.expect_bad(self.cli("stage", "--output", "build/existing"), "never overwritten")
        self.assertEqual((existing / "mine").read_text(), "local preference")
        outside = self.area / "outside"; outside.mkdir(); (outside / "sentinel").write_text("unchanged")
        (build / "link").symlink_to(outside, target_is_directory=True)
        self.expect_bad(self.cli("stage", "--output", "build/link"), "never overwritten")
        self.assertEqual(list(outside.iterdir()), [outside / "sentinel"])
        shutil.rmtree(build)
        build.symlink_to(outside, target_is_directory=True)
        self.expect_bad(self.cli("stage", "--output", "build/new"), "stage refused")
        self.assertEqual(list(outside.iterdir()), [outside / "sentinel"])

    def test_source_symlinks_and_changed_stock_fixture_rejected(self):
        source = self.repo / "core/shell/cristal.toml"
        original = source.read_bytes()
        outside = self.area / "outside.toml"; outside.write_bytes(original)
        source.unlink(); source.symlink_to(outside)
        self.expect_bad(self.cli("check"), "cannot safely read")
        source.unlink(); source.write_bytes(original)
        fixture = self.repo / "test/fixtures/omarchy/window-helper.lua"
        fixture.write_text(fixture.read_text() + "\n-- unexpected edit\n")
        self.expect_bad(self.cli("check"), "fixture changed")

    def test_lua_loading_cache_and_registration_model(self):
        result = subprocess.run(["/usr/bin/lua", str(self.repo / "test/lua-loading.lua"), str(self.repo)],
                                env=ENV, capture_output=True, text=True, timeout=10)
        self.expect_ok(result)
        self.assertIn("anonymous accumulation", result.stdout)

    def test_no_outside_writes_or_mutator_invocations(self):
        before = tree(SANDBOX)
        result = self.cli("stage", "--output", "build/audited")
        self.expect_ok(result)
        audit = json.loads(result.stderr.split("HEARTCHY_EXEC_AUDIT=", 1)[1])
        self.assertEqual([Path(command[0]).name for command in audit], ["lua"])
        after = tree(SANDBOX, [self.repo / "build/audited"])
        self.assertEqual(before, after)
        for key in ("WAYLAND_DISPLAY", "DISPLAY", "DBUS_SESSION_BUS_ADDRESS", "HYPRLAND_INSTANCE_SIGNATURE", "XDG_RUNTIME_DIR"):
            self.assertNotIn(key, os.environ)
        self.assertEqual(list(Path("/run").iterdir()), [])
        self.assertEqual(list(Path("/home").iterdir()), [])
        self.assertEqual([name for _, name in socket.if_nameindex()], ["lo"])
        # Prove the execution guard itself blocks a harmless mutator stub.
        stub = self.area / "systemctl"; stub.write_text('#!/bin/sh\nexit 99\n'); stub.chmod(0o755)
        tool = self.repo / "tools/heartchy-dev"
        tool.write_text('import subprocess\nsubprocess.run([' + repr(str(stub)) + '])\n')
        result = self.cli("check")
        self.expect_bad(result, "forbidden process")
        self.assertNotEqual(result.returncode, 99)

    @unittest.skipIf(os.environ.get("HEARTCHY_PORTABLE_CHILD") == "1", "SKIP: recursion guard; outer suite tests portability")
    def test_check_tests_stage_from_independent_temporary_copy(self):
        self.assertFalse((self.repo / ".git").exists())
        self.expect_ok(self.cli("check"))
        self.expect_ok(self.cli("stage", "--output", "build/portable"))
        result = subprocess.run([str(self.repo / "test/all")], cwd=Path("/"),
                                env={**ENV, "HEARTCHY_PORTABLE_CHILD": "1"},
                                capture_output=True, text=True, timeout=180)
        self.expect_ok(result)
        self.assertIn("FAIL=0", result.stdout)
        self.assertIn("PASS test_staging_reproducible_inventory_and_preservation", result.stdout)
        self.assertIn("PASS test_plan_conflict_resolution_is_explicit_and_limited", result.stdout)
        self.assertIn("PASS test_lua_plan_byte_lifecycle_and_dependency", result.stdout)
        self.assertIn("PASS test_feature_scaffold_scope_and_portability", result.stdout)

    def prepare_planner(self):
        self.expect_ok(self.cli("stage", "--output", "build/planner-candidate"))

    def plan(self, fixture, *options, resources=("shell_tokens", "shell_intent")):
        args = ["plan", "--candidate", "build/planner-candidate", "--target",
                "test/fixtures/planner/" + fixture, "--format", "json"]
        for resource in resources:
            args += ["--resource", resource]
        result = self.cli(*args, *options, cwd=Path("/"))
        self.assertIn(result.returncode, (0, 3), result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(result.returncode, 3 if data["blocked"] or data["pending_conflicts"] else 0)
        return data, result

    def plan_row(self, plan, key="menu.background-alpha", resource="shell_tokens"):
        return next(row for row in plan["entries"] if row["key"] == key and row["resource"] == resource)

    def test_plan_first_application_has_no_assumed_ownership(self):
        self.prepare_planner()
        plan, result = self.plan("first")
        row = self.plan_row(plan)
        self.assertEqual(plan["phase"], "first_application")
        self.assertEqual(row["base"], {"state": "unmanaged"})
        self.assertEqual(row["decision"], "LOCAL_PRESERVED")
        self.assertEqual(row["planned"]["value"], .42)
        absent = self.plan_row(plan, "menu.scrim-alpha")
        self.assertEqual(absent["current"], {"state": "absent"})
        self.assertEqual(absent["reason"], "INITIAL_EXPLICIT_KEY_ADDITION")
        self.assertIn("state.json", " ".join(plan["inputs"]))
        self.assertFalse(plan["inputs"]["test/fixtures/planner/first/state.json"]["exists"])
        self.assertNotIn("SYNTHETIC_UNMANAGED", result.stdout)
        plan, _ = self.plan("first", "--prefer-heartchy", "shell_intent:bar.transparent")
        self.assertEqual(self.plan_row(plan, "bar.transparent", "shell_intent")["decision"], "REPLACEMENT_REQUESTED")
        self.assertEqual(self.plan_row(plan)["decision"], "LOCAL_PRESERVED")
        path = self.repo / "test/fixtures/planner/first/config/omarchy/shell.toml"
        path.unlink()
        absent, _ = self.plan("first", resources=("shell_tokens",))
        self.assertTrue(all(row["reason"] == "INITIAL_EXPLICIT_KEY_ADDITION" for row in absent["entries"]))
        self.assertFalse(absent["inputs"][path.relative_to(self.repo).as_posix()]["exists"])
        self.assertFalse(path.exists())

    def test_plan_three_way_managed_local_and_already_equal(self):
        self.prepare_planner()
        for name, decision, planned in [("managed", "MANAGED_CHANGE", .75),
                                       ("local", "LOCAL_PRESERVED", .42), ("same", "NO_CHANGE", .75)]:
            with self.subTest(name=name):
                plan, _ = self.plan(name)
                row = self.plan_row(plan)
                self.assertEqual(plan["phase"], "subsequent_application")
                self.assertEqual(row["decision"], decision)
                self.assertEqual(row["planned"]["value"], planned)
                self.assertFalse(plan["application_authorized"])
        # Removing a managed preference is a local change, not permission to restore it.
        local = self.repo / "test/fixtures/planner/local/config/omarchy/shell.toml"
        local.write_text('[personal]\nnote="unchanged"\n')
        plan, _ = self.plan("local")
        self.assertEqual(self.plan_row(plan)["decision"], "LOCAL_PRESERVED")
        self.assertEqual(self.plan_row(plan)["planned"], {"state": "absent"})

    def test_plan_conflict_resolution_is_explicit_and_limited(self):
        self.prepare_planner()
        plan, _ = self.plan("conflict")
        self.assertEqual(self.plan_row(plan)["decision"], "CONFLICT_PENDING")
        self.assertEqual(self.plan_row(plan)["planned"]["value"], .60)
        kept, _ = self.plan("conflict", "--keep-local", "shell_tokens:menu.background-alpha")
        self.assertEqual(self.plan_row(kept)["decision"], "LOCAL_PRESERVED")
        self.assertEqual(self.plan_row(kept)["reason"], "EXPLICIT_KEEP_LOCAL")
        chosen, _ = self.plan("conflict", "--prefer-heartchy", "shell_tokens:menu.background-alpha")
        row = self.plan_row(chosen)
        self.assertEqual(row["decision"], "REPLACEMENT_REQUESTED")
        self.assertEqual(row["current"]["value"], .60)
        self.assertEqual(row["planned"]["value"], .75)
        self.assertTrue(row["approval_required_at_application"] and row["backup_required_at_application"])
        for before, after in zip(plan["entries"], chosen["entries"]):
            if before["key"] != "menu.background-alpha":
                self.assertEqual(before, after)
        # A resource selector is a bounded set, not --force.
        group, _ = self.plan("first", "--prefer-heartchy", "shell_tokens")
        self.assertEqual(self.plan_row(group)["decision"], "REPLACEMENT_REQUESTED")
        self.assertEqual(self.plan_row(group, "bar.transparent", "shell_intent")["decision"], "LOCAL_PRESERVED")
        for extra in [("--prefer-heartchy", "shell_tokens:font.base-size"),
                      ("--prefer-heartchy", "plugins"),
                      ("--keep-local", "shell_tokens", "--prefer-heartchy", "shell_tokens:menu.background-alpha")]:
            result = self.cli("plan", "--candidate", "build/planner-candidate", "--target",
                              "test/fixtures/planner/first", *extra)
            self.expect_bad(result, "plan:")

    def test_plan_invalid_contracts_and_state_cannot_be_overridden(self):
        self.prepare_planner()
        bad, _ = self.plan("invalid", "--prefer-heartchy", "shell_tokens", "--prefer-heartchy", "shell_intent")
        self.assertTrue(all(row["decision"] == "BLOCKED" for row in bad["entries"]))
        self.assertFalse(any(row["approval_required_at_application"] for row in bad["entries"]))
        marker = self.repo / "test/fixtures/planner/first/target.json"
        data = json.loads(marker.read_text())
        data["contracts"]["shell_tokens"] = "unrecognized-v2"
        marker.write_text(json.dumps(data))
        bad, _ = self.plan("first", "--prefer-heartchy", "shell_tokens")
        self.assertEqual(self.plan_row(bad)["reason"], "UNSUPPORTED_TARGET_CONTRACT")
        state = self.repo / "test/fixtures/planner/local/state.json"
        data = json.loads(state.read_text())
        data["resources"]["shell_tokens"]["values"]["font.base-size"] = {"state": "present", "value": 11}
        state.write_text(json.dumps(data))
        bad, _ = self.plan("local", "--prefer-heartchy", "shell_tokens")
        self.assertTrue(bad["blocked"])
        self.assertEqual(self.plan_row(bad)["base"], {"state": "unknown"})
        state.write_text('{"broken":')
        bad, _ = self.plan("local")
        self.assertEqual(bad["phase"], "unknown")
        target_json = self.repo / "test/fixtures/planner/managed/config/omarchy/shell.json"
        target_json.unlink()
        bad, _ = self.plan("managed", "--prefer-heartchy", "shell_intent")
        self.assertIn("JSON_SEED_REQUIRED", self.plan_row(bad, "bar.transparent", "shell_intent")["reason"])
        target_json.write_text('{"version":1,"bar":{"id":"other.bar","transparent":false}}')
        bad, _ = self.plan("managed", "--prefer-heartchy", "shell_intent")
        self.assertIn("BAR_CONTRACT_INCOMPATIBLE", self.plan_row(bad, "bar.transparent", "shell_intent")["reason"])

    def test_plan_stale_inputs_require_new_review(self):
        self.prepare_planner()
        selected = ("--prefer-heartchy", "shell_tokens:menu.background-alpha")
        plan, _ = self.plan("conflict", *selected)
        saved = self.repo / "build/previous-plan.json"
        saved.write_text(json.dumps(plan))
        same, _ = self.plan("conflict", *selected, "--recheck", "build/previous-plan.json")
        self.assertEqual(same["freshness"]["status"], "MATCH")
        path = self.repo / "test/fixtures/planner/conflict/config/omarchy/shell.toml"
        original = path.read_bytes()
        path.write_bytes(original + b'# unrelated later edit\n')
        stale, _ = self.plan("conflict", *selected, "--recheck", "build/previous-plan.json")
        self.assertEqual(stale["freshness"]["status"], "STALE")
        self.assertTrue(all(row["decision"] == "BLOCKED" for row in stale["entries"]))
        self.assertIn(path.relative_to(self.repo).as_posix(), stale["freshness"]["changed_inputs"])
        path.write_bytes(original)
        stale, _ = self.plan("conflict", "--keep-local", "shell_tokens:menu.background-alpha", "--recheck", "build/previous-plan.json")
        self.assertFalse(stale["freshness"]["same_context"])
        first, _ = self.plan("first")
        saved.write_text(json.dumps(first))
        # Creation of previously absent state invalidates the old first-install plan.
        shutil.copyfile(self.repo / "test/fixtures/planner/managed/state.json",
                        self.repo / "test/fixtures/planner/first/state.json")
        stale, _ = self.plan("first", "--recheck", "build/previous-plan.json")
        self.assertEqual(stale["freshness"]["status"], "STALE")

    def test_plan_preserves_recipient_bytes_and_never_executes_recipient_lua(self):
        self.prepare_planner()
        before = tree(self.repo)
        plan, result = self.plan("first", "--prefer-heartchy", "hypr", resources=())
        lua = [row for row in plan["entries"] if row["resource"] in ("hypr_module", "hypr_connection")]
        self.assertTrue(lua and all(row["decision"] == "BLOCKED" for row in lua))
        self.assertTrue(all(row["current"] == {"state": "unknown"} for row in lua))
        self.assertEqual(before, tree(self.repo))
        self.assertNotIn("SYNTHETIC_UNMANAGED", result.stdout)
        self.assertNotIn("recipient Lua must never execute", result.stdout)
        audit = json.loads(result.stderr.split("HEARTCHY_EXEC_AUDIT=", 1)[1])
        self.assertEqual(len(audit), 1)  # Candidate validation only; recipient is never executed.
        self.assertTrue(all(command[1].endswith('/tools/lua-contract.lua') for command in audit))
        for path, identity in plan["inputs"].items():
            if identity["exists"]:
                self.assertEqual(sha((self.repo / path).read_bytes()), identity["sha256"])
        text = self.cli("plan", "--candidate", "build/planner-candidate", "--target",
                        "test/fixtures/planner/first", "--resource", "shell_intent")
        self.expect_ok(text)
        self.assertIn("base=", text.stdout)
        self.assertIn("NO WRITES", text.stdout)

    def test_plan_rejects_escapes_symlinks_and_modified_candidate(self):
        self.prepare_planner()
        for location in ["/home/example/.config", "../target", "build/../test/fixtures/planner/first", "core"]:
            result = self.cli("plan", "--candidate", "build/planner-candidate", "--target", location)
            self.expect_bad(result, "plan:")
        shell = self.repo / "test/fixtures/planner/first/config/omarchy/shell.json"
        original = shell.read_bytes()
        outside = self.area / "outside.json"
        outside.write_bytes(original)
        shell.unlink()
        shell.symlink_to(outside)
        blocked, _ = self.plan("first", "--prefer-heartchy", "shell_intent")
        self.assertEqual(self.plan_row(blocked, "bar.transparent", "shell_intent")["decision"], "BLOCKED")
        self.assertEqual(outside.read_bytes(), original)
        candidate = self.repo / "build/planner-candidate/core/shell/settings-intent.json"
        candidate.write_text('{"bar":{"transparent":false}}')
        blocked, _ = self.plan("first", "--prefer-heartchy", "shell_intent")
        self.assertEqual(blocked["blocks"][0]["reason"], "CANDIDATE_INVALID")

    def test_plan_special_files_fail_without_waiting_for_a_writer(self):
        self.prepare_planner()
        target = self.repo / "test/fixtures/planner/first"
        for relative in ("config/omarchy/shell.json", "state.json"):
            path = target / relative
            original = path.read_bytes() if path.exists() else None
            if path.exists():
                path.unlink()
            os.mkfifo(path)
            blocked, _ = self.plan("first", "--prefer-heartchy", "shell_intent")
            self.assertTrue(blocked["blocked"])
            self.assertIn("not a standalone regular file", str(blocked))
            path.unlink()
            if original is not None:
                path.write_bytes(original)

    def lua_case(self, name):
        recipes = json.loads((self.repo / "test/fixtures/planner/lua-cases.json").read_text())["cases"]
        recipe = next(item for item in recipes if item["name"] == name)
        target = self.repo / "test/fixtures/planner" / ("lua-case-" + name)
        shutil.copytree(self.repo / "test/fixtures/planner/lua-first", target)
        personal = (target / "config/hypr/looknfeel.lua").read_bytes()
        proposal = (self.repo / "core/hypr/heartchy.lua").read_bytes()
        contents = {"proposal": proposal, "old": b"-- synthetic prior module\n" + proposal,
                    "local": b'error("recipient module must never execute")\n', "absent": None}
        current = contents[recipe["module"]]
        if current is not None:
            (target / "config/hypr/heartchy.lua").write_bytes(current)
        state = {"schema_version": 1, "kind": "heartchy-managed-state", "successful": True,
                 "application_id": "synthetic-lua-application", "resources": {}}
        def identity(data):
            return {"state": "present", "value": {"sha256": sha(data), "bytes": len(data)}}
        if recipe["base"] != "none":
            state["resources"]["hypr_module"] = {"contract": "heartchy-lua-module-bytes-v1",
                "values": {"content": identity(contents[recipe["base"]])}}
        connection = recipe["connection"]
        look = target / "config/hypr/looknfeel.lua"
        if connection in ("managed", "marked"):
            look.write_bytes(LUA_LOAD + personal)
        if connection in ("managed", "deleted-managed"):
            state["resources"]["hypr_connection"] = {"contract": "omarchy-lua-prefix-v1",
                "values": {"load": identity(LUA_LOAD)}}
        elif connection == "equivalent":
            look.write_bytes(b"-- unowned equivalent spelling\nrequire 'hypr.heartchy';\n" + personal)
        elif connection == "absent":
            look.unlink()
        if state["resources"]:
            (target / "state.json").write_text(json.dumps(state))
        return target, recipe, personal

    def lua_rows(self, plan):
        return (self.plan_row(plan, "content", "hypr_module"), self.plan_row(plan, "load", "hypr_connection"))

    def test_lua_plan_byte_lifecycle_and_dependency(self):
        self.prepare_planner()
        names = [x["name"] for x in json.loads((self.repo / "test/fixtures/planner/lua-cases.json").read_text())["cases"]]
        for name in names:
            with self.subTest(case=name):
                target, recipe, personal = self.lua_case(name)
                before = tree(target)
                plan, result = self.plan(target.name, resources=("hypr",))
                module, link = self.lua_rows(plan)
                self.assertEqual(module["decision"], recipe["module_decision"])
                self.assertEqual(link["decision"], recipe["connection_decision"])
                self.assertEqual(tree(target), before)
                self.assertEqual(module["functional_validation"], "NOT_RUN")
                self.assertEqual(link["functional_validation"], "NOT_RUN")
                if name == "first":
                    self.assertEqual(module["operation"], "create-file")
                    self.assertEqual(link["operation"], "insert-prefix")
                    self.assertEqual(link["insertion"], {"byte_offset": 0, "text": LUA_LOAD.decode()})
                    proposed = link["insertion"]["text"].encode() + personal
                    self.assertEqual(proposed[len(LUA_LOAD):], personal)
                    self.assertEqual(link["proposed_file"]["value"]["sha256"], sha(proposed))
                    self.assertNotIn("border_size = 3", link["difference"]["text"])
                if name == "repeat":
                    self.assertEqual(link["operation"], "none")
                    self.assertNotIn("insertion", link)
                    self.assertEqual(link["difference"]["text"], "")
                    self.assertEqual(link["ownership"], "managed-block")
                if name.startswith("unowned"):
                    self.assertEqual(link["ownership"], "not-established")
                if name == "deleted-load":
                    self.assertEqual(link["planned"], {"state": "absent"})
                    self.assertEqual(link["operation"], "none")
                    restored, _ = self.plan(target.name, "--prefer-heartchy", "hypr_connection:load", resources=("hypr",))
                    requested = self.lua_rows(restored)[1]
                    self.assertEqual(requested["decision"], "REPLACEMENT_REQUESTED")
                    self.assertEqual(requested["operation"], "insert-prefix")
                    self.assertTrue(requested["approval_required_at_application"])
                if module["decision"] in ("LOCAL_PRESERVED", "CONFLICT_PENDING"):
                    self.assertTrue(module["warnings"])
                    self.assertEqual(link["operation"], "none")
                    self.assertFalse(link["depends_on"][0]["satisfied"])
                audit = json.loads(result.stderr.split("HEARTCHY_EXEC_AUDIT=", 1)[1])
                self.assertEqual(len(audit), 1)

    def test_lua_plan_selected_replacement_and_local_preservation(self):
        self.prepare_planner()
        target, _, _ = self.lua_case("module-conflict")
        preserved, _ = self.plan(target.name, "--keep-local", "hypr_module:content", resources=("hypr",))
        module, link = self.lua_rows(preserved)
        self.assertEqual(module["decision"], "LOCAL_PRESERVED")
        self.assertEqual(module["operation"], "none")
        self.assertEqual(link["decision"], "BLOCKED")
        chosen, _ = self.plan(target.name, "--prefer-heartchy", "hypr_module:content", resources=("hypr",))
        module, link = self.lua_rows(chosen)
        self.assertEqual(module["decision"], "REPLACEMENT_REQUESTED")
        self.assertEqual(module["operation"], "replace-file")
        self.assertTrue(module["approval_required_at_application"] and module["backup_required_at_application"])
        self.assertEqual(link["decision"], "NO_CHANGE")
        self.assertTrue(link["depends_on"][0]["approval_pending"])
        self.assertIn('-error("recipient module must never execute")', module["difference"]["text"])
        limited, _ = self.plan(target.name, resources=("hypr_connection",))
        self.assertEqual(self.plan_row(limited, "load", "hypr_connection")["decision"], "BLOCKED")
        self.assertEqual(len(limited["entries"]), 1)
        with self.subTest("no scalar Lua overrides"):
            result = self.cli("plan", "--candidate", "build/planner-candidate", "--target",
                              "test/fixtures/planner/" + target.name,
                              "--prefer-heartchy", "hypr:decoration.blur.size")
            self.expect_bad(result, "selector resource outside requested scope")

    def test_lua_plan_module_diff_preserves_unterminated_and_binary_bytes(self):
        self.prepare_planner()
        target, _, _ = self.lua_case("existing-unowned")
        path = target / "config/hypr/heartchy.lua"
        path.write_bytes(b"old")
        plan, _ = self.plan(target.name, "--prefer-heartchy", "hypr_module", resources=("hypr_module",))
        row = self.plan_row(plan, "content", "hypr_module")
        self.assertEqual(row["decision"], "REPLACEMENT_REQUESTED")
        self.assertIn('-old\n\\ No newline at end of file\n+', row["difference"]["text"])
        self.assertNotIn('-old+', row["difference"]["text"])
        raw = b"\xff\x00\xfe"
        path.write_bytes(raw)
        plan, _ = self.plan(target.name, "--prefer-heartchy", "hypr_module", resources=("hypr_module",))
        row = self.plan_row(plan, "content", "hypr_module")
        import base64
        self.assertEqual(row["difference"]["format"], "base64-replacement")
        self.assertEqual(base64.b64decode(row["difference"]["before"]), raw)
        self.assertEqual(base64.b64decode(row["difference"]["after"]), (self.repo / "core/hypr/heartchy.lua").read_bytes())
        self.assertEqual(path.read_bytes(), raw)

    def test_lua_plan_lexical_boundaries_and_exact_personal_preservation(self):
        self.prepare_planner()
        target, _, _ = self.lua_case("first")
        look = target / "config/hypr/looknfeel.lua"
        examples = [b"", b"-- comment only\n", b"\r\n-- Windows line endings\r\nhl.config({general={border_size=3}})\r\n",
                    b'--[=[\nrequire("hypr.heartchy")\n-- BEGIN HEARTCHY: fake\n]=]\n'
                    b'hl.config({ note = [[require("hypr.heartchy")]], other = "-- END HEARTCHY" })\n',
                    b'hl.config({ note = "require(\\\"hypr.heartchy\\\")", other = "\\\\" })\n']
        for original in examples:
            with self.subTest(original=original):
                look.write_bytes(original)
                plan, _ = self.plan(target.name, resources=("hypr",))
                _, link = self.lua_rows(plan)
                self.assertEqual(link["decision"], "MANAGED_CHANGE", link["reason"])
                self.assertEqual(link["insertion"]["text"].encode(), LUA_LOAD)
                self.assertEqual(link["proposed_file"]["value"]["sha256"], sha(LUA_LOAD + original))
                self.assertEqual(look.read_bytes(), original)
        # Equivalent syntax is recognized lexically, never adopted or rewritten.
        (target / "config/hypr/heartchy.lua").write_bytes((self.repo / "core/hypr/heartchy.lua").read_bytes())
        for code in [b"require 'hypr.heartchy';\n", b'require ( "hypr.heartchy" )\n', b'require[=[hypr.heartchy]=]\n']:
            look.write_bytes(b"-- retained comment\n" + code)
            plan, _ = self.plan(target.name, resources=("hypr",))
            _, link = self.lua_rows(plan)
            self.assertEqual(link["reason"], "UNOWNED_EQUIVALENT_LOAD")
            self.assertEqual(link["operation"], "none")

    def test_lua_plan_ambiguous_structure_and_markers_never_forced(self):
        self.prepare_planner()
        target, _, personal = self.lua_case("repeat")
        look = target / "config/hypr/looknfeel.lua"
        cases = [
            (LUA_LOAD.splitlines(keepends=True)[0] + personal, "LOAD_MARKERS_DAMAGED"),
            (LUA_LOAD + LUA_LOAD + personal, "LOAD_MARKERS_DAMAGED"),
            (LUA_LOAD.replace(b'require("hypr.heartchy")', b'require("hypr.other")') + personal, "LOAD_MARKERS_DAMAGED"),
            (b"-- new leading comment\n" + LUA_LOAD + personal, "LOAD_MARKERS_DAMAGED"),
            (LUA_LOAD + b'require("hypr.heartchy")\n', "DUPLICATE_EXECUTABLE_LOAD"),
            (b'require("hypr.heartchy")\n' + personal, "MANAGED_LOAD_MARKERS_REMOVED"),
            (LUA_LOAD + b'if true then require("hypr.heartchy") end\n', "LUA_UNSUPPORTED_DECLARATION"),
            (LUA_LOAD + b'local r = require; r("hypr.heartchy")\n', "LUA_UNSUPPORTED_DECLARATION"),
            (LUA_LOAD + b'hl.config({x = function() end})\n', "LUA_NON_LITERAL_VALUE"),
            (LUA_LOAD + b'--[=[unterminated', "LUA_UNTERMINATED_LONG_COMMENT"),
            (LUA_LOAD + b'hl.config({ end = 3 })', "LUA_RESERVED_FIELD_NAME"),
            (LUA_LOAD + b'os.execute("do not execute")\n', "LUA_UNSUPPORTED_TOP_LEVEL_CALL"),
        ]
        for code, reason in cases:
            with self.subTest(reason=reason):
                look.write_bytes(code)
                plan, _ = self.plan(target.name, "--prefer-heartchy", "hypr", resources=("hypr",))
                _, link = self.lua_rows(plan)
                self.assertEqual(link["decision"], "BLOCKED")
                self.assertIn(reason, link["reason"])
                self.assertEqual(link["operation"], "none")
                self.assertNotIn("insertion", link)
                self.assertEqual(look.read_bytes(), code)
        (target / "state.json").unlink()
        for code, reason in [(personal + b'require("hypr.heartchy")\n', "LOAD_AFTER_PERSONAL_STATEMENTS"),
                             (b'require("hypr." .. "heartchy")\n', "LUA_INDIRECT_OR_OTHER_MODULE_LOAD"),
                             (b'require("hypr.other")\n', "LUA_INDIRECT_OR_OTHER_MODULE_LOAD")]:
            look.write_bytes(code)
            plan, _ = self.plan(target.name, resources=("hypr",))
            self.assertIn(reason, self.lua_rows(plan)[1]["reason"])

    def test_lua_plan_dependency_entrypoint_shadow_and_scope(self):
        self.prepare_planner()
        target, _, _ = self.lua_case("first")
        plan, _ = self.plan(target.name, "--keep-local", "hypr_module", resources=("hypr",))
        module, link = self.lua_rows(plan)
        self.assertEqual(module["planned"], {"state": "absent"})
        self.assertIn("MODULE_DEPENDENCY_UNSATISFIED", link["reason"])
        limited, _ = self.plan(target.name, resources=("hypr_connection",))
        self.assertEqual(limited["entries"][0]["decision"], "BLOCKED")
        entrypoint = target / "config/hypr/hyprland.lua"
        original = entrypoint.read_bytes()
        entrypoint.write_bytes(original.replace(b'require("hypr.looknfeel")', b'require("hypr.unknown")'))
        blocked, _ = self.plan(target.name, "--prefer-heartchy", "hypr", resources=("hypr",))
        self.assertIn("ENTRYPOINT_ORDER_UNVERIFIED", self.lua_rows(blocked)[1]["reason"])
        entrypoint.write_bytes(original)
        for name in ("heartchy", "looknfeel"):
            shadow = target / "state/hypr" / (name + ".lua")
            shadow.parent.mkdir(parents=True, exist_ok=True)
            shadow.write_text('error("shadow must never execute")\n')
            blocked, _ = self.plan(target.name, "--prefer-heartchy", "hypr", resources=("hypr",))
            self.assertIn("STATE_MODULE_SHADOW", self.lua_rows(blocked)[1]["reason"])
            shadow.unlink()
        # Explicitly replacing an unowned local module can unblock insertion,
        # but its approval remains a dependency, never an implicit grant.
        (target / "config/hypr/heartchy.lua").write_text('error("unowned")\n')
        chosen, _ = self.plan(target.name, "--prefer-heartchy", "hypr_module", resources=("hypr",))
        module, link = self.lua_rows(chosen)
        self.assertEqual(module["decision"], "REPLACEMENT_REQUESTED")
        self.assertEqual(link["operation"], "insert-prefix")
        self.assertTrue(link["approval_required_at_application"])

    def test_lua_entrypoint_stock_extensions_and_real_hyprmoncfg_regression(self):
        self.prepare_planner()
        target, _, personal = self.lua_case("first")
        path = target / "config/hypr/hyprland.lua"
        stock = path.read_bytes()
        look = target / "config/hypr/looknfeel.lua"
        cases = json.loads((self.repo / "test/fixtures/planner/entrypoint-cases.json").read_text())
        for case in cases:
            with self.subTest(case=case["name"]):
                entry = stock
                if case.get("swap"):
                    entry = entry.replace(b'require("hypr.input")', b'require("hypr.autostart")', 1)
                if case.get("broken_concat"):
                    entry = entry.replace(b" .. ", b" . -- separated operator\n. ", 1)
                entry += case["tail"].encode()
                path.write_bytes(entry)
                look.write_bytes((LUA_LOAD if case.get("look") else b"") + personal)
                before = tree(target)
                plan, _ = self.plan(target.name, resources=("hypr",))
                _, link = self.lua_rows(plan)
                if case["blocked"]:
                    self.assertEqual(link["decision"], "BLOCKED")
                    self.assertIn(case["blocked"], link["reason"])
                    self.assertEqual(link["operation"], "none")
                else:
                    self.assertNotEqual(link["decision"], "BLOCKED", link["reason"])
                    self.assertEqual(link["operation"], "none" if case.get("look") else "insert-prefix")
                self.assertEqual(before, tree(target))

    def test_lua_extended_entrypoint_apply_rollback_preserves_foreign_bytes(self):
        target = self.apply_fixture()
        path = target / "config/hypr/hyprland.lua"
        case = json.loads((self.repo / "test/fixtures/planner/entrypoint-cases.json").read_text())[2]
        path.write_bytes(path.read_bytes() + case["tail"].encode())
        original_entry = path.read_bytes()
        personal = (target / "config/hypr/looknfeel.lua").read_bytes()
        _, approval = self.apply_plan()
        self.expect_ok(self.apply_cli(approval))
        self.assertEqual(path.read_bytes(), original_entry)
        self.assertEqual((target / "config/hypr/looknfeel.lua").read_bytes(), LUA_LOAD + personal)
        self.expect_ok(self.effect_cli("rollback"))
        self.assertEqual(path.read_bytes(), original_entry)
        self.assertEqual((target / "config/hypr/looknfeel.lua").read_bytes(), personal)

    def test_lua_plan_recheck_both_files_and_path_protections(self):
        self.prepare_planner()
        target, _, _ = self.lua_case("repeat")
        baseline, _ = self.plan(target.name, resources=("hypr",))
        (self.repo / "build/lua-plan.json").write_text(json.dumps(baseline))
        same, _ = self.plan(target.name, "--recheck", "build/lua-plan.json", resources=("hypr",))
        self.assertEqual(same["freshness"]["status"], "MATCH")
        for name in ("heartchy.lua", "looknfeel.lua"):
            path = target / "config/hypr" / name
            original = path.read_bytes()
            path.write_bytes(original + b"-- later personal edit\n")
            stale, _ = self.plan(target.name, "--recheck", "build/lua-plan.json", resources=("hypr",))
            self.assertEqual(stale["freshness"]["status"], "STALE")
            self.assertTrue(all(row["decision"] == "BLOCKED" and row["operation"] == "none" for row in stale["entries"]))
            for dependency in self.lua_rows(stale)[1]["depends_on"]:
                self.assertFalse(dependency["satisfied"] or dependency["approval_pending"])
                self.assertEqual(dependency["decision"], "BLOCKED")
            self.assertIn(path.relative_to(self.repo).as_posix(), stale["freshness"]["changed_inputs"])
            path.unlink()
            outside = self.area / name
            outside.write_bytes(original)
            path.symlink_to(outside)
            bad, _ = self.plan(target.name, "--prefer-heartchy", "hypr", resources=("hypr",))
            self.assertTrue(bad["blocked"])
            self.assertEqual(outside.read_bytes(), original)
            path.unlink()
            os.mkfifo(path)
            bad, _ = self.plan(target.name, resources=("hypr",))
            self.assertTrue(bad["blocked"])
            path.unlink()
            path.write_bytes(original)

    def test_feature_scaffold_scope_and_portability(self):
        personal = self.area / "recipient/.config/omarchy/shell.toml"
        personal.parent.mkdir(parents=True)
        personal.write_text('# private synthetic preference\n[menu]\nbackground-alpha=0.4\n')
        template = (self.repo / "work/FEATURE_TEMPLATE.md").read_bytes()
        directories = {p.relative_to(self.repo) for p in self.repo.rglob("*") if p.is_dir()}
        for slug, cwd in (("scope-example", Path("/")), ("other-example", self.repo)):
            before = tree(SANDBOX)
            result = self.cli("feature", "new", slug, cwd=cwd)
            self.expect_ok(result)
            self.assertIn("HEARTCHY_EXEC_AUDIT=[]", result.stderr)
            document = self.repo / "work/features" / (slug + ".md")
            text = document.read_text()
            self.assertIn("\nID: HCY-" + slug + "\n", text)
            self.assertIn("\nEstado: DESIGN\n", text)
            self.assertNotIn("{{", text)
            self.assertEqual(template, (self.repo / "work/FEATURE_TEMPLATE.md").read_bytes())
            # Exactly the requested work document may differ, even in the fake
            # recipient and sibling projects outside the checkout.
            self.assertEqual(before, tree(SANDBOX, [document]))
        self.assertFalse((self.repo / ".git").exists())
        self.assertEqual(directories, {p.relative_to(self.repo) for p in self.repo.rglob("*") if p.is_dir()})

    def test_feature_invalid_arguments_and_help_have_no_effects(self):
        before = tree(SANDBOX)
        for args in (("feature", "--help"), ("feature", "new", "--help")):
            result = self.cli(*args)
            self.expect_ok(result)
            self.assertIn("HEARTCHY_EXEC_AUDIT=[]", result.stderr)
        for args in (("feature",), ("feature", "new"), ("feature", "install", "x"),
                     ("feature", "new", "x", "--force"), ("feature", "new", "x", "y")):
            result = self.cli(*args)
            self.assertEqual(result.returncode, 2)
            self.assertIn("HEARTCHY_EXEC_AUDIT=[]", result.stderr)
        for slug in ("../escape", "/tmp/escape", "bad/name", "bad\\name", ".", "..", "UPPER", "a--b",
                     "a-", "1start", "área", "bad name", "x\ny", "x" * 65, ""):
            result = self.cli("feature", "new", slug)
            self.expect_bad(result, "invalid feature slug")
            self.assertIn("HEARTCHY_EXEC_AUDIT=[]", result.stderr)
        self.assertEqual(before, tree(SANDBOX))

    def test_feature_existing_documents_and_unsafe_paths_are_preserved(self):
        folder = self.repo / "work/features"
        folder.mkdir(exist_ok=True)
        outside = self.area / "outside.md"
        outside.write_text("preserve me\n")
        for kind in ("file", "directory", "symlink", "dangling", "hardlink", "fifo"):
            destination = folder / (kind + ".md")
            if kind == "file": destination.write_text("existing feature\n")
            elif kind == "directory": destination.mkdir()
            elif kind == "symlink": destination.symlink_to(outside)
            elif kind == "dangling": destination.symlink_to(self.area / "absent.md")
            elif kind == "hardlink": os.link(outside, destination)
            else: os.mkfifo(destination)
            result = self.cli("feature", "new", kind)
            self.expect_bad(result, "feature refused/failed")
            self.assertIn("HEARTCHY_EXEC_AUDIT=[]", result.stderr)
            self.assertEqual(outside.read_text(), "preserve me\n")
            if kind == "file": self.assertEqual(destination.read_text(), "existing feature\n")
            if kind == "directory": destination.rmdir()
            else: destination.unlink()
        held = self.area / "held-features"
        folder.rename(held)
        folder.symlink_to(held, target_is_directory=True)
        result = self.cli("feature", "new", "parent-link")
        self.expect_bad(result, "feature refused/failed")
        self.assertFalse((held / "parent-link.md").exists())
        folder.unlink()
        held.rename(folder)
        work = self.repo / "work"
        held_work = self.area / "held-work"
        work.rename(held_work)
        work.symlink_to(held_work, target_is_directory=True)
        self.expect_bad(self.cli("feature", "new", "work-link"), "cannot safely read")
        self.assertFalse((held_work / "features/work-link.md").exists())

    def test_feature_template_contract_refuses_incomplete_or_unsafe_documents(self):
        path = self.repo / "work/FEATURE_TEMPLATE.md"
        original = path.read_text()
        broken = [original.replace("## Privilegios", "## Unexpected"),
                  original + "\n## Objetivo\nDuplicate\n",
                  original.replace("Estado: DESIGN", "Estado: APPROVED"),
                  original.replace("Estado: DESIGN", "Estado: APPROVED\nEstado: DESIGN"),
                  original.replace("{{slug}}", "{{unknown}}"),
                  original.replace("Responsable: PENDIENTE\n", "")]
        for content in broken:
            path.write_text(content)
            before = tree(SANDBOX)
            result = self.cli("feature", "new", "bad-template")
            self.expect_bad(result, "feature template")
            self.assertIn("HEARTCHY_EXEC_AUDIT=[]", result.stderr)
            self.assertEqual(before, tree(SANDBOX))
        path.write_text(original)
        held = self.area / "template.md"
        path.rename(held)
        path.symlink_to(held)
        self.expect_bad(self.cli("feature", "new", "template-link"), "cannot safely read")
        self.assertFalse((self.repo / "work/features/template-link.md").exists())

    def test_workflow_checks_routing_metadata_and_real_link_targets(self):
        self.expect_ok(self.cli("check"))
        cases = [
            ("AGENTS.md", lambda s: s.replace("agents/skills/cli-command.md", "agents/skills/missing.md"), "cannot safely read"),
            ("agents/skills/testing.md", lambda s: s.replace("name: testing", "name: wrong"), "purpose/trigger"),
            ("agents/skills/testing.md", lambda s: s.replace(s.splitlines()[2], "description: "), "purpose/trigger"),
            ("agents/skills/testing.md", lambda s: s + "\n[missing](../../docs/missing.md)\n", "cannot safely read"),
            ("agents/skills/testing.md", lambda s: s + "\n[bad anchor](../../docs/development.md#absent-gate)\n", "broken anchor"),
            ("agents/skills/testing.md", lambda s: s + "\n[escape](../../../outside.md)\n", "path escapes scope"),
        ]
        for relative, change, message in cases:
            path = self.repo / relative
            original = path.read_text()
            path.write_text(change(original))
            self.expect_bad(self.cli("check"), message)
            path.write_text(original)
        # Missing a procedure, rather than just mislinking it, must also fail.
        guide = self.repo / "agents/skills/cli-command.md"
        guide.unlink()
        self.expect_bad(self.cli("check"), "cannot safely read")

    def apply_fixture(self):
        self.prepare_planner()
        target = self.repo / "build/simulations/core"
        shutil.copytree(self.repo / "test/fixtures/planner/lua-first", target)
        (target / "config/omarchy").mkdir()
        (target / "config/omarchy/shell.json").write_text('{"version":1,"bar":{"id":"omarchy.bar","transparent":false,"layout":{"right":["stock"]}},"idle":{"enabled":true}}\n')
        (target / "config/omarchy/shell.toml").write_text('# personal comment\n[menu]\nbackground-alpha = 0.5 # keep comment\ncustom-value = 3\n[font]\nbase-size = 14\n')
        return target

    def apply_plan(self, *options):
        result = self.cli("plan", "--candidate", "build/planner-candidate", "--target", "build/simulations/core", "--state-root", "build/state/core", "--format", "json", *options)
        self.assertIn(result.returncode, (0, 3), result.stderr)
        path = self.repo / "build/approved.json"
        path.write_text(result.stdout)
        return json.loads(result.stdout), sha(path.read_bytes())

    def apply_cli(self, approval):
        return self.cli("apply", "--candidate", "build/planner-candidate", "--target", "build/simulations/core", "--state-root", "build/state/core", "--plan", "build/approved.json", "--approve", approval, "--format", "json")

    def effect_cli(self, command, *extra):
        args = [command, "--target", "build/simulations/core", "--state-root", "build/state/core", "--format", "json"]
        if command != "validate":
            args += ["--approve", command]
        return self.cli(*args, *extra)

    def test_core_reapply_releases_old_file_creation_metadata(self):
        target = self.apply_fixture()
        tokens = target / "config/omarchy/shell.toml"
        tokens.unlink()
        _, approval = self.apply_plan("--resource", "shell_tokens")
        self.expect_ok(self.apply_cli(approval))
        self.expect_ok(self.effect_cli("rollback"))
        self.assertFalse(tokens.exists())
        for personal in (b"", b"[menu]\n"):
            tokens.write_bytes(personal)
            _, approval = self.apply_plan("--resource", "shell_tokens")
            self.expect_ok(self.apply_cli(approval))
            self.expect_ok(self.effect_cli("rollback"))
            self.assertTrue(tokens.exists())
            self.assertEqual(tokens.read_bytes(), personal)

    def test_core_target_rejects_second_state_authority(self):
        target = self.apply_fixture()
        _, approval = self.apply_plan("--resource", "hypr")
        self.expect_ok(self.apply_cli(approval))
        before = tree(target)
        result = self.cli("rollback", "--target", "build/simulations/core", "--state-root", "build/state/other", "--approve", "rollback")
        self.expect_bad(result, "TARGET_STATE_AUTHORITY_MISMATCH")
        self.assertEqual(tree(target), before)
        self.expect_ok(self.effect_cli("rollback"))

    def test_core_lua_inspection_cannot_assign_globals(self):
        data = (self.repo / "core/hypr/heartchy.lua").read_bytes() + b"\nhl = nil\n"
        result = subprocess.run(["/usr/bin/lua", str(self.repo / "tools/lua-contract.lua")], input=data, capture_output=True, env=ENV)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"read-only", result.stderr)

    def matching_shell_fixture(self):
        target = self.apply_fixture()
        shell = target / "config/omarchy/shell.json"
        shell.write_bytes(shell.read_bytes().replace(b'"transparent":false', b'"transparent":true'))
        tokens = target / "config/omarchy/shell.toml"
        foreign = (self.repo / "test/fixtures/planner/foreign-shell.toml").read_bytes()
        tokens.write_bytes(foreign + (self.repo / "core/shell/cristal.toml").read_bytes())
        return target

    def revised_token_candidate(self):
        source = self.repo / "core/shell/cristal.toml"
        source.write_bytes(source.read_bytes().replace(b'border-alpha = 0.6\n', b'border-alpha = 0.55\n', 1))
        self.rehash("core/shell/cristal.toml")
        shutil.rmtree(self.repo / "build/planner-candidate")
        self.prepare_planner()

    def test_recipient_toml_omafiles_boolean_arrays_and_foreign_format_preserved(self):
        target = self.apply_fixture()
        tokens = target / "config/omarchy/shell.toml"
        foreign = (self.repo / "test/fixtures/planner/foreign-shell.toml").read_bytes()
        tokens.write_bytes(foreign + tokens.read_bytes())
        original = tokens.read_bytes()
        plan, approval = self.apply_plan("--prefer-heartchy", "shell_tokens:menu.background-alpha")
        self.assertFalse(plan["blocked"])
        self.expect_ok(self.apply_cli(approval))
        self.assertTrue(tokens.read_bytes().startswith(foreign))
        self.assertIn(b'background-alpha = 0.75 # keep comment', tokens.read_bytes())
        self.expect_ok(self.effect_cli("validate"))
        self.expect_ok(self.effect_cli("rollback"))
        self.assertEqual(tokens.read_bytes(), original)
        # Managed spellings incompatible with the stock line consumer stay
        # blocked, even though foreign full TOML is accepted by tomllib.
        for variant in [b'["menu"]\nbackground-alpha = 0.75\n', b'[menu]\nbackground-alpha = 7e-1\n',
                        b'[menu]\nbackground-alpha = true\n']:
            tokens.write_bytes(foreign + variant)
            before = tree(target)
            plan, approval = self.apply_plan("--prefer-heartchy", "shell_tokens")
            self.assertTrue(plan["blocked"])
            self.expect_bad(self.apply_cli(approval), "BLOCKED")
            self.assertEqual(before, tree(target))

    def test_matching_preexisting_shell_acceptance_never_claims_a_previous_value(self):
        target = self.matching_shell_fixture()
        before = tree(target)
        plan, approval = self.apply_plan("--resource", "shell_intent", "--resource", "shell_tokens")
        self.assertEqual(len(plan["entries"]), 62)
        for row in plan["entries"]:
            self.assertEqual(row["decision"], "NO_CHANGE")
            self.assertEqual(row["reason"], "ALREADY_MATCHES")
            self.assertEqual(row["base"], {"state": "unmanaged"})
            self.assertEqual(row["state_operation"], "accept-matching-reference")
            self.assertTrue(row["approval_required_at_application"])
        human = self.cli("plan", "--candidate", "build/planner-candidate", "--target", "build/simulations/core",
                         "--state-root", "build/state/core", "--resource", "shell_intent", "--resource", "shell_tokens")
        self.expect_ok(human)
        self.assertEqual(human.stdout.count("state_operation=accept-matching-reference"), 62)
        self.assertEqual(tree(target), before)
        result = self.apply_cli(approval)
        self.expect_ok(result)
        applied = json.loads(result.stdout)
        self.assertEqual(applied["changed_files"], [])
        self.assertEqual(len(applied["accepted_matching"]), 62)
        self.assertEqual(tree(target), before)
        ledger = json.loads((self.repo / "build/state/core/ledger.json").read_text())
        self.assertEqual(ledger["owned"], {})
        self.assertEqual(ledger["files"], {})
        self.assertEqual(len(ledger["accepted"]), 62)
        self.assertTrue(all(set(value) == {"state", "value"} for value in ledger["accepted"].values()))
        self.expect_ok(self.effect_cli("validate"))
        plan, approval = self.apply_plan("--resource", "shell_intent", "--resource", "shell_tokens")
        self.assertTrue(all(row["base_origin"] == "matching-preexisting" for row in plan["entries"]))
        state_before = tree(self.repo / "build/state/core")
        result = self.apply_cli(approval)
        self.expect_ok(result)
        self.assertEqual(json.loads(result.stdout)["result"], "NO_CHANGE")
        self.assertEqual(tree(self.repo / "build/state/core"), state_before)
        self.assertEqual(tree(target), before)
        # An acceptance is a reference, not permission to undo a later edit.
        tokens = target / "config/omarchy/shell.toml"
        tokens.write_bytes(tokens.read_bytes().replace(b'border-alpha = 0.6\n', b'border-alpha = 0.9\n', 1))
        edited = tree(target)
        result = self.effect_cli("rollback")
        self.expect_ok(result)
        self.assertEqual(len(json.loads(result.stdout)["acceptance_released_without_writes"]), 62)
        self.assertEqual(tree(target), edited)
        self.expect_ok(self.effect_cli("rollback"))
        self.assertEqual(tree(target), edited)

    def test_recipient_toml_stock_consumer_ambiguity_and_literal_dotted_key(self):
        target = self.matching_shell_fixture()
        tokens = target / "config/omarchy/shell.toml"
        for suffix in ['[later]\nnote = """\n[menu]\nborder-alpha = 0.1\n"""\n',
                       '[foreign.nested]\nborder-alpha = 0.1\n',
                       '["foreign.table"]\nborder-alpha = 0.6\n']:
            with self.subTest(suffix=suffix):
                tokens.write_bytes(b'[menu]\nborder-alpha = 0.6\n' + suffix.encode())
                before = tree(target)
                plan, approval = self.apply_plan("--resource", "shell_tokens")
                self.assertTrue(plan["blocked"])
                self.assertIn("TOML/stock Shell interpretation differs", self.plan_row(plan)["reason"])
                self.expect_bad(self.apply_cli(approval), "BLOCKED")
                self.assertEqual(tree(target), before)
        # A dotted *literal root name* is foreign data, not a managed table.
        tokens.write_bytes(b'"menu.border-alpha" = 0.6 # retained\n[personal]\nratio = nan\n')
        before = tokens.read_bytes()
        plan, approval = self.apply_plan("--resource", "shell_tokens")
        row = self.plan_row(plan, "menu.border-alpha")
        self.assertEqual(row["current"], {"state": "absent"})
        self.assertEqual(row["decision"], "MANAGED_CHANGE")
        self.assertEqual(row["state_operation"], "none")
        self.expect_ok(self.apply_cli(approval))
        self.assertTrue(tokens.read_bytes().startswith(before))
        self.expect_ok(self.effect_cli("rollback"))
        self.assertEqual(tokens.read_bytes(), before)

    def test_accepted_reference_future_update_and_rollback_capture_real_prewrite_value(self):
        target = self.matching_shell_fixture()
        before = tree(target)
        _, approval = self.apply_plan("--resource", "shell_tokens")
        self.expect_ok(self.apply_cli(approval))
        self.revised_token_candidate()
        plan, approval = self.apply_plan("--resource", "shell_tokens")
        row = self.plan_row(plan, "menu.border-alpha")
        self.assertEqual(row["decision"], "MANAGED_CHANGE")
        self.assertEqual(row["base_origin"], "matching-preexisting")
        self.expect_ok(self.apply_cli(approval))
        ledger = json.loads((self.repo / "build/state/core/ledger.json").read_text())
        self.assertEqual(set(ledger["owned"]), {"shell_tokens:menu.border-alpha"})
        self.assertEqual(ledger["owned"]["shell_tokens:menu.border-alpha"]["original"], {"state":"present", "value":0.6})
        self.assertEqual(len(ledger["accepted"]), 60)
        self.expect_ok(self.effect_cli("rollback"))
        self.assertEqual(tree(target), before)

    def test_accepted_reference_local_conflict_keep_and_scoped_replacement(self):
        target = self.matching_shell_fixture()
        _, approval = self.apply_plan("--resource", "shell_tokens")
        self.expect_ok(self.apply_cli(approval))
        tokens = target / "config/omarchy/shell.toml"
        tokens.write_bytes(tokens.read_bytes().replace(b'border-alpha = 0.6\n', b'border-alpha = 0.9\n', 1))
        edited = tree(target)
        self.revised_token_candidate()
        plan, approval = self.apply_plan("--resource", "shell_tokens")
        self.assertEqual(self.plan_row(plan, "menu.border-alpha")["decision"], "CONFLICT_PENDING")
        self.expect_bad(self.apply_cli(approval), "BLOCKED")
        self.assertEqual(tree(target), edited)
        plan, approval = self.apply_plan("--resource", "shell_tokens", "--keep-local", "shell_tokens:menu.border-alpha")
        self.assertEqual(self.plan_row(plan, "menu.border-alpha")["decision"], "LOCAL_PRESERVED")
        self.expect_ok(self.apply_cli(approval))
        self.assertEqual(tree(target), edited)
        plan, approval = self.apply_plan("--resource", "shell_tokens", "--prefer-heartchy", "shell_tokens:menu.border-alpha")
        self.assertEqual(self.plan_row(plan, "menu.border-alpha")["decision"], "REPLACEMENT_REQUESTED")
        result = self.apply_cli(approval)
        self.expect_ok(result)
        self.assertEqual(len(json.loads(result.stdout)["changed_files"]), 1)
        ledger = json.loads((self.repo / "build/state/core/ledger.json").read_text())
        self.assertEqual(ledger["owned"]["shell_tokens:menu.border-alpha"]["original"]["value"], .9)
        self.expect_ok(self.effect_cli("rollback"))
        self.assertEqual(tree(target), edited)

    def test_acceptance_stale_inputs_recovery_and_explicit_keep_do_not_create_false_ownership(self):
        target = self.matching_shell_fixture()
        tokens = target / "config/omarchy/shell.toml"
        options = ("--resource", "shell_tokens", "--keep-local", "shell_tokens:menu.border-alpha")
        plan, approval = self.apply_plan(*options)
        self.assertEqual(self.plan_row(plan, "menu.border-alpha")["state_operation"], "none")
        tokens.write_bytes(tokens.read_bytes() + b'# later foreign comment\n')
        before = tree(target)
        self.expect_bad(self.apply_cli(approval), "STALE_OR_INVALID_PLAN")
        self.assertEqual(tree(target), before)
        stale = self.cli("plan", "--candidate", "build/planner-candidate", "--target", "build/simulations/core",
                         "--state-root", "build/state/core", "--format", "json", "--recheck", "build/approved.json", *options)
        self.assertEqual(stale.returncode, 3, stale.stderr)
        self.assertTrue(all(row["decision"] == "BLOCKED" and row["state_operation"] == "none"
                            for row in json.loads(stale.stdout)["entries"]))
        _, approval = self.apply_plan(*options)
        result = self.fault_cli(approval, "after_replace", 0, kill=True)
        self.assertEqual(result.returncode, 97, result.stderr)
        self.assertEqual(tree(target), before)
        self.expect_bad(self.effect_cli("validate"), "RECOVERY_REQUIRED")
        self.expect_ok(self.effect_cli("recover"))
        self.assertFalse((self.repo / "build/state/core/managed.json").exists())
        _, approval = self.apply_plan(*options)
        self.expect_ok(self.apply_cli(approval))
        ledger = json.loads((self.repo / "build/state/core/ledger.json").read_text())
        self.assertNotIn("shell_tokens:menu.border-alpha", ledger["accepted"])
        self.assertEqual(ledger["owned"], {})
        self.assertEqual(tree(target), before)
        self.expect_ok(self.effect_cli("rollback"))
        self.assertEqual(tree(target), before)

    def test_apply_first_preservation_owned_state_noop_and_rollback(self):
        target = self.apply_fixture()
        personal = (target / "config/hypr/looknfeel.lua").read_bytes()
        plan, approval = self.apply_plan("--prefer-heartchy", "shell_intent:bar.transparent", "--prefer-heartchy", "shell_tokens:menu.background-alpha")
        self.assertFalse(plan["blocked"])
        result = self.apply_cli(approval)
        self.expect_ok(result)
        applied = json.loads(result.stdout)
        self.assertEqual(applied["structural_validation"], "PASS")
        self.assertEqual((target / "config/hypr/looknfeel.lua").read_bytes(), LUA_LOAD + personal)
        doc = json.loads((target / "config/omarchy/shell.json").read_text())
        self.assertEqual(doc["bar"]["layout"], {"right": ["stock"]})
        self.assertEqual(doc["idle"], {"enabled": True})
        tokens = (target / "config/omarchy/shell.toml").read_text()
        self.assertIn('background-alpha = 0.75 # keep comment', tokens)
        self.assertIn('base-size = 14', tokens)
        self.expect_ok(self.effect_cli("validate"))
        journal = json.loads((self.repo / applied["journal"]).read_text())
        self.assertEqual(journal["status"], "SUCCESS")
        self.assertTrue(all(f["committed"] for f in journal["files"]))
        self.assertFalse(any((self.repo / "build/state/core/operations").rglob("before/[0-9]*")))
        before = tree(target)
        _, second = self.apply_plan()
        state_before = tree(self.repo / "build/state/core")
        repeat = self.apply_cli(second)
        self.expect_ok(repeat)
        self.assertEqual(json.loads(repeat.stdout)["result"], "NO_CHANGE")
        self.assertEqual(before, tree(target))
        self.assertEqual(state_before, tree(self.repo / "build/state/core"))
        rolled = self.effect_cli("rollback")
        self.expect_ok(rolled)
        self.assertEqual((target / "config/hypr/looknfeel.lua").read_bytes(), personal)
        self.assertFalse((target / "config/hypr/heartchy.lua").exists())
        self.assertEqual(json.loads((target / "config/omarchy/shell.json").read_text())["bar"]["transparent"], False)
        self.assertIn('background-alpha = 0.5 # keep comment', (target / "config/omarchy/shell.toml").read_text())
        before = tree(target)
        self.expect_ok(self.effect_cli("rollback"))
        self.assertEqual(before, tree(target))

    def test_apply_local_preferences_selection_and_stale_plan(self):
        target = self.apply_fixture()
        plan, approval = self.apply_plan("--prefer-heartchy", "shell_tokens:menu.background-alpha")
        self.assertEqual(self.plan_row(plan, "bar.transparent", "shell_intent")["decision"], "LOCAL_PRESERVED")
        self.expect_ok(self.apply_cli(approval))
        self.assertFalse(json.loads((target / "config/omarchy/shell.json").read_text())["bar"]["transparent"])
        _, approval = self.apply_plan("--prefer-heartchy", "shell_intent:bar.transparent")
        look = target / "config/hypr/looknfeel.lua"
        look.write_bytes(look.read_bytes() + b'-- later personal edit\n')
        before = tree(target)
        self.expect_bad(self.apply_cli(approval), "STALE_OR_INVALID_PLAN")
        self.assertEqual(before, tree(target))
        _, approval = self.apply_plan("--prefer-heartchy", "shell_intent:bar.transparent")
        self.expect_ok(self.apply_cli(approval))
        shell = target / "config/omarchy/shell.json"
        doc = json.loads(shell.read_text()); doc["bar"]["transparent"] = False; doc["foreign"] = "later"
        shell.write_text(json.dumps(doc))
        tokens = target / "config/omarchy/shell.toml"
        tokens.write_text(tokens.read_text().replace("background-alpha = 0.75", "background-alpha = 0.9", 1))
        result = self.effect_cli("rollback")
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertIn("LOCAL_PRESERVED", result.stdout)
        self.assertEqual(json.loads(shell.read_text())["foreign"], "later")
        self.expect_ok(self.effect_cli("rollback", "--replace", "shell_tokens:menu.background-alpha"))
        self.assertEqual(json.loads(shell.read_text())["foreign"], "later")

    def test_apply_module_update_local_conflict_and_equivalent_load(self):
        target = self.apply_fixture()
        _, approval = self.apply_plan()
        self.expect_ok(self.apply_cli(approval))
        source = self.repo / "core/hypr/heartchy.lua"
        source.write_bytes(b'-- candidate revision\n' + source.read_bytes())
        self.rehash("core/hypr/heartchy.lua")
        shutil.rmtree(self.repo / "build/planner-candidate")
        self.prepare_planner()
        plan, approval = self.apply_plan()
        self.assertEqual(self.plan_row(plan, "content", "hypr_module")["decision"], "MANAGED_CHANGE")
        self.expect_ok(self.apply_cli(approval))
        module = target / "config/hypr/heartchy.lua"
        module.write_bytes(module.read_bytes() + b'-- user edit\n')
        before = tree(target)
        plan, approval = self.apply_plan()
        self.assertTrue(plan["blocked"])
        self.expect_bad(self.apply_cli(approval), "BLOCKED")
        self.assertEqual(before, tree(target))
        plan, approval = self.apply_plan("--prefer-heartchy", "hypr_module:content")
        self.expect_ok(self.apply_cli(approval))
        self.assertEqual(module.read_bytes(), source.read_bytes())

    def fault_cli(self, approval, phase, index=0, kill=False):
        code = AUDIT_BOOTSTRAP.replace('runpy.run_path(sys.argv[0], run_name="__main__")', '''
    api = runpy.run_path(sys.argv[0], run_name="heartchy_dev_library")
    ns = {"__name__": "heartchy_apply"}
    exec(compile(api["read_project"]("tools/heartchy-apply.py"), "tools/heartchy-apply.py", "exec"), ns)
    from types import SimpleNamespace
    options = SimpleNamespace(command="apply", candidate="build/planner-candidate", target="build/simulations/core", state_root="build/state/core", plan="build/approved.json", approve=sys.argv[1], format="json")
    def fault(where, number):
        if where == sys.argv[2] and number == int(sys.argv[3]):
            if sys.argv[4] == "kill":
                raise SystemExit(97)
            raise OSError("simulated failure")
    code = ns["run"](api, options, fault)
''')
        return subprocess.run(["/usr/bin/python3", "-I", "-B", "-c", code, str(self.repo / "tools/heartchy-dev"), approval, phase, str(index), "kill" if kill else "error"], env=ENV, cwd=self.area, capture_output=True, text=True, timeout=15)

    def test_apply_prepare_partial_failure_journal_recovery_and_death(self):
        target = self.apply_fixture()
        _, approval = self.apply_plan("--prefer-heartchy", "shell_intent")
        original = tree(target)
        result = self.fault_cli(approval, "prepared")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("RECOVERED", result.stderr)
        self.assertEqual(original, tree(target))
        _, approval = self.apply_plan("--prefer-heartchy", "shell_intent")
        result = self.fault_cli(approval, "after_replace", 1)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("RECOVERED", result.stderr)
        self.assertEqual(original, tree(target))
        _, approval = self.apply_plan("--prefer-heartchy", "shell_intent")
        result = self.fault_cli(approval, "after_replace", 0, kill=True)
        self.assertEqual(result.returncode, 97, result.stderr)
        self.expect_bad(self.apply_cli(approval), "RECOVERY_REQUIRED")
        self.expect_bad(self.effect_cli("validate"), "RECOVERY_REQUIRED")
        self.expect_ok(self.effect_cli("recover"))
        self.assertEqual(original, tree(target))
        self.expect_ok(self.effect_cli("recover"))

    def test_apply_routes_permissions_invalid_approval_and_corrupt_state(self):
        target = self.apply_fixture()
        _, approval = self.apply_plan()
        before = tree(target)
        self.expect_bad(self.apply_cli("0" * 64), "approval")
        self.assertEqual(before, tree(target))
        module = target / "config/hypr/heartchy.lua"
        outside = self.area / "outside.lua"; outside.write_text("foreign")
        module.symlink_to(outside)
        self.expect_bad(self.apply_cli(approval), "STALE_OR_INVALID_PLAN")
        self.assertEqual(outside.read_text(), "foreign")
        module.unlink()
        for forbidden in ("/etc", "/usr", "/boot", "build/simulations/../core"):
            self.expect_bad(self.cli("apply", "--candidate", "build/planner-candidate", "--target", forbidden, "--state-root", "build/state/core", "--plan", "build/approved.json", "--approve", approval), "FAIL apply")
        _, approval = self.apply_plan()
        self.expect_ok(self.apply_cli(approval))
        (self.repo / "build/state/core/ledger.json").write_text('{}')
        self.expect_bad(self.effect_cli("rollback"), "RECOVERY_REQUIRED")
        self.assertIn("HEARTCHY_EXEC_AUDIT=[]", self.cli("apply", "--help").stderr)

    def test_rollback_preserves_comments_and_releases_already_removed_load(self):
        target = self.apply_fixture()
        _, approval = self.apply_plan()
        self.expect_ok(self.apply_cli(approval))
        tokens = target / "config/omarchy/shell.toml"
        tokens.write_text(tokens.read_text().replace('border-alpha = 0.65', 'border-alpha = 0.65 # later explanation'))
        look = target / "config/hypr/looknfeel.lua"
        look.write_bytes(look.read_bytes()[len(LUA_LOAD):])
        personal = look.read_bytes()
        result = self.effect_cli("rollback")
        self.expect_ok(result)
        self.assertIn("hypr_connection:load", json.loads(result.stdout)["already_restored"])
        self.assertEqual(look.read_bytes(), personal)
        self.assertFalse((target / "config/hypr/heartchy.lua").exists())
        self.assertIn('# later explanation', tokens.read_text())
        self.assertNotIn('border-alpha =', tokens.read_text())
        self.assertIn('base-size = 14', tokens.read_text())

    def test_rollback_user_module_and_unowned_load_are_not_silently_removed(self):
        target = self.apply_fixture()
        module = target / "config/hypr/heartchy.lua"
        module.write_bytes(b'-- prior unowned module\n')
        look = target / "config/hypr/looknfeel.lua"
        look.write_bytes(b"require 'hypr.heartchy'\n" + look.read_bytes())
        personal = look.read_bytes()
        plan, approval = self.apply_plan("--prefer-heartchy", "hypr_module:content")
        self.assertEqual(self.plan_row(plan, "load", "hypr_connection")["decision"], "NO_CHANGE")
        self.expect_ok(self.apply_cli(approval))
        ledger = json.loads((self.repo / "build/state/core/ledger.json").read_text())
        self.assertNotIn("hypr_connection:load", ledger["owned"])
        self.expect_ok(self.effect_cli("rollback"))
        self.assertEqual(module.read_bytes(), b'-- prior unowned module\n')
        self.assertEqual(look.read_bytes(), personal)
        _, approval = self.apply_plan("--prefer-heartchy", "hypr_module:content")
        self.expect_ok(self.apply_cli(approval))
        module.write_bytes(b'error("must not execute recipient Lua")\n')
        result = self.effect_cli("rollback")
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertEqual(module.read_bytes(), b'error("must not execute recipient Lua")\n')
        self.expect_ok(self.effect_cli("rollback", "--replace", "hypr_module:content"))
        self.assertEqual(module.read_bytes(), b'-- prior unowned module\n')
        self.assertEqual(look.read_bytes(), personal)

    def test_recovery_refuses_external_edit_and_restores_state_after_late_failure(self):
        target = self.apply_fixture()
        original = tree(target)
        for phase, number in (("prepare_image", 1), ("after_replace", 4), ("after_replace", 5)):
            _, approval = self.apply_plan("--prefer-heartchy", "shell_intent")
            result = self.fault_cli(approval, phase, number, kill=True)
            self.assertEqual(result.returncode, 97, result.stderr)
            self.expect_bad(self.apply_cli(approval), "RECOVERY_REQUIRED")
            self.expect_ok(self.effect_cli("recover"))
            self.assertEqual(original, tree(target))
            self.assertFalse((self.repo / "build/state/core/managed.json").exists())
        _, approval = self.apply_plan()
        self.assertEqual(self.fault_cli(approval, "after_replace", 0, kill=True).returncode, 97)
        look = target / "config/hypr/looknfeel.lua"
        post = look.read_bytes()
        look.write_bytes(post + b'-- external edit during interruption\n')
        before = tree(target)
        self.expect_bad(self.effect_cli("recover"), "third-party change")
        self.assertEqual(before, tree(target))
        look.write_bytes(post)
        self.expect_ok(self.effect_cli("recover"))
        self.assertEqual(original, tree(target))

    def local_descriptor(self, config, name="core-local"):
        descriptor = self.repo / "build/local-targets" / name
        descriptor.mkdir(parents=True)
        stock = self.area / "stock"
        if not stock.exists():
            (stock / "config/hypr").mkdir(parents=True)
            (stock / "default/hypr").mkdir(parents=True)
            shutil.copyfile(self.repo / "test/fixtures/planner/lua-first/config/hypr/hyprland.lua", stock / "config/hypr/hyprland.lua")
            shutil.copyfile(self.repo / "test/fixtures/omarchy/bootstrap.lua", stock / "default/hypr/bootstrap.lua")
            shutil.copyfile(self.repo / "test/fixtures/omarchy/defaults.lua", stock / "default/hypr/omarchy.lua")
        contracts = json.loads((self.repo / "test/fixtures/planner/lua-first/target.json").read_text())["contracts"]
        marker = {"schema_version":1, "kind":"heartchy-local-target", "contracts":contracts,
                  "config_root":str(config), "shadow_root":str(config.parent / ".local/state"), "stock_root":str(stock)}
        (descriptor / "target.json").write_text(json.dumps(marker))
        return descriptor, marker

    def test_local_descriptor_is_bound_to_state_and_recovery_not_to_home(self):
        target = self.apply_fixture()
        external = self.area / "local-home/.config"
        shutil.copytree(target / "config", external)
        descriptor, marker = self.local_descriptor(external)
        result = self.cli("plan", "--candidate", "build/planner-candidate", "--target", "build/local-targets/core-local", "--state-root", "build/state/core", "--format", "json")
        self.expect_ok(result)
        path = self.repo / "build/approved.json"; path.write_text(result.stdout)
        args = ["apply", "--candidate", "build/planner-candidate", "--target", "build/local-targets/core-local", "--state-root", "build/state/core", "--plan", "build/approved.json", "--approve", sha(path.read_bytes()), "--format", "json"]
        self.expect_ok(self.cli(*args))
        second = self.area / "other-home/.config"
        shutil.copytree(external, second)
        marker["config_root"] = str(second)
        marker["shadow_root"] = str(second.parent / ".local/state")
        (descriptor / "target.json").write_text(json.dumps(marker))
        first_before, second_before = tree(external), tree(second)
        self.expect_bad(self.cli("rollback", "--target", "build/local-targets/core-local", "--state-root", "build/state/core", "--approve", "rollback"), "RECOVERY_REQUIRED")
        self.expect_bad(self.cli("recover", "--target", "build/local-targets/core-local", "--state-root", "build/state/core", "--approve", "recover"), "RECOVERY_REQUIRED")
        self.assertEqual(first_before, tree(external)); self.assertEqual(second_before, tree(second))
        marker["config_root"] = str(external)
        marker["shadow_root"] = str(external.parent / ".local/state")
        (descriptor / "target.json").write_text(json.dumps(marker))
        self.expect_ok(self.cli("rollback", "--target", "build/local-targets/core-local", "--state-root", "build/state/core", "--approve", "rollback"))
        self.assertFalse((external / "hypr/heartchy.lua").exists())
        for root in ("/etc", "/usr", "/boot", str(self.area / "link")):
            marker["config_root"] = root
            (descriptor / "target.json").write_text(json.dumps(marker))
            if root.endswith("link"):
                Path(root).symlink_to(external, target_is_directory=True)
            before = tree(external)
            result = self.cli("plan", "--candidate", "build/planner-candidate", "--target", "build/local-targets/core-local", "--state-root", "build/state/core", "--format", "json")
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(before, tree(external))

    def test_corrupt_origin_and_plan_decisions_cannot_authorize_other_values(self):
        target = self.apply_fixture()
        _, approval = self.apply_plan("--prefer-heartchy", "shell_intent")
        path = self.repo / "build/approved.json"
        edited = json.loads(path.read_text()); row = self.plan_row(edited, "bar.transparent", "shell_intent")
        row["planned"]["value"] = "forged"
        path.write_text(json.dumps(edited))
        before = tree(target)
        self.expect_bad(self.apply_cli(sha(path.read_bytes())), "STALE_OR_INVALID_PLAN")
        self.assertEqual(before, tree(target))
        _, approval = self.apply_plan("--prefer-heartchy", "shell_intent")
        self.expect_ok(self.apply_cli(approval))
        ledger_path = self.repo / "build/state/core/ledger.json"
        ledger = json.loads(ledger_path.read_text())
        ledger["owned"]["shell_intent:bar.transparent"]["original"] = {"state":"absent"}
        ledger_path.write_text(json.dumps(ledger))
        before = tree(target)
        self.expect_bad(self.effect_cli("rollback"), "RECOVERY_REQUIRED")
        self.assertEqual(before, tree(target))

    def test_recovery_detects_permission_edit_and_respects_lua_commit_order(self):
        target = self.apply_fixture()
        original = tree(target)
        _, approval = self.apply_plan()
        self.assertEqual(self.fault_cli(approval, "after_replace", 0, kill=True).returncode, 97)
        module = target / "config/hypr/heartchy.lua"
        look = target / "config/hypr/looknfeel.lua"
        self.assertTrue(module.exists())
        self.assertFalse(look.read_bytes().startswith(LUA_LOAD))
        module.chmod(0o600)
        before = tree(target)
        self.expect_bad(self.effect_cli("recover"), "file mode change")
        self.assertEqual(before, tree(target))
        module.chmod(0o644)
        self.expect_ok(self.effect_cli("recover"))
        self.assertEqual(original, tree(target))
        # After both Lua commits, a load always has its module present.
        _, approval = self.apply_plan()
        self.assertEqual(self.fault_cli(approval, "after_replace", 1, kill=True).returncode, 97)
        self.assertTrue(module.exists())
        self.assertTrue(look.read_bytes().startswith(LUA_LOAD))
        self.expect_ok(self.effect_cli("recover"))
        self.assertEqual(original, tree(target))

    def test_apply_effect_scope_help_invalid_commands_and_ambiguous_toml(self):
        target = self.apply_fixture()
        _, approval = self.apply_plan()
        state = self.repo / "build/state/core"
        before = tree(SANDBOX, excluded=(target, state))
        result = self.apply_cli(approval)
        self.expect_ok(result)
        claims = list((target.parent / ".heartchy-authorities").glob("*.json"))
        self.assertEqual(len(claims), 1)
        self.assertEqual(json.loads(claims[0].read_text()), {"schema_version": 1, "state_root": str(state)})
        self.assertEqual(before, tree(SANDBOX, excluded=(target, state, claims[0])))
        self.assertIn('"/usr/bin/lua"', result.stderr)
        self.assertNotIn('systemctl', result.stderr)
        before = tree(SANDBOX)
        for command in ("apply", "rollback", "recover", "validate"):
            self.expect_ok(self.cli(command, "--help"))
            invalid = self.cli(command, "--force")
            self.assertEqual(invalid.returncode, 2)
            self.assertIn("HEARTCHY_EXEC_AUDIT=[]", invalid.stderr)
        self.assertEqual(before, tree(SANDBOX))
        # Valid general TOML can still be incompatible with Shell's parser.
        tokens = target / "config/omarchy/shell.toml"
        tokens.write_text(tokens.read_text().replace('background-alpha = 0.5', 'background-alpha = 5e-1', 1))
        plan, approval = self.apply_plan()
        self.assertTrue(plan["blocked"])
        before = tree(target)
        self.expect_bad(self.apply_cli(approval), "BLOCKED")
        self.assertEqual(before, tree(target))

    def test_explicit_replacement_keeps_the_latest_local_preference_recoverable(self):
        target = self.apply_fixture()
        _, approval = self.apply_plan("--prefer-heartchy", "shell_tokens:menu.background-alpha")
        self.expect_ok(self.apply_cli(approval))
        tokens = target / "config/omarchy/shell.toml"
        tokens.write_text(tokens.read_text().replace("background-alpha = 0.75", "background-alpha = 0.9", 1))
        _, approval = self.apply_plan("--prefer-heartchy", "shell_tokens:menu.background-alpha")
        self.expect_ok(self.apply_cli(approval))
        self.assertIn("background-alpha = 0.75 # keep comment", tokens.read_text())
        self.expect_ok(self.effect_cli("rollback"))
        self.assertIn("background-alpha = 0.9 # keep comment", tokens.read_text())
        self.assertIn("base-size = 14", tokens.read_text())

    def updates_model(self):
        module = runpy.run_path(str(self.repo / "mockups/updates.py"))
        releases, installed = module["parse_catalog"]((self.repo / "mockups/updates.json").read_text())
        return module, module["Model"](releases, installed)

    def test_updates_fictional_catalog_contract(self):
        module, model = self.updates_model()
        self.assertEqual([r.version for r in model.releases], ["0.3.1", "0.3.0", "0.2.2", "0.2.1", "0.2.0", "0.1.0"])
        self.assertEqual(sum(r.version == model.installed for r in model.releases), 1)
        self.assertEqual({r.height for r in model.releases}, {4, 6})
        original = json.loads((self.repo / "mockups/updates.json").read_text())
        variants = []
        d = json.loads(json.dumps(original)); d["fictional"] = False; variants.append(d)
        d = json.loads(json.dumps(original)); d["installed"] = ["0.2.0", "0.3.0"]; variants.append(d)
        d = json.loads(json.dumps(original)); d["installed"] = "9.9.9"; variants.append(d)
        d = json.loads(json.dumps(original)); d["releases"].reverse(); variants.append(d)
        d = json.loads(json.dumps(original)); d["releases"][0] = d["releases"][1]; variants.append(d)
        d = json.loads(json.dumps(original)); del d["releases"][1]["summary"]; variants.append(d)
        d = json.loads(json.dumps(original)); d["releases"][0]["summary"] = "unexpected"; variants.append(d)
        d = json.loads(json.dumps(original)); d["releases"][0]["date"] = "2026-02-30"; variants.append(d)
        d = json.loads(json.dumps(original)); d["releases"][0]["name"] = "\x1b[2J"; variants.append(d)
        for variant in variants:
            with self.subTest(variant=variant):
                with self.assertRaises(ValueError):
                    module["parse_catalog"](json.dumps(variant))
        with self.assertRaises(ValueError):
            module["parse_catalog"]('{"schema_version":1,"schema_version":1}')

    def test_updates_keyboard_flow_cancel_progress_and_noop(self):
        module, m = self.updates_model()
        original = m.installed
        m.event("enter"); self.assertEqual(m.screen, "omarchy")
        m.event("back"); m.event("next"); m.event("enter")
        self.assertEqual(m.screen, "releases")
        m.event("next"); self.assertEqual(m.current.version, "0.3.0")
        m.event("enter"); self.assertEqual(m.screen, "report"); m.event("enter"); self.assertEqual((m.screen, m.button), ("confirm", 1))
        m.event("enter"); self.assertEqual((m.screen, m.installed), ("releases", original))
        m.event("enter"); m.event("enter"); m.event("prev"); m.event("enter", 10)
        self.assertEqual(m.screen, "progress")
        m.tick(11); self.assertGreater(m.progress, 0); self.assertLess(m.progress, 1)
        m.event("back"); m.tick(100)
        self.assertEqual((m.screen, m.installed), ("releases", original))
        m.event("enter"); m.event("enter"); m.event("prev"); m.event("enter", 20)
        m.tick(20 + module["SIMULATION_SECONDS"])
        self.assertEqual((m.screen, m.installed), ("result", "0.3.0"))
        self.assertEqual(sum(r.version == m.installed for r in m.releases), 1)
        m.event("enter"); m.event("enter"); m.event("enter"); m.event("prev"); m.event("enter")
        self.assertEqual((m.screen, m.no_change, m.installed), ("result", True, "0.3.0"))
        m.event("enter"); m.event("back"); m.event("back")
        self.assertTrue(m.closed)

    def test_updates_multiline_card_geometry_and_hierarchy(self):
        module, m = self.updates_model()
        for width in (64, 90, 110):
            statuses = []
            for r in m.releases:
                lines = module["card_text"](r, m.installed, width).splitlines()
                self.assertEqual(len(lines), r.height)
                self.assertTrue(all(len(line) == width for line in lines))
                self.assertIn(r.name + "  " + r.version, lines[1])
                self.assertIn(r.date, lines[-2])
                status = "● Instalada" if r.version == m.installed else "○ No instalada"
                self.assertTrue(lines[1].endswith(status + " │"))
                statuses.append(status)
                if r.kind == "major":
                    self.assertIn(r.summary[:25], lines[2])
                else:
                    self.assertFalse(r.summary)
                    self.assertEqual(lines[2].strip("│ "), "Publicada " + r.date)
            self.assertEqual(statuses.count("● Instalada"), 1)
        with self.assertRaises(ValueError):
            module["card_text"](m.current, m.installed, 10)

    def test_updates_assets_theme_scope_and_long_cards(self):
        module, m = self.updates_model()
        provenance = json.loads((self.repo / "mockups/assets/provenance.json").read_text())
        for name in ("omarchy", "heartchy"):
            item = provenance[name]
            asset = self.repo / "mockups/assets" / item["file"]
            self.assertEqual(sha(asset.read_bytes()), item["sha256"])
            rows = module["logo"](name.upper())
            self.assertEqual(module["heading"](name.upper(), 120, 44), asset.read_text().rstrip("\n"))
            self.assertNotIn("█", module["heading"](name.upper(), 60, 28))
            self.assertNotIn("█", module["heading"](name.upper(), 120, 20))
            self.assertTrue(any("█" in row for row in rows))
        for background, foreground in (("#101315", "#cacccc"), ("#eeeeee", "#202020")):
            raw = f'hl.env("BACKGROUND", "{background}")\nhl.env("FOREGROUND", "{foreground}")\n'
            raw += 'hl.env("GUM_CONFIRM_SELECTED_BACKGROUND", "#aa7788")\n'
            raw += 'hl.env("FZF_DEFAULT_COMMAND", "dangerous")\nos.execute("do not execute")\n'
            colors = module["theme_colors"](raw)
            self.assertEqual(colors, {"BACKGROUND": background, "FOREGROUND": foreground, "GUM_CONFIRM_SELECTED_BACKGROUND": "#aa7788"})
            ui = module["NativeUI"](m, colors)
            self.assertEqual(ui.env["BACKGROUND"], background)
            self.assertNotIn("FZF_DEFAULT_COMMAND", ui.env)
            self.assertNotIn("GUM_CONFIRM_SELECTED_FOREGROUND", ui.env)
        for raw in ('hl.env("BACKGROUND", "not-a-color")', 'hl.env("BACKGROUND", "999")'):
            with self.assertRaises(ValueError):
                module["theme_colors"](raw)
        r = module["Release"]("Heartchy Gestión y configuración de preferencias compartidas", "0.3.0", "major", "2026-11-15",
                              "Selección y navegación con acentos: área común, módulos y controles. " * 3)
        for width in (36, 54, 100, 120):
            lines = module["card_text"](r, m.installed, width).splitlines()
            self.assertTrue(all(len(line) == width for line in lines))
            self.assertEqual(sum("○ No instalada" in line for line in lines), 1)
            self.assertIn("0.3.0", " ".join(lines))
            self.assertNotIn("HITO PRINCIPAL", "\n".join(lines))
            self.assertNotIn("MEJORA", "\n".join(lines))

    def test_updates_listing_nul_identity_query_resize_and_actions(self):
        module, m = self.updates_model()
        m.screen, m.selected, m.query = "releases", 1, "Base"
        commands = []
        class OutputUI(module["NativeUI"]):
            response = "Base\0enter\0" + "0.3.0\0"
            code = 0
            def clear(self):
                pass
            def tool(self, args, payload=None, capture=False):
                commands.append(args)
                out = "0.3.1\0" + "0.3.0\0" if any(a.startswith("--filter=") for a in args) else self.response
                return subprocess.CompletedProcess(args, 0 if any(a.startswith("--filter=") for a in args) else self.code, out)
        ui = OutputUI(m, {})
        ui.listing()
        self.assertEqual((m.current.version, m.query, m.screen), ("0.3.0", "Base", "report"))
        args = commands[-1]
        self.assertEqual(args[args.index("--query") + 1], "Base")
        self.assertIn("--accept-nth=1", args)
        self.assertIn("--print0", args)
        self.assertIn("--margin=1,0,0,0", args)
        self.assertEqual(args[args.index("--header") + 1], module["banner"]("HEARTCHY", shutil.get_terminal_size().columns - 1, shutil.get_terminal_size().lines) + "\n")
        self.assertIn("load:pos(2)", args[args.index("--bind") + 1])
        m.event("back")
        ui.response = "Base\0\0RESIZE\0" + "0.3.0\0"
        ui.listing()
        self.assertEqual((m.current.version, m.query, m.screen), ("0.3.0", "Base", "releases"))
        ui.response = "Base\0esc\0" + "0.3.1\0"
        ui.listing()
        self.assertEqual((m.current.version, m.query, m.screen), ("0.3.1", "Base", "selector"))
        for key, expected in (("", "releases"), ("enter", "releases"), ("esc", "selector")):
            ui.code = 1
            ui.response = "no-match\0" + key + "\0" + ("RESIZE\0" if key == "" else "")
            m.screen = "releases"
            ui.listing()
            self.assertEqual((m.screen, m.query, m.closed), (expected, "no-match", False))
        ui.code = 0
        ui.response = "\0".join(("Base", "double-click", "0.3.0", ""))
        m.screen = "releases"
        ui.listing()
        self.assertEqual((m.screen, m.current.version), ("report", "0.3.0"))
        for out in ("Base\0enter\0decorated title\0", "Base\0enter\00.3.0", "Base\0unknown\00.3.0\0"):
            ui.response = out
            with self.assertRaises(ValueError):
                ui.listing()
        m.screen, m.selected = "confirm", 5
        self.assertIn("Versión anterior", m.action)
        m.selected = 0
        self.assertEqual(m.action, "Actualizar de 0.2.0 a 0.3.1")
        m.installed = None
        self.assertEqual(m.action, "Instalar Heartchy 0.3.1")

    def test_updates_protocol_reply_is_not_a_user_key(self):
        module, _ = self.updates_model()
        parse = module["progress_keys"]
        self.assertEqual(parse(b"", b"\x1b[?0u"), (False, b""))
        cancel, pending = parse(b"", b"\x1b[?")
        self.assertEqual((cancel, pending), (False, b"\x1b[?"))
        self.assertEqual(parse(pending, b"0uabc"), (False, b""))
        self.assertEqual(parse(b"", b"\x1b[?1u\x03"), (True, b""))
        self.assertEqual(parse(b"", b"\x1b"), (False, b"\x1b"))
        replies = b"\x1b[?2026;2$y\x1b[?2027;0$y\x1b]11;rgb:0000/0000/0000\x07\x1b[?0u"
        self.assertEqual(parse(b"", replies), (False, b""))
        for split in range(1, len(replies)):
            cancel, pending = parse(b"", replies[:split])
            self.assertFalse(cancel, split)
            self.assertEqual(parse(pending, replies[split:]), (False, b""), split)

    def test_updates_spin_protocol_cancellation_and_terminal_restoration(self):
        if not shutil.which("gum", path=ENV["PATH"]):
            self.skipTest("NOT_RUN: Gum unavailable")
        entry = self.area / "progress-fixture.py"
        entry.write_text('import runpy,time\n'
            f'u=runpy.run_path({str(self.repo / "mockups/updates.py")!r})\n'
            f'rs,installed=u["parse_catalog"](open({str(self.repo / "mockups/updates.json")!r}).read())\n'
            'm=u["Model"](rs,installed);m.screen="progress";m.started=time.monotonic()\n'
            'try:u["NativeUI"](m,{}).run()\n'
            'except KeyboardInterrupt:pass\n'
            'print("RESTORED_INSTALLED="+m.installed)\n')
        home = self.area / "home"
        home.mkdir()
        before = tree(self.area)
        def sleep_processes():
            found = set()
            for process_dir in Path("/proc").iterdir():
                if process_dir.name.isdigit():
                    try:
                        if (process_dir / "comm").read_text().strip() == "sleep":
                            found.add(process_dir.name)
                    except FileNotFoundError:
                        pass
            return found
        sleepers = sleep_processes()
        for key in (b"\x1b", b"\x03"):
            with self.subTest(key=key):
                master, slave = pty.openpty()
                fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 44, 120, 0, 0))
                original = termios.tcgetattr(slave)
                process = subprocess.Popen(["/usr/bin/python3", "-I", "-B", "-c", MOCKUP_AUDIT, str(entry)],
                    stdin=slave, stdout=slave, stderr=slave, env={**ENV, "HOME": str(home), "TERM": "xterm-256color"},
                    start_new_session=True, preexec_fn=lambda: fcntl.ioctl(slave, termios.TIOCSCTTY, 0))
                os.close(slave)
                output = bytearray()
                try:
                    deadline = time.monotonic() + 4
                    while time.monotonic() < deadline and b"\x1b[?u" not in output:
                        if select.select([master], [], [], .05)[0]:
                            output.extend(read_mockup_pty(master))
                    self.assertIn(b"\x1b[?u", output, "Gum spin itself must emit the query")
                    os.write(master, b"\x1b[?")
                    time.sleep(.02)
                    os.write(master, b"0u")
                    time.sleep(.05)
                    self.assertIsNone(process.poll(), "protocol response cancelled progress")
                    os.write(master, key)
                    deadline = time.monotonic() + 4
                    while time.monotonic() < deadline:
                        if select.select([master], [], [], .05)[0]:
                            try:
                                output.extend(read_mockup_pty(master))
                            except OSError:
                                break
                    try:
                        code = process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        self.fail("spinner did not cancel: " + output.decode(errors="replace")[-2500:] + " termios=" + repr(termios.tcgetattr(master)))
                    self.assertEqual(code, 0, output.decode(errors="replace"))
                    self.assertIn(b"RESTORED_INSTALLED=0.2.0", output)
                    self.assertNotIn(b"^[[?0u", output)
                    self.assertNotIn(b"\x1b[?0u", output)
                    self.assertEqual(termios.tcgetattr(master), original)
                    self.assertEqual(sleep_processes(), sleepers, "cancelled mockup left a sleep process")
                finally:
                    if process.poll() is None:
                        os.killpg(process.pid, signal.SIGTERM)
                        process.wait(timeout=3)
                    os.close(master)
        self.assertEqual(before, tree(self.area))

    def test_updates_native_adapter_flow_and_cancel(self):
        module, m = self.updates_model()
        commands = []
        class StubUI(module["NativeUI"]):
            accept = True
            def clear(self):
                pass
            def selector(self):
                self.model.selector = 1
                self.model.event("enter")
            def tool(self, arguments, payload=None, capture=False):
                commands.append((arguments, payload))
                out, code = "", 0
                if arguments[1] == "choose":
                    out = "Salir de la maqueta" if self.model.screen == "result" else ("Página siguiente" if "Página siguiente" in arguments else "Revisar confirmación")
                elif arguments[0] == "/usr/bin/fzf":
                    out = "\0".join(r.version for r in m.releases) + "\0" if any(a.startswith("--filter=") for a in arguments) else "\0".join(("", "enter", "0.3.0", ""))
                elif arguments[1] == "confirm":
                    code = 0 if self.accept else 1
                return subprocess.CompletedProcess(arguments, code, out)
            def spin(self, arguments):
                return self.tool(arguments)
        ui = StubUI(m)
        ui.selector(); self.assertEqual(m.screen, "releases")
        ui.listing(); self.assertEqual((m.screen, m.current.version), ("report", "0.3.0"))
        ui.report(); ui.accept = False; ui.confirm()
        self.assertEqual((m.screen, m.installed), ("releases", "0.2.0"))
        ui.listing(); ui.report(); ui.accept = True; ui.confirm(); ui.progress(); ui.result()
        self.assertEqual((m.closed, m.installed), (True, "0.3.0"))
        self.assertEqual(set(args[0] for args, _ in commands), {"/usr/bin/gum", "/usr/bin/fzf"})
        fzf, payload = next((args, payload) for args, payload in commands if args[0] == "/usr/bin/fzf" and "--bind" in args)
        self.assertEqual(len(payload.rstrip("\0").split("\0")), 6)
        self.assertIn("--read0", fzf); self.assertIn("--no-sort", fzf)
        self.assertNotIn("--highlight-line", fzf)
        colors = fzf[fzf.index("--color") + 1]
        self.assertIn("bg+:-1", colors)
        for name in ("OMARCHY", "HEARTCHY"):
            rows = module["logo"](name)
            self.assertEqual(len(rows), 10)
            self.assertEqual(module["heading"](name, 120, 44), "\n".join(rows))
            self.assertIn("cabecera compacta", module["heading"](name, 60, 30))
        self.assertTrue(fzf[fzf.index("--bind") + 1].startswith("load:pos(1)+offset-middle"))
        fzf_calls = [args for args, _ in commands if args[0] == "/usr/bin/fzf" and "--bind" in args]
        self.assertTrue(fzf_calls[-1][fzf_calls[-1].index("--bind") + 1].startswith("load:pos(2)+offset-middle"))
        ui.model.selector = 1
        ui.model.screen = "selector"
        ui.selector()
        self.assertEqual((ui.model.selector, ui.model.screen), (1, "releases"))
        spin = next(args for args, _ in commands if args[1] == "spin")
        self.assertEqual(spin[-3:], ["--", "/usr/bin/sleep", "8.0"])
        self.assertEqual(ui.env["HOME"], "/nonexistent")
        self.assertFalse(any(k.startswith(("FZF_", "GUM_")) for k in ui.env))
        class BadUI(StubUI):
            def tool(self, args, payload=None, capture=False):
                return subprocess.CompletedProcess(args, 0, "not-a-version")
        _, m = self.updates_model(); m.screen = "releases"
        with self.assertRaises(ValueError):
            BadUI(m).listing()
        self.assertEqual(m.installed, "0.2.0")

    def mockup_command(self):
        return ["/usr/bin/python3", "-I", "-B", "-c", MOCKUP_AUDIT, str(self.repo / "bin/heartchy-updates-mockup")]

    def test_updates_report_contract_layout_and_return(self):
        module, m = self.updates_model()
        original = json.loads((self.repo / "mockups/updates.json").read_text())
        for field, value in (("apps", "not a list"), ("notes", ["\x1b[2J"]), ("changes", ["x"] * 5)):
            invalid = json.loads(json.dumps(original)); invalid["releases"][0]["report"][field] = value
            with self.assertRaises(ValueError):
                module["parse_catalog"](json.dumps(invalid))
        for r in m.releases:
            m.selected = m.releases.index(r)
            for width in (30, 92, 118):
                lines = module["report_lines"](m, width)
                self.assertTrue(all(len(line) <= width for line in lines))
                if width >= 86:
                    half = (width - 4) // 2
                    # Read each column in order; a row-major string interleaves
                    # unrelated prose when a bullet wraps onto a second row.
                    text = " ".join(" ".join(line[:half] for line in lines).split()) + " " + " ".join(" ".join(line[half+4:] for line in lines).split())
                else:
                    text = " ".join(" ".join(lines).split())
                self.assertIn(r.version, text)
                for group in (r.changes, r.apps, r.components, r.fixes, r.notes):
                    for item in group:
                        self.assertTrue(item in text or item in " ".join(" ".join(lines).split()), item)
        m.screen, m.query, m.selected = "releases", "Base", 1
        m.event("enter"); self.assertEqual(m.screen, "report")
        m.event("back")
        self.assertEqual((m.screen, m.query, m.current.version, m.installed), ("releases", "Base", "0.3.0", "0.2.0"))
        m.event("enter"); m.event("enter")
        self.assertEqual((m.screen, m.button), ("confirm", 1))
        m.event("enter"); self.assertEqual(m.screen, "releases")

    def test_updates_shutdown_clears_before_palette_restore(self):
        module, m = self.updates_model()
        ui = module["NativeUI"](m, {})
        ui.indexed_colors = True
        ui.saved_slots = {16: "rgb:1111/2222/3333"}
        writes, order = [], []
        class Watch:
            def close(self): order.append("close")
        class Thread:
            def join(self, timeout): order.append("join")
            def is_alive(self): return False
        ui.theme_watch, ui.theme_thread = Watch(), Thread()
        with patch.object(os, "write", side_effect=lambda fd, data: (order.append("write"), writes.append(data))):
            ui.stop_theme()
        self.assertEqual(order, ["join", "close", "write"])
        self.assertTrue(ui.theme_stop.is_set())
        self.assertFalse(ui.indexed_colors)
        self.assertEqual(len(writes), 1)
        sequence = writes[0]
        self.assertLess(sequence.index(b"\x1b[2J"), sequence.index(b"\x1b]4;"))
        self.assertTrue(sequence.startswith(b"\x1b[?2026h"))
        self.assertTrue(sequence.endswith(b"\x1b[?2026l"))
        self.assertNotIn(b"\x1b]104", sequence, "must restore observed slots, not reset user colors")

    def test_updates_report_pagination_resize_and_cancel(self):
        module, m = self.updates_model()
        m.screen, m.query, m.selected = "report", "Base", 1
        panels, options = [], []
        sizes = [os.terminal_size((130, 39)), os.terminal_size((60, 28))]
        class ReportUI(module["NativeUI"]):
            def brand(self): pass
            def panel(self, lines, padding="1 2"): panels.append(lines)
            def tool(self, args, payload=None, capture=False):
                options.append(args)
                # First page uses a short viewport to force pagination; then
                # reduce its width and verify the next page is recomputed.
                return subprocess.CompletedProcess(args, 0,
                    "Página siguiente" if len(options) == 1 else "Volver al listado")
        with patch.object(shutil, "get_terminal_size", side_effect=[os.terminal_size((130, 32)), sizes[1]]):
            ReportUI(m, {}).report()
        self.assertIn("Página siguiente", options[0])
        self.assertTrue(all(len(line) <= 52 for line in panels[1]))
        self.assertLessEqual(len(panels[1]), 6)
        self.assertEqual((m.screen, m.query, m.current.version), ("releases", "Base", "0.3.0"))

    def test_updates_terminal_close_cleans_children_from_each_screen(self):
        if not all(shutil.which(name, path=ENV["PATH"]) for name in ("gum", "fzf", "sleep")):
            self.skipTest("NOT_RUN: native widgets missing")
        entry = self.area / "closing.py"
        entry.write_text('import runpy,time,sys\n'
            f'u=runpy.run_path({str(self.repo / "mockups/updates.py")!r})\n'
            'm=u["Model"](*u["parse_catalog"](u["CATALOG"].read_text()));m.screen=sys.argv[-1];m.started=time.monotonic()\n'
            'ui=u["NativeUI"](m,colors={},animation=False)\n'
            'try:ui.run()\n'
            'except KeyboardInterrupt:print("CLOSED")\n'
            'print("CLEAN="+str(ui.child is None and ui.theme_stop.is_set()))\n')
        screens = {"selector": b"Esc salir", "releases": b"Buscar versi", "report": b"Revisar confirmaci",
                   "confirm": b"Cancelar", "progress": b"Instalaci", "result": b"Salir de la maqueta"}
        for screen, ready in screens.items():
            master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 39, 130, 0, 0))
            original = termios.tcgetattr(slave)
            process = subprocess.Popen(["/usr/bin/python3", "-I", "-B", "-c", MOCKUP_AUDIT, str(entry), screen],
                env={**ENV, "HOME": str(self.area / "home"), "TERM": "xterm-256color"}, stdin=slave, stdout=slave, stderr=slave,
                start_new_session=True, preexec_fn=lambda: fcntl.ioctl(slave, termios.TIOCSCTTY, 0))
            os.close(slave)
            data, descendants = bytearray(), set()
            def collect(pid):
                task = Path("/proc") / str(pid) / "task"
                if task.exists():
                    for t in task.iterdir():
                        for child in (t / "children").read_text().split():
                            if child not in descendants:
                                descendants.add(child); collect(child)
            try:
                deadline = time.monotonic() + 5
                while ready not in data and time.monotonic() < deadline:
                    if select.select([master], [], [], .02)[0]:
                        try: data.extend(read_mockup_pty(master))
                        except OSError: break
                self.assertIn(ready, data, screen)
                time.sleep(.15); collect(process.pid)
                os.kill(process.pid, signal.SIGHUP if screen in ("progress", "report", "result") else signal.SIGTERM)
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    if select.select([master], [], [], .02)[0]:
                        try: data.extend(read_mockup_pty(master))
                        except OSError: break
                    if process.poll() is not None: break
                self.assertEqual(process.wait(timeout=1), 0, screen)
                self.assertIn(b"CLEAN=True", data)
                self.assertEqual(termios.tcgetattr(master), original, screen)
                self.assertFalse(any((Path("/proc") / pid).exists() for pid in descendants), (screen, descendants))
                self.assertNotIn(b"^[[?0u", data)
                end = data.rfind(b"\x1b[?2026h\x1b[0m\x1b[2J")
                self.assertGreater(end, 0)
                self.assertNotIn(b";#", data[end:], "late theme paint after cleanup")
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL); process.wait()
                os.close(master)

    def test_updates_refined_wordmark_and_wipe_geometry(self):
        module, _ = self.updates_model()
        assets = self.repo / "mockups/assets"
        provenance = json.loads((assets / "provenance.json").read_text())
        art, stock = module["logo"]("HEARTCHY"), module["logo"]("OMARCHY")
        self.assertEqual(sha((assets / "heartchy.txt").read_bytes()), provenance["heartchy"]["sha256"])
        self.assertEqual(sha((assets / "omarchy.txt").read_bytes()), "f98c966b1670d71ffc26620a6ff885a73ab355b370bff6082cea3215ee580a29")
        self.assertEqual((len(art), max(map(len, art))), (10, 97))
        self.assertLessEqual(set("".join(art)), set(" ▄▀█"))
        # Compare the borrowed glyphs, not just a provenance claim.
        positions = ((0, 12, 59, 71), (26, 36, 27, 37), (38, 48, 38, 48),
                     (63, 72, 50, 59), (74, 86, 59, 71), (88, 97, 72, 81))
        for left, right, start, end in positions:
            self.assertEqual([r.ljust(97)[left:right] for r in art],
                             [r.ljust(81)[start:end] for r in stock])
        # A centered stem, three cells wide, stays continuous below the T beam.
        for row in art[3:8]:
            self.assertEqual(row[50:61], "    ███    ")
        for before, after in (("OMARCHY", "HEARTCHY"), ("HEARTCHY", "OMARCHY")):
            first = module["wipe_rows"](before, after, 0)
            final = module["wipe_rows"](before, after, 1)
            self.assertEqual(["".join(c for c, _ in row) for row in first], [r.ljust(97) for r in module["logo"](before)])
            self.assertEqual(["".join(c for c, _ in row) for row in final], [r.ljust(97) for r in module["logo"](after)])
            frames = [module["wipe_rows"](before, after, n / 8) for n in range(9)]
            self.assertTrue(all(len(row) == 97 and all(c in " ▄▀█" for c, _ in row) for f in frames for row in f))
            for r in range(10):
                for c in range(97):
                    weights = [f[r][c][1] for f in frames]
                    self.assertEqual(weights, sorted(weights))
                    old, new = module["logo"](before)[r].ljust(97)[c], module["logo"](after)[r].ljust(97)[c]
                    if old == new:
                        self.assertTrue(all(f[r][c][0] == old for f in frames), "shared strokes must remain stable")

    def test_updates_preview_themes_are_readonly_color_overrides(self):
        module, model = self.updates_model()
        themes = self.area / "stock/themes"
        templates = themes.parent / "default/themed"
        templates.mkdir(parents=True)
        (templates / "gum_env.lua.tpl").write_text('hl.env("FOREGROUND", "{{ foreground }}")\n'
            'hl.env("BACKGROUND", "{{ background }}")\n'
            'hl.env("GUM_CHOOSE_CURSOR_FOREGROUND", "{{ accent }}")\n'
            'hl.env("GUM_CONFIRM_SELECTED_BACKGROUND", "{{ selection_background }}")\n')
        (templates / "alacritty.toml.tpl").write_text('[colors.primary]\nbackground="{{ background }}"\n'
            'foreground="{{ foreground }}"\n[colors.selection]\ntext="{{ selection_foreground }}"\nbackground="{{ selection_background }}"\n')
        palettes = (("dark", "#121212", "#bebebe", "#e68e0d"), ("light", "#eff1f5", "#4c4f69", "#1e66f5"),
                    ("green", "#0b0c16", "#ddf7ff", "#82fb9c"), ("extreme", "#000000", "#ffffff", "#8d8d8d"))
        for name, bg, fg, accent in palettes:
            (themes / name).mkdir(parents=True)
            (themes / name / "colors.toml").write_text(f'background="{bg}"\nforeground="{fg}"\naccent="{accent}"\nselection="{accent}"\nbright_foreground="{fg}"\n')
        before = tree(self.area)
        for name, bg, fg, accent in palettes:
            colors, overrides = module["preview_theme"](name, themes)
            self.assertEqual((colors["BACKGROUND"], colors["FOREGROUND"], colors["GUM_CHOOSE_CURSOR_FOREGROUND"]), (bg, fg, accent))
            self.assertTrue(all(re.fullmatch(r'colors\.[a-z_.]+="#[0-9a-fA-F]{6}"', x) for x in overrides))
            ui = module["NativeUI"](model, colors)
            self.assertNotEqual(ui.pink, ui.muted_pink)
            for shade in (ui.pink, ui.muted_pink):
                self.assertGreaterEqual(module["contrast"](shade, bg), 4.5)
            self.assertEqual(ui.env["FOREGROUND"], fg, "Heartchy identity must not recolor stock text")
            with patch.dict(module["window_command"].__globals__, {"preview_theme": lambda name: (colors, overrides)}):
                argv = module["window_command"](name, False)
            self.assertEqual(argv[argv.index("--class") + 1], "TUI.float")
            self.assertEqual(argv[-3:], ["--preview-theme", name, "--no-animation"])
            self.assertEqual(argv.count("--option"), len(overrides))
            self.assertTrue(all(argv[i+1].startswith("colors.") for i, x in enumerate(argv) if x == "--option"))
        for invalid in ("../light", "/etc", "A", "light;touch", "light/other"):
            with self.assertRaises(ValueError):
                module["preview_theme"](invalid, themes)
        self.assertEqual(tree(self.area), before)
        outside = self.area / "outside"
        outside.mkdir(); (themes / "escape").symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "fuera"):
            module["preview_theme"]("escape", themes)
        (templates / "alacritty.toml.tpl").write_text('[window]\nopacity=0.5\n')
        with self.assertRaisesRegex(ValueError, "sólo permite colores"):
            module["preview_theme"]("dark", themes)

    def test_updates_selector_keys_protocol_and_wipe_fallback(self):
        module, _ = self.updates_model()
        parse = module["selector_keys"]
        self.assertEqual(parse(b"", b"\x1b[B\r"), (["next", "enter"], b""))
        self.assertEqual(parse(b"", b"\x1b[D\x1b[A"), (["prev", "prev"], b""))
        self.assertEqual(parse(b"", b"\x1b", True), (["back"], b""))
        responses = (b"\x1b[?0u\x1b[?2026;2$y\x1b]11;rgb:0000/0000/0000\x07\x1b]0;jk title\x07"
                     b"\x1bP1$rj\r\x1b\\\x1b^kj\x1b\\\x1b_kj\x1b\\\x1bXjk\x1b\\")
        for cut in range(len(responses) + 1):
            events, pending = parse(b"", responses[:cut])
            final, pending = parse(pending, responses[cut:] + b"\r")
            self.assertEqual(events + final, ["enter"], cut)
            self.assertEqual(pending, b"")
        for prefix, end in ((b"\x1bP", b"\x1b\\"), (b"\x1b]", b"\x07")):
            events, pending = parse(b"", prefix + b"a" * 700)
            self.assertEqual(events, [])
            self.assertLess(len(pending), 512)
            self.assertEqual(parse(pending, b"jk\r" + end + b"\r"), (["enter"], b""))
        self.assertTrue(.3 <= module["WIPE_SECONDS"] <= .5)
        self.assertLessEqual(module["WIPE_FRAMES"], 20)
        self.assertIn("--no-animation", module["window_command"](animation=False))
        self.assertNotIn("--no-animation", module["window_command"]())

    def test_updates_selector_live_focus_interrupt_and_terminal_restoration(self):
        module, _ = self.updates_model()
        if not shutil.which("gum", path=ENV["PATH"]):
            self.skipTest("NOT_RUN: Gum unavailable")
        home = self.area / "home"; home.mkdir()
        for animation in (True, False):
            with self.subTest(animation=animation):
                entry = self.area / "selector-fixture.py"
                entry.write_text('import runpy\n'
                    f'u=runpy.run_path({str(self.repo / "mockups/updates.py")!r})\n'
                    f'rs,i=u["parse_catalog"](open({str(self.repo / "mockups/updates.json")!r}).read())\n'
                    'm=u["Model"](rs,i)\n'
                    f'u["NativeUI"](m,{{"BACKGROUND":"#121212"}},animation={animation!r}).selector()\n'
                    'print("SELECTOR_FINAL="+str(m.selector)+":"+m.screen+":"+str(m.closed))\n')
                before = tree(self.area)
                master, slave = pty.openpty()
                fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 39, 130, 0, 0))
                original = termios.tcgetattr(slave)
                process = subprocess.Popen(["/usr/bin/python3", "-I", "-B", "-c", MOCKUP_AUDIT, str(entry)],
                    stdin=slave, stdout=slave, stderr=slave, env={**ENV, "HOME": str(home), "TERM": "xterm-256color"},
                    start_new_session=True, preexec_fn=lambda: fcntl.ioctl(slave, termios.TIOCSCTTY, 0))
                os.close(slave); output = bytearray()
                def receive_until(needle, seconds=5):
                    end = time.monotonic() + seconds
                    while needle not in output and time.monotonic() < end:
                        if select.select([master], [], [], .03)[0]:
                            try: output.extend(read_mockup_pty(master))
                            except OSError: break
                    self.assertIn(needle, output, output.decode(errors="replace")[-1800:])
                try:
                    receive_until(b"Enter abrir")
                    active, muted = module["identity_colors"]("#121212")
                    rgb = ";".join(str(int(muted[i:i+2], 16)) for i in (1, 3, 5))
                    self.assertRegex(output, (r"38;2;" + rgb + r"(?:;[0-9]+)*m  Heartchy").encode())
                    output.clear()
                    started = time.monotonic()
                    os.write(master, b"\x1b[?0u\x1b[B")
                    receive_until(b"m> Heartchy")
                    if animation:
                        deadline = time.monotonic() + 2
                        while output.count(b"\x1b[2;2H") < 18 and time.monotonic() < deadline:
                            if select.select([master], [], [], .01)[0]:
                                output.extend(read_mockup_pty(master))
                        self.assertEqual(output.count(b"\x1b[2;2H"), 18)
                        self.assertTrue(.53 <= time.monotonic() - started < .95, "completed Middleout duration must be bounded")
                        output.clear()
                        os.write(master, b"\x1b[A")
                        receive_until(b"m> Omarchy")
                        output.clear()
                        fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", 23, 60, 0, 0))
                        os.killpg(process.pid, signal.SIGWINCH)
                        receive_until(b"cabecera compacta")
                        output.clear()
                        fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", 39, 130, 0, 0))
                        os.killpg(process.pid, signal.SIGWINCH)
                        receive_until(b"Enter abrir")
                        # Continue navigating while the reverse sweep is active.
                        os.write(master, b"\x1b[B")
                        output.clear()
                        receive_until(b"m> Heartchy")
                    started = time.monotonic()
                    # Enter during Middleout must skip remaining frames immediately.
                    os.write(master, b"\r")
                    receive_until(b"SELECTOR_FINAL=1:releases:False")
                    self.assertLess(time.monotonic() - started, .3)
                    self.assertEqual(process.wait(timeout=3), 0)
                    self.assertNotIn(b"^[[?0u", output)
                    self.assertNotIn(b"\x1b[?0u", output)
                    self.assertEqual(termios.tcgetattr(master), original)
                finally:
                    if process.poll() is None:
                        os.killpg(process.pid, signal.SIGKILL); process.wait()
                    os.close(master)
                self.assertEqual(tree(self.area), before)

    def test_updates_native_window_and_fixed_logo_canvas(self):
        module, m = self.updates_model()
        for name in ("OMARCHY", "HEARTCHY"):
            painted = module["banner"](name, 129, 38)
            plain = re.sub(r"\x1b\[[0-9;]*m", "", painted)
            rows = plain.splitlines()
            self.assertEqual(rows[:len(module["logo"](name))], module["logo"](name))
            self.assertEqual(rows.index(module["SIMULATION"]), 11)
            self.assertLessEqual(max(map(len, rows)), 129)
            self.assertLess(len(module["banner"](name, 42, 16).splitlines()), 5)
        before = tree(self.area)
        launched = []
        def open_window(argv, check):
            launched.append(argv)
            self.assertFalse(check)
            return subprocess.CompletedProcess(argv, 0)
        with patch.object(sys, "argv", ["mockup", "--window"]), patch.object(subprocess, "run", open_window), patch.object(os, "access", return_value=True):
            self.assertEqual(module["main"](), 0)
        self.assertEqual(launched, [["/usr/bin/alacritty", "--class", "TUI.float", "--title", "Heartchy · SIMULACIÓN", "-e", str(self.repo / "bin/heartchy-updates-mockup")]])
        self.assertEqual(before, tree(self.area))

    def updates_theme_fixture(self, directory, background, foreground, accent):
        module, _ = self.updates_model()
        values = {key: foreground if key.endswith("FOREGROUND") else background
                  for key in module["THEME_KEYS"]}
        values["BORDER_FOREGROUND"] = accent
        values["GUM_CHOOSE_CURSOR_FOREGROUND"] = accent
        values["GUM_CONFIRM_PROMPT_FOREGROUND"] = accent
        values["GUM_SPIN_SPINNER_FOREGROUND"] = accent
        values["GUM_CONFIRM_SELECTED_BACKGROUND"] = accent
        values["GUM_CHOOSE_SELECTED_BACKGROUND"] = accent
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "gum_env.lua").write_text("".join(f'hl.env("{k}", "{v}")\n' for k,v in values.items()))
        (directory / "alacritty.toml").write_text(f'[colors.normal]\ngreen="{accent}"\n'
            f'[colors.primary]\nbackground="{background}"\nforeground="{foreground}"\n')
        (directory / "colors.toml").write_text(f'background="{background}"\nforeground="{foreground}"\n'
            f'accent="{accent}"\ngreen="{accent}"\nselection="{accent}"\nbright_foreground="{foreground}"\n')
        return values

    def test_updates_live_theme_generation_replacement_and_incomplete_sources(self):
        module, _ = self.updates_model()
        directory = self.area / "state/omarchy/current/theme"
        a = self.updates_theme_fixture(directory, "#101315", "#eeeeee", "#ffaa11")
        watch = module["ThemeWatch"](directory)
        def received(expected):
            deadline = time.monotonic() + 1
            while time.monotonic() < deadline:
                palette = watch.ready(.04)
                if palette is not None:
                    self.assertEqual(palette[0], expected)
                    return
            self.fail("complete palette event not published within one second")
        try:
            received(a)
            # Surviving ancestor observes both replacement directories and files.
            directory.rename(directory.with_name("old-generation"))
            b = self.updates_theme_fixture(directory, "#eeeeee", "#202020", "#224488")
            received(b)
            text = (directory / "gum_env.lua").read_text()
            (directory / "gum_env.lua").unlink()
            for _ in range(6):
                self.assertIsNone(watch.ready(.04))
            self.assertIsNotNone(watch.problem)
            (directory / "gum_env.lua").write_text('hl.env("FOREGROUND", "#999999")\n')
            for _ in range(6):
                self.assertIsNone(watch.ready(.04))
            self.assertIn("incompleta", watch.problem)
            replacement = directory / "new-colors"
            replacement.write_text(text)
            replacement.replace(directory / "gum_env.lua")
            received(b)
            # Rapid incomplete generations never mix A's Gum with B's terminal.
            for n in range(4):
                self.updates_theme_fixture(directory, "#222222", "#aaaaaa", "#663399")
                watch.ready(.001)
                (directory / "alacritty.toml").write_text("[incomplete")
                watch.ready(.001)
            self.updates_theme_fixture(directory, "#101315", "#eeeeee", "#ffaa11")
            received(a)
            # Two individually valid, stable files from different palettes must
            # not be accepted during a slow, non-atomic theme activation.
            old_terminal = (directory / "alacritty.toml").read_bytes()
            self.updates_theme_fixture(directory, "#eeeeee", "#202020", "#224488")
            new_terminal = (directory / "alacritty.toml").read_bytes()
            (directory / "alacritty.toml").write_bytes(old_terminal)
            for _ in range(9):
                self.assertIsNone(watch.ready(.05))
            self.assertIn("generaciones distintas", watch.problem)
            (directory / "alacritty.toml").write_bytes(new_terminal)
            received(b)
            foundation = (directory / "colors.toml").read_text()
            (directory / "colors.toml").write_text(foundation.replace('foreground="#202020"', 'foreground=123'))
            for _ in range(6):
                self.assertIsNone(watch.ready(.04))
            self.assertIn("tipo/valor", watch.problem)
            (directory / "colors.toml").write_text(foundation)
            received(b)
            with patch.dict(watch.ready.__globals__, {"theme_snapshot": lambda _: self.fail("idle filesystem polling")}):
                for _ in range(3):
                    self.assertIsNone(watch.ready(.02))
            self.assertLessEqual(len(watch.watches), len(directory.parents) + 1)
        finally:
            fd = watch.fd; watch.close()
        with self.assertRaises(OSError):
            os.fstat(fd)
        # An initially absent high-level ancestor can be created in stages.
        absent = self.area / "absent/state/omarchy/current/theme"
        watch = module["ThemeWatch"](absent)
        try:
            absent.parents[3].mkdir()
            watch.ready(.02)
            self.updates_theme_fixture(absent, "#101315", "#eeeeee", "#ffaa11")
            received(a)
        finally:
            watch.close()

    def test_updates_live_palette_transparent_text_and_scoped_panels(self):
        module, m = self.updates_model()
        slots = module["COLOR_SLOTS"]
        self.assertEqual(len(set(slots.values())), len(slots))
        self.assertTrue(all(16 <= index < 256 for index in slots.values()))
        for background, foreground, accent in (("#101315", "#eeeeee", "#ffaa11"),
                                                ("#eff1f5", "#4c4f69", "#1e66f5")):
            directory = self.area / "palette"
            colors = self.updates_theme_fixture(directory, background, foreground, accent)
            palette = module["palette_slots"](colors, accent)
            surface = palette[slots["surface"]]
            self.assertNotEqual(surface, background)
            for role in ("text", "help", "pink", "muted-pink"):
                self.assertGreaterEqual(module["contrast"](palette[slots[role]], surface), 4.5)
            self.assertNotEqual(palette[slots["pink"]], palette[slots["muted-pink"]])
            ui = module["NativeUI"](m, colors)
            ui.indexed_colors = True
            m.screen = "selector"
            self.assertTrue(all(ui.child_env()[k] == "" for k in colors if k.endswith("BACKGROUND")))
            self.assertNotIn("48;", ui.surface("Ayuda"))
            self.assertNotIn("48;", ui.live_banner("HEARTCHY", 129, 39))
            m.screen = "confirm"
            self.assertEqual(ui.child_env()["GUM_CONFIRM_SELECTED_BACKGROUND"], str(slots["pink"]))
            sequence = module["palette_sequence"](palette)
            self.assertLess(len(sequence), 4096)
            self.assertIn(b"\x1b]4;", sequence)
            commands = re.findall(rb"\x1b]([^\x1b]+)\x1b\\", sequence)
            self.assertEqual(len(commands), len(palette))
            self.assertTrue(all(len(command.split(b";")) == 3 for command in commands),
                            "one pair per OSC; long parameter lists are discarded by real terminal parsers")
            self.assertNotRegex(sequence, rb"\x1b\](?:10|11|12|52);")
            self.assertNotIn(b"\x1b[2J", sequence)
            header = ui.live_banner("HEARTCHY", 129, 39)
            self.assertNotIn("38;2;", header)
            self.assertEqual(len(re.sub(r"\x1b\[[0-9;]*m", "", header).splitlines()[0]), 97)
            self.assertEqual(module["theme_snapshot"](directory)[0], colors)
        with self.assertRaises(ValueError):
            module["palette_sequence"]({16: "unsafe\033]52;clipboard"})

    def test_updates_palette_handshake_preserves_dynamic_colors_and_rejects_no_reply(self):
        entry = self.area / "palette-handshake.py"
        entry.write_text('import runpy,json\n'
            f'u=runpy.run_path({str(self.repo / "mockups/updates.py")!r})\n'
            'try:\n'
            ' saved,keys=u["save_terminal_palette"]((16,17));print("SAVED="+json.dumps(saved)+":"+repr(keys))\n'
            'except ValueError as e:print("BLOCKED="+str(e))\n')
        first = b"\x1b]4;16;rgb:abcd/1111/2222\x1b\\"
        # Every boundary matters, including a read containing only the first
        # ESC. A PTY/emulator may split either the introducer or terminator.
        for cut in (*range(1, len(first)), None):
            responding = cut is not None
            master, slave = pty.openpty()
            attrs = termios.tcgetattr(slave)
            process = subprocess.Popen(["/usr/bin/python3", "-I", "-B", str(entry)],
                stdin=slave, stdout=slave, stderr=slave, env=ENV, start_new_session=True,
                preexec_fn=lambda: fcntl.ioctl(slave, termios.TIOCSCTTY, 0))
            os.close(slave); output = b""
            try:
                end = time.monotonic() + 2
                while process.poll() is None and time.monotonic() < end:
                    if select.select([master], [], [], .02)[0]:
                        try: data = os.read(master, 65536)
                        except OSError: break
                        output += data
                        if responding and b"\x1b]4;16;?" in data:
                            os.write(master, first[:cut])
                            time.sleep(.02)
                            os.write(master, first[cut:] + b"\x1b[B\x1b]4;17;rgb:1234/5678/abcd\x1b\\")
                while select.select([master], [], [], .02)[0]:
                    try: output += os.read(master, 65536)
                    except OSError: break
                self.assertEqual(process.wait(timeout=2), 0)
                self.assertEqual(termios.tcgetattr(master), attrs)
                if responding:
                    self.assertIn(b'"16": "rgb:abcd/1111/2222"', output)
                    self.assertIn(b'"17": "rgb:1234/5678/abcd"', output)
                    self.assertIn(b"b'\\x1b[B'", output)
                else:
                    self.assertIn(b"BLOCKED=terminal no", output)
                    self.assertNotIn(b"\x1b]4;16;#", output)
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL); process.wait()
                os.close(master)

    def test_updates_live_theme_same_children_query_focus_progress_and_exit(self):
        if not all(shutil.which(name, path=ENV["PATH"]) for name in ("gum", "fzf", "sleep")):
            self.skipTest("NOT_RUN: native widgets missing")
        home = self.area / "home"
        (home / ".config/omarchy").mkdir(parents=True)
        (home / ".config/omarchy/shell.json").write_text("unchanged personal sentinel")
        directory = home / ".local/state/omarchy/current/theme"
        entry = self.area / "live-fixture.py"
        entry.write_text('import runpy\n'
            f'u=runpy.run_path({str(self.repo / "mockups/updates.py")!r})\n'
            f'rs,i=u["parse_catalog"](open({str(self.repo / "mockups/updates.json")!r}).read())\n'
            'm=u["Model"](rs,i);ui=u["NativeUI"](m,animation=__import__("sys").argv[-1]!="--no-animation")\n'
            'ui.run()\n'
            'print("END="+str(m.closed)+":"+m.installed+":"+m.query+":"+m.current.version+":"+str(ui.revision))\n'
            'print("WATCHER_CLOSED="+str(not ui.theme_thread.is_alive()))\n')
        for animation in (True, False):
            a = self.updates_theme_fixture(directory, "#101315", "#eeeeee", "#ffaa11")
            master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 39, 130, 0, 0))
            attrs = termios.tcgetattr(slave)
            args = ["/usr/bin/python3", "-I", "-B", "-c", MOCKUP_AUDIT, str(entry)]
            if not animation:
                args += ["--no-animation"]
            process = subprocess.Popen(args, env={**ENV, "HOME": str(home), "TERM": "xterm-256color"},
                stdin=slave, stdout=slave, stderr=slave, start_new_session=True,
                preexec_fn=lambda: fcntl.ioctl(slave, termios.TIOCSCTTY, 0))
            os.close(slave)
            output = bytearray()
            def wait(needle, seconds=5):
                deadline = time.monotonic() + seconds
                while needle not in output and time.monotonic() < deadline:
                    if select.select([master], [], [], .02)[0]:
                        try: output.extend(read_mockup_pty(master))
                        except OSError: break
                self.assertIn(needle, output, output.decode(errors="replace")[-2200:])
            def children():
                return (Path("/proc") / str(process.pid) / "task" / str(process.pid) / "children").read_text().split()
            def change(background, foreground, accent):
                output.clear()
                self.updates_theme_fixture(directory, background, foreground, accent)
                wait(b";" + foreground.encode(), 1)
            try:
                wait(b"Enter abrir")
                # Change during Middleout; no synthetic key or acceptance.
                output.clear(); os.write(master, b"\x1b[B")
                wait(b"Heartchy")
                change("#eeeeee", "#202020", "#224488")
                if animation:
                    module, _ = self.updates_model()
                    adapter = runpy.run_path(str(self.repo / "mockups/animation_preview.py"))
                    expected = adapter["frame_output"](adapter["static_rows"](module["logo"]("HEARTCHY")),
                                                        module["indexed"]("loose-pink"))
                    wait(expected.encode(), 1)
                self.assertIsNone(process.poll())
                output.clear(); os.write(master, b"\r"); wait(b"Buscar versi")
                time.sleep(.15)
                output.clear(); os.write(master, b"Base"); time.sleep(.15)
                os.write(master, b"\x1b[B"); time.sleep(.15)
                same_fzf = children()
                self.assertEqual(len(same_fzf), 1)
                change("#101315", "#eeeeee", "#ffaa11")
                self.assertEqual(children(), same_fzf, "theme switch recreated Fzf and could lose viewport")
                change("#eeeeee", "#202020", "#224488")
                self.assertEqual(children(), same_fzf)
                output.clear(); os.write(master, b"\r"); wait(b"Revisar confirmaci"); time.sleep(.15)
                output.clear(); os.write(master, b"\r"); wait("¿Continuar".encode())
                wait(b"Cancelar"); time.sleep(.1)
                self.assertIn(b"Heartchy Base  0.3.0", output)
                same_confirm = children()
                change("#101315", "#eeeeee", "#ffaa11")
                self.assertEqual(children(), same_confirm)
                # Cancelar remains focused; Enter returns to list, no progress.
                output.clear(); os.write(master, b"\r"); wait(b"Buscar versi")
                self.assertNotIn(b"SIMULADA", output)
                time.sleep(.15)
                output.clear(); os.write(master, b"\r"); wait(b"Revisar confirmaci"); time.sleep(.15)
                output.clear(); os.write(master, b"\r"); wait("¿Continuar".encode()); wait(b"Cancelar")
                self.assertIn(b"Heartchy Base  0.3.0", output, "selected ID/query lost after cancel")
                time.sleep(.15)
                output.clear(); started = time.monotonic(); os.write(master, b"\x1b[D\r")
                wait("Instalación SIMULADA".encode())
                time.sleep(.15)
                same_spinner = children()
                self.assertEqual(len(same_spinner), 1)
                spin_task = Path("/proc") / same_spinner[0] / "task" / same_spinner[0] / "children"
                def work():
                    return sorted({pid for task in spin_task.parent.parent.iterdir()
                                   for pid in (task / "children").read_text().split()})
                same_work = work()
                self.assertEqual(len(same_work), 1)
                os.write(master, b"\x1b[?0u")
                change("#eeeeee", "#202020", "#224488")
                self.assertEqual(children(), same_spinner)
                self.assertEqual(work(), same_work, "simulation work restarted or duplicated")
                change("#101315", "#eeeeee", "#ffaa11")
                wait("Simulación completada".encode(), 10)
                self.assertTrue(7.5 < time.monotonic() - started < 10)
                wait(b"Resultado simulado")
                time.sleep(.2)
                same_result = children()
                change("#eeeeee", "#202020", "#224488")
                self.assertEqual(children(), same_result)
                output.clear(); os.write(master, b"\x1b[B\r")
                wait(b"END=True:0.3.0:Base:0.3.0:")
                wait(b"WATCHER_CLOSED=True")
                self.assertIn(b";rgb:1111/2222/3333", output)
                self.assertNotIn(b"^[[?0u", output)
                self.assertEqual(process.wait(timeout=3), 0)
                self.assertEqual(termios.tcgetattr(master), attrs)
                self.assertEqual((home / ".config/omarchy/shell.json").read_text(), "unchanged personal sentinel")
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM); process.wait(timeout=3)
                os.close(master)

    def test_updates_launcher_portability_no_effects_and_invalid_input(self):
        home = self.area / "home"
        (home / ".config/omarchy").mkdir(parents=True)
        (home / ".config/omarchy/shell.json").write_text('private sentinel: never read or write')
        before = tree(self.area)
        env = {**ENV, "HOME": str(home), "TERM": "xterm-256color"}
        for args, code in ((("--help",), 0), (("--window", "--help"), 0), (("--window", "--apply"), 2), (("--apply",), 2), ((), 2)):
            result = subprocess.run(self.mockup_command() + list(args), cwd="/", env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, code, result.stdout + result.stderr)
            self.assertNotIn("forbidden", result.stdout + result.stderr)
        self.assertEqual(before, tree(self.area))
        self.assertTrue(os.access(self.repo / "bin/heartchy-updates-mockup", os.X_OK))

    def test_updates_real_gum_fzf_pty_flow_without_host_effects(self):
        missing = [p for p in ("gum", "fzf", "sleep") if not shutil.which(p, path=ENV["PATH"])]
        if missing:
            self.skipTest("NOT_RUN: missing native UI dependencies: " + ", ".join(missing))
        home = self.area / "home"
        (home / ".config/omarchy").mkdir(parents=True)
        (home / ".config/omarchy/shell.json").write_text("untouched sentinel")
        before = tree(self.area)
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 44, 104, 0, 0))
        attrs = termios.tcgetattr(slave)
        process = subprocess.Popen(self.mockup_command(), cwd="/",
            env={**ENV, "HOME": str(home), "TERM": "xterm-256color"}, stdin=slave, stdout=slave, stderr=slave,
            start_new_session=True, preexec_fn=lambda: fcntl.ioctl(slave, termios.TIOCSCTTY, 0))
        os.close(slave)
        received = bytearray()
        def wait_text(text, timeout=8):
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if text.encode() in received:
                    return
                if select.select([master], [], [], .1)[0]:
                    try:
                        received.extend(read_mockup_pty(master))
                    except OSError:
                        break
            self.fail("PTY missing " + text + ": " + received.decode(errors="replace")[-2000:])
        def wait_gum(prompt):
            wait_text(prompt)
            wait_text("Cancelar" if "Continuar" in prompt else "Salir de la maqueta" if prompt == "Resultado simulado" else "Esc salir")
            time.sleep(.15)

        def wait_fzf(new=True):
            # The prompt is emitted before the remaining frame. Input starts
            # only after Fzf has drawn its cursor, including after each resize.
            if new:
                wait_text("\x1b[2J\x1b[H")
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                frame = received.rsplit(b"\x1b[2J\x1b[H", 1)[-1] if new else received
                if re.search(rb"Buscar versi[\s\S]*\x1b\[\?25h", frame):
                    return
                if select.select([master], [], [], .1)[0]:
                    received.extend(read_mockup_pty(master))
            self.fail("Fzf did not finish drawing its input cursor")

        try:
            wait_gum("Updates / Omarchy")
            received.clear()
            os.write(master, b"\x1b[B\r"); wait_fzf()
            received.clear()
            os.write(master, b"NO_MATCH_TEST"); wait_fzf(new=False)
            # Await each native resize redraw before sending further keys.
            received.clear()
            fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", 34, 88, 0, 0))
            os.killpg(process.pid, signal.SIGWINCH)
            wait_fzf()
            received.clear()
            os.write(master, b"\r"); wait_fzf()
            received.clear()
            os.write(master, b"\x1b"); wait_gum("Updates / Omarchy")
            received.clear()
            os.write(master, b"\r"); wait_fzf()
            received.clear()
            os.write(master, b"\x15"); wait_fzf(new=False)
            received.clear()
            fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", 44, 104, 0, 0))
            os.killpg(process.pid, signal.SIGWINCH)
            wait_fzf()
            received.clear()
            os.write(master, b"Base"); wait_fzf(new=False)
            received.clear()
            os.write(master, b"\x1b[B\r"); wait_text("Revisar confirmación"); time.sleep(.15)
            received.clear(); os.write(master, b"\r"); wait_gum("¿Continuar con la simulación?")
            self.assertIn(b"Heartchy Base  0.3.0", received.rsplit(b"\x1b[2J\x1b[H", 1)[-1])
            received.clear()
            os.write(master, b"\r"); wait_fzf()
            received.clear()
            # Query Base contains only two releases: down cycles to 0.3.1.
            os.write(master, b"\x1b[B\r"); wait_text("Revisar confirmación"); time.sleep(.15)
            received.clear(); os.write(master, b"\r"); wait_gum("¿Continuar con la simulación?")
            self.assertIn(b"Heartchy Base  0.3.1", received.rsplit(b"\x1b[2J\x1b[H", 1)[-1])
            received.clear()
            os.write(master, b"\r"); wait_fzf()
            received.clear()
            os.write(master, b"\x1b[B\r"); wait_text("Revisar confirmación"); time.sleep(.15)
            received.clear(); os.write(master, b"\r"); wait_gum("¿Continuar con la simulación?")
            self.assertIn(b"Heartchy Base  0.3.0", received.rsplit(b"\x1b[2J\x1b[H", 1)[-1])
            received.clear()
            os.write(master, b"\r"); wait_fzf()
            received.clear()
            # Cancelling must retain the selected milestone, not jump to 0.3.1.
            os.write(master, b"\r"); wait_text("Revisar confirmación"); time.sleep(.15)
            received.clear(); os.write(master, b"\r"); wait_gum("¿Continuar con la simulación?")
            self.assertIn(b"Heartchy Base  0.3.0", received.rsplit(b"\x1b[2J\x1b[H", 1)[-1])
            received.clear()
            os.write(master, b"\x1b[D\r"); wait_text("Instalación SIMULADA")
            # Emulate the real terminal's reply to Gum spin's keyboard query.
            os.write(master, b"\x1b[?0u")
            wait_text("Simulación completada", timeout=12)
            self.assertNotIn(b"^[[?0u", received)
            wait_text("Versión ficticia instalada: 0.3.0")
            wait_gum("Resultado simulado")
            received.clear()
            os.write(master, b"\r"); wait_fzf()
            received.clear()
            os.write(master, b"\x1b"); wait_gum("Updates / Omarchy")
            os.write(master, b"\x1b")
            self.assertEqual(process.wait(timeout=4), 0)
            self.assertEqual(termios.tcgetattr(master), attrs)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL); process.wait()
            os.close(master)
        self.assertEqual(before, tree(self.area))

    def test_default_middleout_shared_frames_cached_both_directions(self):
        if not Path('/usr/bin/ttfx').exists():
            self.skipTest('NOT_RUN: ttfx unavailable')
        module, model = self.updates_model()
        ui = module['NativeUI'](model, {})
        with patch.object(subprocess, 'run', wraps=subprocess.run) as process:
            ui.prepare_middleout()
            self.assertEqual(len(process.call_args_list), 3)
            self.assertEqual(process.call_args_list[0].args[0], ['/usr/bin/ttfx', '--version'])
            for call in process.call_args_list[1:]:
                self.assertEqual(call.args[0][14], 'middleout')
        tools = ui.logo_tools()
        for before, after in (('OMARCHY','HEARTCHY'), ('HEARTCHY','OMARCHY')):
            frames = ui.middleout[after]
            self.assertEqual(frames[2], (tuple(' '*97 for _ in range(10)), False))
            self.assertEqual(frames[-1], (tools['static_rows'](module['logo'](after)), True))
            self.assertTrue(.35 <= len(frames)/tools['FPS'] <= .7)
        cached = ui.middleout
        with patch.object(subprocess, 'run', side_effect=AssertionError('engine respawned')):
            ui.prepare_middleout()
        self.assertIs(ui.middleout, cached)

    def test_default_middleout_incompatibility_requires_explicit_opt_out(self):
        module, model = self.updates_model()
        errors = [FileNotFoundError('ttfx absent'), subprocess.TimeoutExpired('/usr/bin/ttfx',2),
                  subprocess.CompletedProcess([],0,b'ttfx 0.5.0\n')]
        for failure in errors:
            ui = module['NativeUI'](model, {})
            with self.subTest(failure=str(failure)), patch.object(subprocess, 'run') as run:
                if isinstance(failure, Exception): run.side_effect = failure
                else: run.return_value = failure
                with self.assertRaisesRegex(ValueError, 'Middleout no disponible.*--no-animation'):
                    ui.selector()
                self.assertEqual(ui.middleout, {})
                self.assertEqual(run.call_count,1)
                self.assertEqual(run.call_args.args[0], ['/usr/bin/ttfx','--version'])
        # Invalid frames cannot leave a partially usable default cached.
        ui = module['NativeUI'](model, {})
        with patch.object(subprocess, 'run', side_effect=[
                subprocess.CompletedProcess([],0,b'ttfx 0.3.2\n'),
                subprocess.CompletedProcess([],0,b'corrupt',b'')]):
            with self.assertRaisesRegex(ValueError,'--no-animation'):
                ui.prepare_middleout()
            self.assertEqual(ui.middleout,{})

    def test_default_no_animation_and_burst_never_launch_per_key_processes(self):
        import contextlib, io
        module, _ = self.updates_model()
        for animation in (False, True):
            _, model = self.updates_model()
            ui = module['NativeUI'](model, {}, animation=animation)
            if animation:
                if not Path('/usr/bin/ttfx').exists():
                    self.skipTest('NOT_RUN: ttfx unavailable')
                ui.prepare_middleout()
            output = io.StringIO()
            # All arrows are pending together; consume the burst and Enter,
            # without playing any intermediate transitions or launching ttfx.
            with patch.object(termios, 'tcgetattr', return_value=[0,0,0,0,0,0,[]]), \
                 patch.object(termios,'tcsetattr'), \
                 patch.object(shutil,'get_terminal_size',return_value=os.terminal_size((130,39))), \
                 patch.object(select,'select',return_value=([0],[],[])), \
                 patch.object(os,'read',return_value=b'\x1b[B\x1b[A\x1b[B\r'), \
                 patch.object(subprocess,'run',side_effect=AssertionError('engine per key')), \
                 patch.object(ui,'tool',side_effect=lambda args,**kw: subprocess.CompletedProcess(args,0,args[-1])), \
                 patch.object(ui,'paint_wipe',side_effect=AssertionError('old wipe used')), \
                 contextlib.redirect_stdout(output):
                ui.selector()
            self.assertEqual((model.selector,model.screen),(1,'releases'))
            self.assertEqual(output.getvalue().count('\x1b[2;2H'),3)
            expected=ui.logo_tools()['frame_output'](ui.logo_tools()['static_rows'](module['logo']('HEARTCHY')),
                                                   module['color_escape'](ui.pink))
            self.assertIn(expected,output.getvalue())
            if not animation: self.assertEqual(ui.middleout,{})

    def test_animation_native_frames_exact_and_scoped(self):
        if not Path('/usr/bin/ttfx').exists():
            self.skipTest('NOT_RUN: ttfx unavailable')
        module, _ = self.updates_model()
        preview = runpy.run_path(str(self.repo / 'mockups/animation_preview.py'))
        engine = preview['NativeFrames']()
        for effect in preview['PARAMETERS']:
            for word in ('OMARCHY', 'HEARTCHY'):
                with self.subTest(effect=effect, word=word):
                    frames = engine.get(effect, module['logo'](word))
                    expected = tuple(r.ljust(97) for r in module['logo'](word))
                    self.assertEqual(frames[-1], expected)
                    self.assertGreater(len(frames), 1)
                    for frame in frames:
                        self.assertEqual(len(frame), 10)
                        self.assertTrue(all(len(row) == 97 for row in frame))
                        painted = preview['frame_output'](frame, '\x1b[38;5;44m')
                        self.assertEqual(re.findall(r'\x1b\[(\d+);(\d+)H', painted), [(str(i), '2') for i in range(2, 12)])
                        self.assertNotIn('\x1b[48', painted)
                        plain = re.sub(r'\x1b\[[?0-9;]*[hlHm]', '', painted)
                        self.assertEqual(plain, ''.join(frame))
                    other = 'HEARTCHY' if word == 'OMARCHY' else 'OMARCHY'
                    composed = list(preview['transition_frames'](module['logo'](other), frames))
                    self.assertEqual(composed[2], (tuple(' ' * 97 for _ in range(10)), False))
                    self.assertEqual(composed[-1], (expected, True))
                    with patch.object(subprocess, 'run', side_effect=AssertionError('cache spawned a child')):
                        self.assertIs(engine.get(effect, module['logo'](word)), frames)
        # Long effects remain visibly long, not sampled down to a false morph.
        self.assertGreater(len(engine.get('decrypt', module['logo']('HEARTCHY'))) / 30, 10)
        self.assertLess(len(engine.get('slice', module['logo']('HEARTCHY'))) / 30 + .1, .7)

    def test_animation_parity_decoder_rejects_controls_and_contract_drift(self):
        preview = runpy.run_path(str(self.repo / 'mockups/animation_preview.py'))
        expected = tuple(' ' * 97 for _ in range(10))
        def record(rows):
            body = '\n'.join(rows).encode()
            return str(len(body)).encode() + b'\n' + body + b'\n'
        blank = record(expected[1:])
        self.assertEqual(preview['decode_frames'](blank + blank, expected), (expected,))
        for raw in (b'\x1b[H', blank[:-1], blank[:-20], blank + b'1\nx',
                    record(['\x1b' + ' ' * 96] * 9), record(['界' * 97] * 9),
                    record(['a' * 97] * 9), record([' ' * 98] * 9), b'9' * 500):
            with self.subTest(raw=raw[:30]), self.assertRaises(ValueError):
                preview['decode_frames'](raw, expected)
        engine = preview['NativeFrames']()
        with patch.object(subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, b'ttfx 0.5.0\n')):
            with self.assertRaisesRegex(ValueError, '0.3.2'):
                engine.get('slice', [''] * 10)
        with self.assertRaises(ValueError):
            preview['command']('random-effect')

    def test_animation_resize_during_native_generation_never_paints_old_geometry(self):
        import contextlib, io
        module, model = self.updates_model()
        preview = runpy.run_path(str(self.repo / 'mockups/animation_preview.py'))
        ui = module['NativeUI'](model, {})
        size = [os.terminal_size((130, 39))]
        def generate(*args):
            size[0] = os.terminal_size((60, 23))
            return (tuple(r.ljust(97) for r in module['logo']('HEARTCHY')),)
        reads = iter([b'\x1b[B\x1b[C', b'', b'\x1b'])
        # The zero-timeout post-generation poll has no input; next idle poll
        # gets Escape. No old 97-column frame may be painted into 60 columns.
        events = iter([([0], [], []), ([], [], []), ([0], [], [])])
        def read(*_):
            value = next(reads)
            return next(reads) if not value else value
        out = io.StringIO()
        with patch.object(termios, 'tcgetattr', return_value=[0,0,0,0,0,0,[]]), \
             patch.object(termios, 'tcsetattr'), \
             patch.object(shutil, 'get_terminal_size', side_effect=lambda: size[0]), \
             patch.object(select, 'select', side_effect=lambda *a: next(events)), \
             patch.object(os, 'read', side_effect=read), \
             patch.object(preview['NativeFrames'], 'get', side_effect=generate), \
             contextlib.redirect_stdout(out):
            # Treat Escape immediately; fragmentation is covered in real PTY.
            def keys(pending, data, expired=False, extra=None):
                return module['selector_keys'](pending, data, True, extra)
            preview['compare'](ui, module['logo'], keys, module['heading'], module['banner'],
                               module['indexed'], module['color_escape'])
        self.assertNotIn('\x1b[2;2H', out.getvalue())
        self.assertIn('cabecera compacta', out.getvalue())

    def test_animation_preview_cli_and_normal_default_unchanged(self):
        module, _ = self.updates_model()
        regular = module['window_command']()
        preview = module['window_command'](animation=False, animation_preview=True)
        self.assertEqual(preview, regular + ['--no-animation', '--animation-preview'])
        self.assertNotIn('--animation-preview', regular)
        result = subprocess.run([str(self.repo / 'bin/heartchy-updates-mockup'), '--help'], env=ENV,
                                cwd=self.area, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn('--animation-preview', result.stdout)
        keys, pending = module['selector_keys'](b'', b'\x1b[?0u\x1b[C\x1b[D', False,
                                              {b'\x1b[C': 'heartchy', b'\x1b[D': 'omarchy'})
        self.assertEqual((keys, pending), (['heartchy', 'omarchy'], b''))
        self.assertEqual(module['selector_keys'](b'', b'\x1b[C')[0], ['next'])

    def test_animation_preview_pty_cancel_resize_theme_and_no_animation(self):
        if not all(Path('/usr/bin/' + n).exists() for n in ('gum', 'ttfx')):
            self.skipTest('NOT_RUN: native preview dependency unavailable')
        module, _ = self.updates_model()
        home = self.area / 'home'; home.mkdir()
        source = self.area / 'theme-state/omarchy/current/theme'
        self.updates_theme_fixture(source, '#121212', '#eeeeee', '#ffaa11')
        for animation in (True, False):
            with self.subTest(animation=animation):
                master, slave = pty.openpty()
                fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 39, 130, 0, 0))
                original = termios.tcgetattr(slave)
                command = ['/usr/bin/python3', '-I', '-B', '-c', MOCKUP_AUDIT,
                           str(self.repo / 'bin/heartchy-updates-mockup'), '--animation-preview']
                if not animation: command += ['--no-animation']
                before = tree(self.area)
                process = subprocess.Popen(command, stdin=slave, stdout=slave, stderr=slave,
                    env={**ENV, 'HOME': str(home), 'XDG_STATE_HOME': str(source.parents[2]), 'TERM': 'xterm-256color'},
                    start_new_session=True, preexec_fn=lambda: fcntl.ioctl(slave, termios.TIOCSCTTY, 0))
                os.close(slave); output = bytearray()
                def receive(needle, timeout=5):
                    stop = time.monotonic() + timeout
                    while needle.encode() not in output and time.monotonic() < stop:
                        if select.select([master], [], [], .02)[0]:
                            try: output.extend(read_mockup_pty(master))
                            except OSError: break
                    self.assertIn(needle.encode(), output, output.decode(errors='replace')[-1500:])
                def keys(data):
                    output.clear(); os.write(master, data)
                try:
                    receive('Esc volver')
                    keys(b'\x1b[B\x1b[C'); receive('Última muestra')
                    self.assertIn(b'Omarchy', output)
                    if animation:
                        self.assertGreater(output.count(b'\x1b[2;2H'), 8)
                    else:
                        self.assertIn(b'omitida', output)
                    keys(b'\x1b[D'); receive('Última muestra')
                    keys(b'\r'); receive('Última muestra')
                    # Select decrypt then interrupt; no queued 14-second effects.
                    keys(b'\x1b[B\x1b[B\x1b[B\x1b[C'); receive('Reproduciendo Decrypt')
                    if animation:
                        receive('frames' if b'frames' in output else 'Reproduciendo Decrypt')
                        time.sleep(.12)
                        started = time.monotonic(); keys(b'\x1b[D\x1b[C\x1b[A')
                        receive('> Beams'); self.assertLess(time.monotonic() - started, .5)
                        # Replace palette during a longer effect. The same watcher
                        # ends the preview at its correct destination immediately.
                        keys(b'\x1b[C'); receive('Reproduciendo Beams'); time.sleep(.1)
                        moved = source.with_name('previous'); source.rename(moved)
                        self.updates_theme_fixture(source, '#eeeeee', '#202020', '#0044aa')
                        output.clear(); receive('Interrumpida', 2)
                        self.assertIn(b'\x1b]4;', output)
                        shutil.rmtree(source); moved.rename(source)
                    else:
                        receive('Última muestra')
                    keys(b'\x1b[C'); receive('Reproduciendo')
                    fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack('HHHH', 23, 60, 0, 0))
                    os.killpg(process.pid, signal.SIGWINCH); receive('cabecera compacta')
                    keys(b'\x1b[C'); receive('omitida')
                    fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack('HHHH', 39, 130, 0, 0))
                    os.killpg(process.pid, signal.SIGWINCH); output.clear(); receive('Esc volver')
                    keys(b'\x1b'); receive('Enter abrir')
                    keys(b'\x1b[B\r'); receive('Buscar versi')
                    keys(b'\x1b'); receive('Enter abrir')
                    keys(b'\x03'); self.assertEqual(process.wait(timeout=3), 0)
                    self.assertEqual(termios.tcgetattr(master), original)
                    self.assertNotIn(b'^[[', output)
                finally:
                    if process.poll() is None:
                        os.killpg(process.pid, signal.SIGKILL); process.wait()
                    os.close(master)
                self.assertEqual(tree(self.area), before)

    @unittest.skip("NOT_RUN: no disposable Omarchy graphical environment provisioned; historical captures are not a new test")
    def test_new_graphical_integration(self):
        pass


class Report(unittest.TextTestResult):
    def addSuccess(self, test):
        super().addSuccess(test)
        self.stream.writeln("PASS " + test._testMethodName)

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.stream.writeln("FAIL " + test._testMethodName)

    def addError(self, test, err):
        super().addError(test, err)
        self.stream.writeln("FAIL " + test._testMethodName)

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        result = "NOT_RUN" if reason.startswith("NOT_RUN:") else "SKIP"
        self.stream.writeln(result + " " + test._testMethodName + ": " + reason)


if __name__ == "__main__":
    if os.environ.get("HEARTCHY_TEST_ISOLATED") != "1" or ROOT != Path("/work"):
        raise SystemExit("Use ./test/all; direct execution outside its namespace is refused")
    (SANDBOX / "suite-started").write_text("started\n")
    parser = argparse.ArgumentParser()
    parser.add_argument("--only")
    args = parser.parse_args()
    tests = unittest.defaultTestLoader.getTestCaseNames(CoreTests)
    if args.only and args.only not in tests:
        parser.error("unknown test: " + args.only)
    absent = [name for name in ("lua", "git") if not shutil.which(name, path=ENV["PATH"])]
    if absent:
        print("NOT_RUN: missing " + ", ".join(absent) + "; PASS=0 FAIL=0 NOT_RUN=1")
        raise SystemExit(2)
    suite = unittest.TestSuite([CoreTests(args.only)]) if args.only else unittest.defaultTestLoader.loadTestsFromTestCase(CoreTests)
    result = unittest.TextTestRunner(stream=sys.stdout, verbosity=0, resultclass=Report).run(suite)
    failed = len(result.failures) + len(result.errors)
    passed = result.testsRun - failed - len(result.skipped)
    not_run = sum(reason.startswith("NOT_RUN:") for _, reason in result.skipped)
    print(f"RESULT PASS={passed} FAIL={failed} SKIP={len(result.skipped) - not_run} NOT_RUN={not_run}")
    raise SystemExit(1 if failed else 0)
