# NAW: Nix Agent Workspace

NAW manages agent skills and project workspaces with Nix. Use a project workspace
for skills, instructions and development tools, or Home Manager for global skills.
Both copy skill sources into the read-only Nix store without interpreting
`SKILL.md` or its metadata.

## Project workspaces

Create a project from the template, edit `flake.nix`, then enter its shell:

```sh
nix flake new -t github:SpreadZhao/NAW#workspace my-project
cd my-project
nix develop "path:$PWD"
```

The `path:` reference includes files that Git does not track yet. Declare the
project's skills, instructions and tools with `lib.mkWorkspace`:

```nix
{
  inputs.naw.url = "github:SpreadZhao/NAW";
  inputs.my-skills = {
    url = "github:example/skills";
    flake = false;
  };
  outputs = { naw, my-skills, ... }:
    naw.lib.mkWorkspace {
      skills.example = "${my-skills}/skills/example";
      targets = [ "agents" "claude" ];
      instructions = ''
        Project instructions go here.
      '';
      packages = pkgs: [ pkgs.git pkgs.ripgrep ];
    };
}
```

`mkWorkspace` returns `devShells.<system>.default` and
`checks.<system>.workspace`. On shell entry, the installer finds the nearest
ancestor containing `flake.nix`, prepares that workspace and sets
`NAW_WORKSPACE_ROOT` before running the optional `shellHook`.

| Argument | Default | Purpose |
| --- | --- | --- |
| `skills` | `{ }` | Map skill names to source paths or derivations |
| `targets` | `[ "agents" ]` | Select agent skill directories from the table below |
| `instructions` | `""` | Text written to `AGENTS.md` |
| `packages` | `pkgs: [ ]` | Development tools; a package list also works |
| `shellHook` | `""` | Shell code run after workspace setup |
| `systems` | `[ "x86_64-linux" "aarch64-linux" ]` | Platforms to build outputs for |

The installer links each selected skill directory to the store and always
creates `AGENTS.md`. Selecting `claude` also creates `CLAUDE.md` as a link to it.
Re-enter the shell after changing declarations or sources to update these links.
Removed targets are unlinked, and missing managed links are restored.

Initial setup refuses existing `AGENTS.md`, `CLAUDE.md` or selected skill paths,
including empty directories, identical links and broken links. Later runs refuse
modified managed links. Parent directories must be real directories, not symlinks.
Back up and move conflicting entries yourself; the installer does not adopt them.
Unselected agent skill directories are left alone.

Workspace state is under `.naw/`: `current` selects the active bundle and `roots/`
keeps it registered with Nix garbage collection. The installer locks the workspace
and replaces `current` atomically. Failures before that replacement roll back the
prepared links; power loss or forced termination may require manual recovery.
The packaged `naw-workspace-activate` command uses Bash, coreutils, util-linux and
Nix. `nix develop` invokes it automatically.

## Global skills

Import the module from your Home Manager configuration and select skills and targets:

```nix
{ inputs, ... }:
{
  imports = [ inputs.naw.homeManagerModules.globalSkills ];

  programs.naw.globalSkills = {
    enable = true;
    skills.example = "${inputs.my-skills}/skills/example";
    targets = [ "agents" "claude" ];
  };
}
```

This module exposes `enable`, `skills` and `targets`. It links each selected
skill directory through Home Manager's `home.file`. Updates, removal, conflicts
and dry runs follow Home Manager's normal behavior, without forced overwrites
or automatic backups. Back up conflicting files before applying the configuration.

Global skills do not generate project instructions or run the workspace installer.
They have no separate NAW state directory or extra GC roots.

## Sources and target paths

Both interfaces accept local Nix paths, locked inputs and derivations. Keep
sources outside generated directories and edit those sources, not the store copy.

| Target | Path relative to the project root or home directory |
| --- | --- |
| `agents` | `.agents/skills` |
| `claude` | `.claude/skills` |
| `codex` | `.codex/skills` |

Project and global installations have separate lifecycles. Reload a project
shell for workspace changes; apply Home Manager for global changes. NAW does
not manage `.gitignore`, Git configuration or the index. The template's
`.gitignore` is an ordinary project file.

Legacy interfaces and state have no automatic migration. Back up and move old
generated files before setup, retaining the original skill and instruction sources.

## Develop NAW

This repository uses its local `lib.mkWorkspace` for development. Enter with
`nix develop "path:$PWD"` while new sources are untracked, or use `nix develop`
and direnv once they are tracked. The shell provides nixfmt, ShellCheck, shfmt,
Statix, deadnix, Git and ripgrep.

NAW installs its local `naw-development` skill for agents and Claude and generates
their instructions from `flake.nix`. Edit that source and `skills/`, then re-enter
the shell. Generated links and `.naw/` state are ignored by Git.

Run `nix flake check "path:$PWD"` to check the exports and build the workspace
bundle. For installer changes, also test the affected behavior in an isolated
temporary workspace. See the [development skill](skills/naw-development/SKILL.md)
for module ownership and maintenance constraints.
