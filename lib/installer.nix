{
  pkgs,
  skills ? { },
  targets ? [ "agents" ],
  instructions ? "",
  scope,
  root ? "",
}:
let
  inherit (pkgs) lib;
  directories = {
    agents = ".agents/skills";
    claude = ".claude/skills";
    codex = ".codex/skills";
  };
  paths =
    map (target: directories.${target}) (lib.unique targets)
    ++ lib.optionals (scope == "workspace") (
      [ "AGENTS.md" ] ++ lib.optional (builtins.elem "claude" targets) "CLAUDE.md"
    );
  links = pkgs.writeText "agent-workspace-links" (lib.concatMapStrings (path: path + "\n") paths);
  document = pkgs.writeText "agent-workspace-instructions" instructions;
  bundle = pkgs.runCommand "agent-workspace" { } (
    ''
      mkdir -p "$out/skills"
      cp ${links} "$out/links"
    ''
    + lib.concatStrings (
      lib.mapAttrsToList (name: source: ''
        cp -RL -- ${lib.escapeShellArg "${source}"} "$out/skills/"${lib.escapeShellArg name}
      '') skills
    )
    + lib.optionalString (scope == "workspace") ''
      cp ${document} "$out/AGENTS.md"
    ''
  );
  program = pkgs.writeShellApplication {
    name = "agent-workspace-install";
    runtimeInputs = [
      pkgs.coreutils
      pkgs.util-linux
      pkgs.nix
    ];
    text = ''
      exec ${pkgs.bash}/bin/bash ${../runtime/install.sh} \
        ${lib.escapeShellArg scope} ${bundle} ${lib.escapeShellArg root}
    '';
  };
in
program // { passthru = { inherit bundle; }; }
