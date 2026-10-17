# Agent workspace

Declare `skills`, `targets`, `instructions` and development `packages` in flake.nix,
then enter with `nix develop path:$PWD` or direnv. Local sources and remote inputs
are copied into the Nix Store. Skill content is not validated.

Enabled skill directories are whole-directory links to read-only generated content.
AGENTS.md is generated from `instructions`; adding `"claude"` to `targets` also
generates CLAUDE.md. Edit the Nix declarations and their sources, then reload.

Any existing target, even an empty directory or identical link, prevents initial
installation. Managed links update on reload. Old manager state is not migrated.
The template's .gitignore is an ordinary editable file; the manager never touches it.

See the agent-workspace README for the interface and Home Manager integration.
