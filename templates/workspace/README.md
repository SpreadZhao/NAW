# NAW Workspace

Declare `skills`, `targets`, `instructions` and development `packages` in flake.nix,
then enter with `nix develop path:$PWD` or direnv. Sources are copied into the Nix
Store without validating Skill content.

NAW links enabled skill directories to read-only content. AGENTS.md is generated
from `instructions`; adding `"claude"` to `targets` also generates CLAUDE.md.
Edit the declarations and their sources, then reload.

Existing targets, including empty directories and identical links, prevent initial
installation. Managed links update on reload; state is kept under `.naw/`.
The template's .gitignore is an ordinary editable file and is not managed by NAW.

Global skills use the separate `homeManagerModules.globalSkills` module.
See the NAW README for both interfaces.
