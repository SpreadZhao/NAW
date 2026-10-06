"""Run local Nix integration checks without touching real user/workspace targets.

Usage: nix develop path:$PWD -c python tests/integration.py /absolute/manager
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_install import snapshot


def run(root, *args, success=True):
    result = subprocess.run(args, cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if (result.returncode == 0) != success:
        raise AssertionError(f"{args}\n{result.stdout}\n{result.stderr}")
    return result


manager = Path(sys.argv[1]).resolve()
with tempfile.TemporaryDirectory(prefix="agent-workspace-integration-") as temporary:
    root = Path(temporary) / "project"
    root.mkdir()
    run(root, "nix", "flake", "init", "-t", f"path:{manager}#workspace")
    flake = root / "flake.nix"
    flake.write_text(flake.read_text().replace("catalog = { };", 'extraSkills.one = "${agent-workspace}/tests/fixtures/one";').replace("claude = false;", "claude = true;"))
    assert "spreadconfig" not in flake.read_text()
    run(root, "nix", "flake", "lock", "--override-input", "agent-workspace", f"path:{manager}")
    run(root, "nix", "develop", f"path:{root}", "-c", "true")
    target = root / ".agents/skills/one"
    assert target.is_symlink() and (root / ".claude/skills/one").is_symlink()
    assert os.readlink(root / "CLAUDE.md") == "AGENTS.md"
    state = json.loads((root / ".agent-workspace/state.json").read_text())
    roots = state["roots"]
    assert roots and all((root / item).is_symlink() for item in roots)
    before = snapshot(root)
    run(root, "nix", "develop", f"path:{root}", "-c", "true")
    assert snapshot(root) == before, "second nix develop changed managed content"
    # Nix must register the indirect root at the workspace's new location.
    moved = root.parent / "moved"
    shutil.move(root, moved)
    root = moved
    run(root, "nix", "develop", f"path:{root}", "-c", "true")
    root_query = run(root, "nix-store", "--query", "--roots", os.readlink(root / roots[0])).stdout
    assert str(root / roots[0]) in root_query, root_query
    # An unowned instruction file conflicts before installing a missing skill.
    target = root / ".agents/skills/one"
    target.unlink()
    shutil.rmtree(root / ".agent-workspace")
    (root / ".gitignore").unlink()
    before = snapshot(root)
    run(root, "nix", "develop", f"path:{root}", "-c", "true", success=False)
    assert snapshot(root) == before, "conflict left workspace changes"
    flake = root / "flake.nix"
    flake.write_text(flake.read_text().replace("claude = true;", "claude = true;\n      manageInstructions = false;\n      manageGitignore = false;"))
    run(root, "nix", "develop", f"path:{root}", "-c", "true")
    assert target.is_symlink()
    assert not (root / ".gitignore").exists()
    # The activation flag must suppress all workspace writes.
    inactive = root.parent / "inactive"
    inactive.mkdir()
    (inactive / "flake.nix").write_text(flake.read_text().replace("claude = true;", "claude = true;\n      autoActivate = false;"))
    shutil.copy2(root / "flake.lock", inactive / "flake.lock")
    before = snapshot(inactive)
    run(inactive, "nix", "develop", f"path:{inactive}", "-c", "true")
    assert snapshot(inactive) == before
    local = root.parent / "local-source"
    local.mkdir()
    (local / "skills").mkdir()
    shutil.copytree(manager / "tests/fixtures/one", local / "skills/one")
    (local / "flake.nix").write_text(flake.read_text().replace(
        '"${agent-workspace}/tests/fixtures/one"', './skills/one'))
    shutil.copy2(root / "flake.lock", local / "flake.lock")
    run(local, "nix", "develop", f"path:{local}", "-c", "true")
    before = snapshot(local)
    run(local, "nix", "develop", f"path:{local}", "-c", "true")
    assert snapshot(local) == before, "a local Nix path changed across activations"
print("Independent template, nix develop, input/local sources, idempotence, Claude, conflicts, switches and moved GC roots: passed")
