---
name: naw-development
description: Maintain NAW's Nix workspace library, Bash installer, Home Manager module, and project template.
---

# NAW development

## Code ownership

- `lib/default.nix` defines `mkWorkspace` and its development-shell outputs.
  The root flake uses this local library for NAW's own workspace; keep its library,
  Home Manager, and template exports available to consumers.
- `lib/skills.nix` copies skill sources without interpreting `SKILL.md` or adding
  content validation. `lib/workspace.nix` builds the workspace bundle and installer.
- `runtime/workspace.sh` owns project setup, updates, conflict checks, and rollback.
  It manages selected skill directories, instruction links, and `.naw/` state.
- `modules/global-skills.nix` uses native Home Manager `home.file` behavior.
  Keep its lifecycle separate from the project installer.
- `templates/workspace/` is the consumer starting point, not NAW's own devShell.

## Maintenance constraints

Preserve first-install conflict checks, managed-link ownership, real-directory
parents, and rollback before the `current` link changes. Updates may replace only
NAW-owned links. Git configuration, the index, and `.gitignore` belong to the user.

Workspace outputs support `x86_64-linux` and `aarch64-linux`. Check target paths
and defaults in both public entry points when changing the API, and update the
consumer template and README together. Keep skill sources outside generated paths.

## Validation

Use `nix develop "path:$PWD"` while new files are untracked. Once sources are
tracked, `nix develop` or the root `.envrc` loads the same workspace.

Run nixfmt on changed Nix files and `git diff --check`. For installer changes,
run `bash -n`, ShellCheck, and shfmt, then exercise affected setup, reload, conflict,
or rollback behavior in a temporary workspace outside the checkout.

Run `nix flake check "path:$PWD"` to evaluate the exports and build the local
workspace bundle. A bundle build assembles generated files; it does not exercise
the installer. Test runtime changes separately and remove temporary files.
