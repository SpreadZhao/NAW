# Agent workspace

Edit flake.nix to declare a catalog and select skills, then enter with nix develop.
This template starts without skills or business tools. Sources can be Nix paths,
derivations or pinned non-flake inputs.

The template references github:SpreadZhao/agent-workspace. For local development,
replace its input URL with a path: reference to your checkout or override it when locking.
Use a path: reference for an untracked flake, or track template files in Git.

claude = true enables Claude skills and CLAUDE.md. Explicit targets override the
target presets. Existing AGENTS.md conflicts by default: choose
manageInstructions = false or onConflict = "skip" to keep user instructions.

See the manager README for configuration, ownership, cleanup and GC roots.
