#!/usr/bin/env python3
"""Preflight and install skill entries without replacing existing content."""

import ctypes
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile

import yaml


OWNER = "agent-workspace"
LEGACY_OWNER = "spreadconfig-workspace"
START = "# >>> agent workspace (managed) >>>"
END = "# <<< agent workspace (managed) <<<"
LEGACY_START = "# >>> spreadconfig workspace (managed) >>>"
LEGACY_END = "# <<< spreadconfig workspace (managed) <<<"
NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
HASH = re.compile(r"[0-9a-f]{64}\Z")


class InstallError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise InstallError(message)


def exists(path):
    return os.path.lexists(path)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, f"duplicate JSON key: {key}")
            result[key] = value
        return result
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)


def relative(value):
    require(isinstance(value, str) and value and "\0" not in value
            and "\\" not in value and not PurePosixPath(value).is_absolute()
            and all(part not in ("", ".", "..") for part in value.split("/")),
            f"unsafe relative path: {value!r}")
    return value


def check_skill(source, name):
    require(isinstance(name, str) and len(name) <= 64 and NAME.fullmatch(name),
            f"invalid skill name: {name!r}")
    file = source / "SKILL.md"
    require(source.is_dir() and file.is_file(), f"missing SKILL.md: {source}")
    lines = file.read_text(encoding="utf-8").splitlines()
    require(lines and lines[0] == "---", f"missing frontmatter: {file}")
    try:
        end = lines.index("---", 1)
    except ValueError:
        raise InstallError(f"unterminated frontmatter: {file}") from None
    class UniqueLoader(yaml.SafeLoader):
        pass
    def mapping(loader, node, deep=False):
        pairs = loader.construct_pairs(node, deep=deep)
        result = {}
        for key, value in pairs:
            require(key not in result, f"duplicate frontmatter field in {file}: {key}")
            result[key] = value
        return result
    UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
    header = yaml.load("\n".join(lines[1:end]), Loader=UniqueLoader)
    require(isinstance(header, dict) and header.get("name") == name,
            f"skill name mismatch in {file}: expected {name}")
    description = header.get("description")
    require(isinstance(description, str) and description.strip()
            and len(description) <= 1024, f"invalid description: {file}")


def fingerprint(path):
    """Include contents, directory structure, link text and executable bits."""
    h = hashlib.sha256()
    def add(data):
        h.update(len(data).to_bytes(8, "big"))
        h.update(data)
    def walk(item, name):
        info = item.lstat()
        add(os.fsencode(name))
        if stat.S_ISLNK(info.st_mode):
            add(b"link")
            add(os.fsencode(os.readlink(item)))
        elif stat.S_ISREG(info.st_mode):
            add(b"file")
            add(str(info.st_mode & 0o111).encode())
            content = hashlib.sha256()
            with item.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    content.update(chunk)
            add(content.digest())
        elif stat.S_ISDIR(info.st_mode):
            add(b"dir")
            for child in sorted(item.iterdir()):
                walk(child, f"{name}/{child.name}")
        else:
            raise InstallError(f"unsupported file type: {item}")
    walk(path, "")
    return h.hexdigest()


def matches(path, entry):
    if not exists(path):
        return False
    kind = entry["kind"]
    if kind == "link":
        return path.is_symlink() and os.readlink(path) == entry["target"]
    if path.is_symlink():
        return False
    if kind == "file":
        return path.is_file() and digest(path.read_bytes()) == entry["hash"]
    return path.is_dir() and fingerprint(path) == entry["hash"]


def parents_clear(root, rel):
    current = root
    for part in PurePosixPath(rel).parts[:-1]:
        current /= part
        require(not current.is_symlink(), f"symlinked output parent: {current}")
        require(not exists(current) or current.is_dir(), f"output parent is not a directory: {current}")


def state_paths(scope):
    directory = ".agent-workspace" if scope == "workspace" else ".local/state/agent-workspace"
    return directory, f"{directory}/state.json"


