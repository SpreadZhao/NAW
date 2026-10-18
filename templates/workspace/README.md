# NAW workspace

Declare skills, targets, instructions and development tools in `flake.nix`.
Enter with `nix develop "path:$PWD"` or direnv, then reload after changing the
configuration or its sources.

NAW copies skills to the read-only Nix store and links the selected agent
directories. It generates `AGENTS.md` from `instructions`; selecting `claude`
also creates `CLAUDE.md` as a link to it. Edit the source files, not these links.

Initial setup refuses existing output paths, including empty directories and
identical links. Later runs update managed links using state under `.naw/`.
Maintain the template's `.gitignore` yourself.

See the [NAW documentation](https://github.com/SpreadZhao/NAW) for workspace
arguments, conflict handling and the separate Home Manager global-skills module.
