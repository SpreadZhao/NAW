import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import subprocess

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))
import install as engine


def snapshot(root):
    return {str(p.relative_to(root)): ("link", os.readlink(p)) if p.is_symlink()
            else ("dir",) if p.is_dir() else ("file", p.read_bytes(), p.stat().st_mtime_ns)
            for p in root.rglob("*")}


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.root = base / "workspace"
        self.root.mkdir()
        (self.root / "flake.nix").write_text("{}")
        self.bundle = base / "bundle"
        self.bundle.mkdir()
        self.sources = {}
        for name in ("one", "two"):
            source = base / "sources" / name
            source.mkdir(parents=True)
            (source / "SKILL.md").write_text(f"---\nname: {name}\ndescription: Test skill\n---\nInstructions\n")
            (source / "scripts").mkdir()
            (source / "scripts/run").write_text("#!/bin/sh\necho test\n")
            (source / "scripts/run").chmod(0o755)
            (source / "assets").mkdir()
            (source / "assets/link").symlink_to("../SKILL.md")
            self.sources[name] = source
        self.manifest = {
            "schemaVersion": 3, "scope": "workspace", "onConflict": "error", "mode": "symlink",
            "cleanup": True, "claude": False, "manageInstructions": True, "manageGitignore": True,
            "instructions": "", "bundle": str(self.bundle), "root": str(self.root),
            "targets": {"agents": {"enable": True, "path": ".agents/skills"},
                        "claude": {"enable": False, "path": ".claude/skills"}},
            "skills": [{"name": n, "source": str(s), "targets": ["agents", "claude"]}
                       for n, s in self.sources.items()],
        }

    def run_install(self, **kwargs):
        manifest = copy.deepcopy(self.manifest)
        manifest.update(kwargs)
        engine.activate(manifest, self.root)

    def target(self, name="one"):
        return self.root / ".agents/skills" / name

    def state(self):
        return json.loads((self.root / ".agent-workspace/state.json").read_text())

    def test_new_install_and_idempotence(self):
        self.run_install()
        self.assertEqual(os.readlink(self.target()), str(self.sources["one"]))
        self.assertEqual((self.root / "AGENTS.md").read_text(),
                         "# Workspace Instructions\n\nSkills are available under `.agents/skills`.\n")
        before = snapshot(self.root)
        self.run_install()
        self.assertEqual(snapshot(self.root), before)

    def test_conflict_kinds_error_zero_writes_and_skip_each_skill(self):
        for kind in ("directory", "file", "link", "broken"):
            with self.subTest(kind=kind):
                path = self.target()
                path.parent.mkdir(parents=True, exist_ok=True)
                if kind == "directory":
                    path.mkdir()
                elif kind == "file":
                    path.write_text("external")
                else:
                    path.symlink_to(self.sources["two"] if kind == "link" else "/absent")
                before = snapshot(self.root)
                with self.assertRaises(engine.InstallError):
                    self.run_install()
                self.assertEqual(snapshot(self.root), before)
                self.run_install(onConflict="skip")
                self.assertTrue(self.target("two").is_symlink())
                self.assertNotIn(".agents/skills/one", self.state()["entries"])
                engine.remove(path)
                self.target("two").unlink()
                (self.root / "AGENTS.md").unlink()
                (self.root / ".gitignore").unlink()
                engine.shutil.rmtree(self.root / ".agent-workspace")

    def test_identical_external_link_not_adopted(self):
        self.target().parent.mkdir(parents=True)
        self.target().symlink_to(self.sources["one"])
        self.run_install()
        self.assertNotIn(".agents/skills/one", self.state()["entries"])
        self.run_install(skills=[])
        self.assertTrue(self.target().is_symlink())
        self.assertFalse(engine.exists(self.target("two")))

    def test_multiple_targets_and_claude_instructions(self):
        self.manifest["claude"] = True
        self.manifest["targets"]["claude"]["enable"] = True
        self.manifest["targets"]["custom"] = {"enable": True, "path": "tools/skills"}
        self.manifest["skills"][0]["targets"].append("custom")
        self.run_install(instructions="Use the project formatter.")
        self.assertTrue((self.root / ".claude/skills/one").is_symlink())
        self.assertTrue((self.root / "tools/skills/one").is_symlink())
        self.assertEqual(os.readlink(self.root / "CLAUDE.md"), "AGENTS.md")
        self.assertIn("Use the project formatter.", (self.root / "AGENTS.md").read_text())

    def test_unmanaged_instructions_even_identical_and_switches(self):
        (self.root / "AGENTS.md").write_text("# Workspace Instructions\n\nSkills are available under `.agents/skills`.\n")
        before = snapshot(self.root)
        with self.assertRaises(engine.InstallError):
            self.run_install()
        self.assertEqual(snapshot(self.root), before)
        self.run_install(manageInstructions=False, manageGitignore=False)
        self.assertFalse(engine.exists(self.root / ".gitignore"))
        self.assertNotIn("AGENTS.md", self.state()["entries"])

    def test_copy_fingerprints_and_modified_withdrawal(self):
        self.run_install(mode="copy")
        self.assertFalse(self.target().is_symlink())
        self.assertTrue((self.target() / "assets/link").is_symlink())
        self.assertEqual(engine.fingerprint(self.target()), engine.fingerprint(self.sources["one"]))
        before = snapshot(self.root)
        self.run_install(mode="copy")
        self.assertEqual(snapshot(self.root), before)
        (self.target() / "SKILL.md").write_text("user edit")
        before = snapshot(self.root)
        with self.assertRaises(engine.InstallError):
            self.run_install(mode="copy", skills=[])
        self.assertEqual(snapshot(self.root), before)
        self.run_install(mode="copy", skills=[], onConflict="skip")
        self.assertEqual((self.target() / "SKILL.md").read_text(), "user edit")
        self.assertFalse(engine.exists(self.target("two")))
        self.assertNotIn(".agents/skills/one", self.state()["entries"])

    def test_cleanup_disabled_and_source_change_conflicts(self):
        self.run_install()
        self.run_install(skills=[], cleanup=False)
        self.assertTrue(self.target().is_symlink())
        changed = copy.deepcopy(self.manifest["skills"])
        changed[0]["source"] = str(self.sources["two"])
        # A new source with matching metadata must still not replace the old link.
        next_source = self.sources["one"].parent / "one-new"
        engine.shutil.copytree(self.sources["one"], next_source, symlinks=True)
        changed[0]["source"] = str(next_source)
        before = snapshot(self.root)
        with self.assertRaises(engine.InstallError):
            self.run_install(skills=changed)
        self.assertEqual(snapshot(self.root), before)
        self.run_install(skills=changed, onConflict="skip")
        self.assertEqual(os.readlink(self.target()), str(self.sources["one"]))
        self.target().unlink()
        self.run_install(skills=changed)
        self.assertEqual(os.readlink(self.target()), str(next_source))

    def test_invalid_source_and_target_collision_fail_before_writes(self):
        for data in ("bad", "---\nname: wrong\ndescription: test\n---", "---\nname: one\nname: one\ndescription: test\n---", "---\nname: one\ndescription: ''\n---"):
            (self.sources["one"] / "SKILL.md").write_text(data)
            before = snapshot(self.root)
            with self.assertRaises(engine.InstallError):
                self.run_install(onConflict="skip")
            self.assertEqual(snapshot(self.root), before)
        (self.sources["one"] / "SKILL.md").unlink()
        with self.assertRaises(engine.InstallError):
            self.run_install()
        (self.sources["one"] / "SKILL.md").write_text("---\nname: one\ndescription: Test\n---")
        self.manifest["targets"]["claude"] = {"enable": True, "path": ".agents/skills"}
        with self.assertRaises(engine.InstallError):
            self.run_install()
        self.assertEqual(snapshot(self.root), {"flake.nix": snapshot(self.root)["flake.nix"]})

    def test_symlinked_parent_and_edited_gitignore_fail_before_writes(self):
        (self.root / ".agents").symlink_to(self.sources["one"])
        before = snapshot(self.root)
        with self.assertRaises(engine.InstallError):
            self.run_install()
        self.assertEqual(snapshot(self.root), before)
        (self.root / ".agents").unlink()
        (self.root / ".gitignore").write_text("user-file\n")
        self.run_install()
        self.assertTrue((self.root / ".gitignore").read_text().startswith("user-file\n"))
        self.target("two").unlink()
        with (self.root / ".gitignore").open("a") as f:
            f.write("user-more\n")
        self.run_install()
        self.assertIn("user-more\n", (self.root / ".gitignore").read_text())
        text = (self.root / ".gitignore").read_text().replace("/AGENTS.md", "/user-edit")
        (self.root / ".gitignore").write_text(text)
        before = snapshot(self.root)
        with self.assertRaises(engine.InstallError):
            self.run_install(skills=[])
        self.assertEqual(snapshot(self.root), before)

    def test_legacy_state_migration_without_source_overwrite(self):
        self.run_install()
        state = self.state()
        links = {k: v["target"] for k, v in state["entries"].items() if v["kind"] == "link"}
        files = {"AGENTS.md": state["entries"]["AGENTS.md"]["hash"]}
        block = engine.LEGACY_START + "\n" + "\n".join(sorted({"/.agent-workspace/", "/AGENTS.md"} | {"/"+k for k in links})) + "\n" + engine.LEGACY_END + "\n"
        old = {"schemaVersion": 2, "owner": engine.LEGACY_OWNER, "links": links, "files": files, "gitignoreBlock": block}
        (self.root / ".agent-workspace/state.json").write_text(json.dumps(old))
        (self.root / ".gitignore").write_text("user\n" + block)
        self.run_install()
        self.assertEqual(self.state()["schemaVersion"], 3)
        self.assertIn(engine.START, (self.root / ".gitignore").read_text())

    def test_legacy_claude_link_change_is_a_conflict(self):
        self.manifest["claude"] = True
        self.manifest["targets"]["claude"]["enable"] = True
        self.run_install()
        state = self.state()
        links = {k: v["target"] for k, v in state["entries"].items() if v["kind"] == "link"}
        for name in self.sources:
            rel = f".claude/skills/{name}"
            (self.root / rel).unlink()
            links[rel] = f"../../.agents/skills/{name}"
            (self.root / rel).symlink_to(links[rel])
        block = engine.LEGACY_START + "\n" + "\n".join(sorted({"/.agent-workspace/", "/AGENTS.md"} | {"/"+k for k in links})) + "\n" + engine.LEGACY_END + "\n"
        legacy = {"schemaVersion": 2, "owner": engine.LEGACY_OWNER, "links": links,
                  "files": {"AGENTS.md": state["entries"]["AGENTS.md"]["hash"]}, "gitignoreBlock": block}
        (self.root / ".agent-workspace/state.json").write_text(json.dumps(legacy))
        (self.root / ".gitignore").write_text(block)
        before = snapshot(self.root)
        with self.assertRaises(engine.InstallError):
            self.run_install()
        self.assertEqual(snapshot(self.root), before)
        self.run_install(onConflict="skip")
        self.assertEqual(os.readlink(self.root / ".claude/skills/one"), "../../.agents/skills/one")
        self.assertEqual(self.state()["schemaVersion"], 3)

    def test_identical_external_copy_is_not_owned(self):
        self.target().parent.mkdir(parents=True)
        engine.shutil.copytree(self.sources["one"], self.target(), symlinks=True)
        self.run_install(mode="copy")
        self.assertNotIn(".agents/skills/one", self.state()["entries"])
        self.run_install(mode="copy", skills=[])
        self.assertTrue(self.target().is_dir())
        self.assertFalse(self.target("two").exists())

    def test_workspace_root_search_and_global_defaults(self):
        nested = self.root / "a/b"
        nested.mkdir(parents=True)
        previous = Path.cwd()
        os.chdir(nested)
        try:
            manifest = self.manifest | {"root": None}
            self.assertEqual(engine.root_for(manifest), self.root)
            (nested / "flake.nix").write_text("{}")
            self.assertEqual(engine.root_for(manifest), nested)
        finally:
            os.chdir(previous)
        self.run_install(scope="global", cleanup=False, manageInstructions=False, manageGitignore=False)
        self.assertTrue((self.root / ".local/state/agent-workspace/state.json").is_file())
        self.assertFalse((self.root / "AGENTS.md").exists())

    def test_parallel_installers_share_lock(self):
        manifest = self.root.parent / "manifest.json"
        manifest.write_text(json.dumps(self.manifest))
        command = [sys.executable, str(Path(engine.__file__)), str(manifest)]
        processes = [subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(4)]
        for process in processes:
            stdout, stderr = process.communicate(timeout=20)
            self.assertEqual(process.returncode, 0, stderr.decode())
        self.assertEqual(len(self.state()["entries"]), 3)
        self.assertFalse(list(self.root.rglob(".agent-workspace-*")))

    def test_atomic_create_does_not_clobber_new_external_entry(self):
        for kind in ("link", "file", "copy"):
            with self.subTest(kind=kind):
                path = self.root / f"race-{kind}"
                path.mkdir()
                (path / "user").write_text("external")
                before = snapshot(self.root)
                entry = {"kind": kind, "target": str(self.sources["one"]),
                         "hash": engine.fingerprint(self.sources["one"])}
                payload = b"instructions" if kind == "file" else self.sources["one"]
                with self.assertRaises(FileExistsError):
                    engine.create(path, entry, payload)
                self.assertEqual(snapshot(self.root), before)

    def test_reserved_destinations_are_rejected_before_writes(self):
        for path in (".gitignore", ".agent-workspace"):
            manifest = copy.deepcopy(self.manifest)
            manifest["targets"]["agents"]["path"] = path
            before = snapshot(self.root)
            with self.assertRaises(engine.InstallError):
                engine.activate(manifest, self.root)
            self.assertEqual(snapshot(self.root), before)
        # A skill cannot become an ancestor of the global state directory.
        (self.sources["one"] / "SKILL.md").write_text("---\nname: state\ndescription: Test\n---")
        manifest = self.manifest | {"scope": "global", "manageInstructions": False,
                                   "manageGitignore": False, "skills": [{"name": "state",
                                   "source": str(self.sources["one"]), "targets": ["agents"]}],
                                   "targets": {"agents": {"enable": True, "path": ".local"}}}
        before = snapshot(self.root)
        with self.assertRaises(engine.InstallError):
            engine.activate(manifest, self.root)
        self.assertEqual(snapshot(self.root), before)


if __name__ == "__main__":
    unittest.main()
