{
  pkgs,
  skills,
  targets,
  instructions,
}:
let
  inherit (pkgs) lib;
  skillsDirectory = import ./skills.nix { inherit pkgs skills; };
  directories = {
    agents = ".agents/skills";
    claude = ".claude/skills";
    codex = ".codex/skills";
  };
  paths =
    map (target: directories.${target}) (lib.unique targets)
    ++ [ "AGENTS.md" ]
    ++ lib.optional (builtins.elem "claude" targets) "CLAUDE.md";
  links = pkgs.writeText "naw-workspace-links" (lib.concatMapStrings (path: path + "\n") paths);
  document = pkgs.writeText "naw-workspace-instructions" instructions;
  bundle = pkgs.runCommand "naw-workspace" { } ''
    mkdir -p "$out"
    ln -s ${skillsDirectory} "$out/skills"
    cp ${links} "$out/links"
    cp ${document} "$out/AGENTS.md"
  '';
  program = pkgs.writeShellApplication {
    name = "naw-workspace-activate";
    runtimeInputs = [
      pkgs.coreutils
      pkgs.util-linux
      pkgs.nix
    ];
    text = ''
      exec ${pkgs.bash}/bin/bash ${../runtime/workspace.sh} ${bundle}
    '';
  };
in
program // { passthru = { inherit bundle; }; }
