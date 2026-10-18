{
  description = "Manage agent skills and project workspaces with Nix and Home Manager";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  outputs =
    { nixpkgs, ... }:
    let
      nawLib = import ./lib { inherit nixpkgs; };
      workspace = nawLib.mkWorkspace {
        skills.naw-development = ./skills/naw-development;
        targets = [
          "agents"
          "claude"
        ];
        instructions = ''
          # NAW development

          Use the `naw-development` skill for changes to the library, installer,
          Home Manager module, templates, or this repository's workspace.
          Edit workspace instructions in `flake.nix` and skill sources under
          `skills/`; `AGENTS.md`, `CLAUDE.md`, and installed skills are generated.

          ## Repository policy

          - Keep documentation, comments, help text, and prompts in English.
          - Never execute Nix `switch` commands, including wrappers that default
            to `switch`. Builds, evaluation, formatting, and project workspace
            setup are allowed. The user performs system and Home Manager switches.
          - Preserve unrelated changes. Keep temporary tests, fixtures, logs, and
            reports outside the repository and remove them before finishing.
            Retain tests only when the user asks. Stop temporary processes and
            remove test-only dependencies without deleting shared store contents.
          - If cleanup requires a prohibited switch, prepare the change and report
            what remains with the manual command; do not claim cleanup is complete.

          ## Final writing review

          After the main work and checks, launch a separate writing-review agent.
          Ask it to read https://github.com/weijt606/anti-vibe-writing, including
          `SKILL.md`, the English patterns reference, and the final-pass checklist.
          Use its default clean style to edit task-related documentation, comments,
          help, and prompts for accuracy and concise English. Remove stale claims
          and obsolete commented-out code, and merge repetition while preserving
          behavior, identifiers, commands, paths, and license notices. The reviewer
          must not launch another reviewer and should report when no edits are needed.
          Review its diff, rerun affected checks, and finish cleanup before replying.
        '';
        packages =
          pkgs: with pkgs; [
            deadnix
            git
            nixfmt
            ripgrep
            shellcheck
            shfmt
            statix
          ];
      };
      template = {
        path = ./templates/workspace;
        description = "Project shell with agent skills and instructions";
      };
    in
    {
      lib = nawLib;
      inherit (workspace) devShells checks;
      homeManagerModules.globalSkills = import ./modules/global-skills.nix;
      templates = {
        default = template;
        workspace = template;
      };
    };
}