def load_state(root, scope):
    directory, state_path = state_paths(scope)
    parents_clear(root, state_path)
    path = root / state_path
    if not exists(path):
        return {"entries": {}, "roots": [], "gitignoreBlock": None}
    require(path.is_file() and not path.is_symlink(), f"invalid state file: {path}")
    state = read_json(path)
    if state.get("schemaVersion") == 2 and scope == "workspace":
        require(state.get("owner") == LEGACY_OWNER, "unrecognized legacy state owner")
        links, files = state.get("links"), state.get("files")
        require(isinstance(links, dict) and isinstance(files, dict), "invalid legacy state")
        entries = {}
        for rel, target in links.items():
            if rel == ".agent-workspace/store":
                require(isinstance(target, str) and target.startswith("/nix/store/"), "invalid legacy GC root")
                continue
            require((rel == "CLAUDE.md" and target == "AGENTS.md") or
                    (any(rel.startswith(prefix) for prefix in [".agents/skills/", ".claude/skills/"])
                     and (str(target).startswith("/") or str(target).startswith("../../.agents/skills/"))),
                    f"invalid legacy link: {rel}")
            entries[relative(rel)] = {"kind": "link", "target": target}
        require(set(files) == {"AGENTS.md"}, "invalid legacy generated files")
        entries["AGENTS.md"] = {"kind": "file", "hash": files["AGENTS.md"]}
        state = {"schemaVersion": 3, "owner": OWNER, "entries": entries,
                 "roots": [".agent-workspace/store"], "gitignoreBlock": state.get("gitignoreBlock")}
        expected = LEGACY_START + "\n" + "\n".join(sorted(
            {"/.agent-workspace/", "/AGENTS.md"} | {"/" + k for k in entries}
        )) + "\n" + LEGACY_END + "\n"
        require(state["gitignoreBlock"] == expected, "invalid legacy ignore block")
    require(state.get("schemaVersion") == 3 and state.get("owner") == OWNER,
            "unrecognized state schema or owner")
    require(set(state) == {"schemaVersion", "owner", "entries", "roots", "gitignoreBlock"},
            "invalid state fields")
    require(isinstance(state["entries"], dict) and isinstance(state["roots"], list), "invalid state entries")
    for rel, entry in state["entries"].items():
        relative(rel)
        require(not (rel == directory or rel.startswith(directory + "/") or directory.startswith(rel + "/"))
                and rel != ".gitignore" and not rel.startswith(".gitignore/"), "reserved state path")
        require(isinstance(entry, dict), "invalid state entry")
        if entry.get("kind") == "link":
            require(set(entry) == {"kind", "target"} and isinstance(entry["target"], str)
                    and "\0" not in entry["target"], "invalid state link")
        else:
            require(entry.get("kind") in ("file", "copy") and set(entry) == {"kind", "hash"}
                    and isinstance(entry["hash"], str) and HASH.fullmatch(entry["hash"]), "invalid state fingerprint")
    for rel in state["roots"]:
        relative(rel)
        require(rel == f"{directory}/store" or rel.startswith(f"{directory}/roots/"), "invalid state GC root")
        parents_clear(root, rel)
        if exists(root / rel):
            require((root / rel).is_symlink() and os.readlink(root / rel).startswith("/nix/store/"), "invalid GC root link")
    require(state["gitignoreBlock"] is None or isinstance(state["gitignoreBlock"], str), "invalid ignore block")
    return state


def root_for(manifest):
    explicit = manifest.get("root")
    if explicit is not None:
        root = Path(explicit).expanduser()
        require(root.is_absolute(), "root must be absolute")
        root = root.resolve(strict=True)
    elif manifest["scope"] == "global":
        root = Path.home().resolve(strict=True)
    else:
        root = Path.cwd().resolve(strict=True)
        while not (root / "flake.nix").is_file():
            require(root.parent != root, "no flake.nix above current directory; configure workspaceRoot")
            root = root.parent
    require(root.is_dir() and not root.is_relative_to(Path("/nix/store")), "invalid installation root")
    if manifest["scope"] == "workspace":
        require((root / "flake.nix").is_file(), f"workspace root needs flake.nix: {root}")
    return root


def prepare(manifest):
    require(manifest.get("schemaVersion") == 3, "unsupported manifest")
    require(manifest.get("scope") in ("workspace", "global"), "invalid scope")
    require(manifest.get("onConflict") in ("error", "skip"), "invalid onConflict")
    require(manifest.get("mode") in ("symlink", "copy"), "invalid installation mode")
    for field in ("cleanup", "manageInstructions", "manageGitignore", "claude"):
        require(type(manifest.get(field)) is bool, f"invalid {field}")
    require(isinstance(manifest.get("instructions"), str), "invalid instructions")
    bundle = Path(manifest["bundle"])
    require(bundle.is_absolute() and bundle.is_dir(), "missing built skill bundle")
    desired = {}
    def add(rel, entry, payload=None):
        relative(rel)
        require(rel not in desired, f"duplicate target: {rel}")
        desired[rel] = (entry, payload)
    targets = manifest["targets"]
    for skill in manifest["skills"]:
        source = Path(skill["source"])
        require(source.is_absolute(), "skill source must be absolute")
        check_skill(source, skill["name"])
        for target in skill["targets"]:
            require(target in targets, f"unknown target: {target}")
            if not targets[target]["enable"]:
                continue
            dest = relative(targets[target]["path"])
            rel = f"{dest}/{skill['name']}"
            if manifest["mode"] == "symlink":
                add(rel, {"kind": "link", "target": str(source)})
            else:
                # Match executable bits after materializing writable store copies.
                add(rel, {"kind": "copy", "hash": fingerprint(source)}, source)
    if manifest["scope"] == "workspace" and manifest["manageInstructions"]:
        enabled = ([targets["agents"]["path"]] if targets.get("agents", {}).get("enable")
                   else [t["path"] for t in targets.values() if t["enable"]])
        text = "# Workspace Instructions\n\n"
        if enabled:
            text += "Skills are available under " + ", ".join(f"`{p}`" for p in dict.fromkeys(enabled)) + ".\n"
        if manifest["instructions"]:
            text += "\n" + manifest["instructions"].rstrip() + "\n"
        add("AGENTS.md", {"kind": "file", "hash": digest(text.encode())}, text.encode())
        if manifest["claude"]:
            add("CLAUDE.md", {"kind": "link", "target": "AGENTS.md"})
    directory, _ = state_paths(manifest["scope"])
    for rel in desired:
        require(not (rel == directory or rel.startswith(directory + "/") or directory.startswith(rel + "/"))
                and rel != ".gitignore" and not rel.startswith(".gitignore/"), f"reserved output path: {rel}")
        require(not any(other != rel and rel.startswith(other + "/") for other in desired),
                f"overlapping targets: {rel}")
    return desired


def gitignore_plan(root, old, entries, enabled):
    previous = old.get("gitignoreBlock")
    if not enabled and previous is None:
        return None, None
    path = root / ".gitignore"
    require(not path.is_symlink() and (not exists(path) or path.is_file()), "invalid .gitignore")
    text = path.read_text(encoding="utf-8") if exists(path) else ""
    if previous is not None:
        require(text.count(previous) == 1, "managed .gitignore block was removed or edited")
        prefix = text.replace(previous, "", 1)
    else:
        require(not any(marker in text for marker in (START, END, LEGACY_START, LEGACY_END)), "unowned .gitignore block")
        prefix = text
    if not enabled:
        return prefix.encode(), None
    block = START + "\n" + "\n".join(sorted({"/.agent-workspace/"} | {"/" + rel for rel in entries})) + "\n" + END + "\n"
    if previous is not None:
        # Preserve the exact position and all user-maintained lines.
        return text.replace(previous, block, 1).encode(), block
    return (prefix + ("" if not prefix or prefix.endswith("\n") else "\n") + block).encode(), block


def atomic_file(path, data, mode=0o644):
    if path.is_file() and not path.is_symlink() and path.read_bytes() == data:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".agent-workspace-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fchmod(stream.fileno(), mode)
        os.replace(temporary, path)
    finally:
        if os.path.lexists(temporary):
            os.unlink(temporary)


def create(path, entry, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    if entry["kind"] == "link":
        path.symlink_to(entry["target"])
        return
    directory = Path(tempfile.mkdtemp(prefix=".agent-workspace-", dir=path.parent))
    temporary = directory / "entry"
    try:
        if entry["kind"] == "file":
            temporary.write_bytes(payload)
            temporary.chmod(0o644)
            os.link(temporary, path)
            return
        else:
            shutil.copytree(payload, temporary, symlinks=True)
            for item in [temporary, *temporary.rglob("*")]:
                if not item.is_symlink():
                    os.chmod(item, item.stat().st_mode | stat.S_IWUSR)
            require(fingerprint(temporary) == entry["hash"], f"source changed while copying: {payload}")
        # Linux renameat2 commits a directory atomically without clobbering an
        # entry created outside our cooperative lock after preflight.
        libc = ctypes.CDLL(None, use_errno=True)
        result = libc.renameat2(-100, os.fsencode(temporary), -100, os.fsencode(path), 1)
        if result != 0:
            errno = ctypes.get_errno()
            raise OSError(errno, os.strerror(errno), str(path))
    finally:
        shutil.rmtree(directory)


def remove(path):
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def activate(manifest, root):
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        desired = prepare(manifest)
        old = load_state(root, manifest["scope"])
        owned = dict(old["entries"])
        installs, removals = [], []
        skipped = []
        def conflict(message):
            if manifest["onConflict"] == "error":
                raise InstallError(message)
            skipped.append(message)
        for rel, (entry, payload) in desired.items():
            try:
                parents_clear(root, rel)
            except InstallError as error:
                conflict(str(error))
                owned.pop(rel, None)
                continue
            path = root / rel
            if exists(path):
                if rel == "AGENTS.md" and rel not in old["entries"]:
                    conflict(f"unmanaged instruction file: {path}")
                    continue
                if matches(path, entry):
                    if rel in old["entries"] and matches(path, old["entries"][rel]):
                        owned[rel] = entry
                    # Identical external content is not adopted.
                    continue
                conflict(f"target conflicts with desired result: {path}")
                if rel in owned and not matches(path, owned[rel]):
                    owned.pop(rel)
            else:
                installs.append((rel, entry, payload))
                owned[rel] = entry
        for rel in sorted(set(old["entries"]) - set(desired)):
            if not manifest["cleanup"]:
                continue
            try:
                parents_clear(root, rel)
            except InstallError as error:
                conflict(str(error))
                owned.pop(rel, None)
                continue
            path = root / rel
            if exists(path):
                if matches(path, old["entries"][rel]):
                    removals.append(rel)
                else:
                    conflict(f"removed entry was modified: {path}")
            owned.pop(rel, None)
        ignore_data, block = None, old.get("gitignoreBlock")
        if manifest["scope"] == "workspace":
            try:
                ignore_data, block = gitignore_plan(root, old, owned, manifest["manageGitignore"])
            except InstallError as error:
                conflict(str(error))
        directory, state_path = state_paths(manifest["scope"])
        # Check reserved parents even on a first activation, before any writes.
        parents_clear(root, f"{directory}/roots/root")
        bundle = manifest["bundle"]
        roots = list(old["roots"])
        if str(bundle).startswith("/nix/store/"):
            gc_path = f"{directory}/roots/{digest(str(bundle).encode())}"
            parents_clear(root, gc_path)
            if exists(root / gc_path):
                require((root / gc_path).is_symlink() and os.readlink(root / gc_path) == str(bundle), "GC root conflict")
            (root / gc_path).parent.mkdir(parents=True, exist_ok=True)
            # Re-register indirect roots after a workspace has moved. Nix keeps
            # an identical direct link unchanged.
            subprocess.run(["nix-store", "--add-root", str(root / gc_path), "--indirect", "--realise", str(bundle)],
                           check=True, stdout=subprocess.DEVNULL, timeout=60)
            if gc_path not in roots:
                roots.append(gc_path)
        for rel in removals:
            remove(root / rel)
        for rel, entry, payload in installs:
            create(root / rel, entry, payload)
        if ignore_data is not None:
            atomic_file(root / ".gitignore", ignore_data)
        state = {"schemaVersion": 3, "owner": OWNER, "entries": owned,
                 "roots": roots, "gitignoreBlock": block}
        atomic_file(root / state_path, (json.dumps(state, indent=2, ensure_ascii=False) + "\n").encode(), 0o600)
        for message in skipped:
            print(f"agent-workspace: skipped: {message}", file=sys.stderr)
    finally:
        os.close(descriptor)


def main():
    try:
        require(len(sys.argv) in (2, 3), "usage: install.py MANIFEST [--validate]")
        manifest = read_json(Path(sys.argv[1]))
        if len(sys.argv) == 3:
            require(sys.argv[2] == "--validate", "unknown argument")
            prepare(manifest)
            return 0
        root = root_for(manifest)
        activate(manifest, root)
        print(root)
        return 0
    except (InstallError, OSError, ValueError, TypeError, KeyError, yaml.YAMLError,
            subprocess.SubprocessError) as error:
        print(f"agent-workspace: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
