{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.programs.agent-workspace;
  installer = import ../lib/installer.nix {
    inherit pkgs;
    inherit (cfg) skills targets;
    scope = "global";
    root = config.home.homeDirectory;
  };
in
{
  options.programs.agent-workspace = {
    enable = lib.mkEnableOption "declarative agent skill directories";
    skills = lib.mkOption {
      type = lib.types.attrsOf lib.types.anything;
      default = { };
      description = "Skill names mapped directly to Nix sources.";
    };
    targets = lib.mkOption {
      type = lib.types.listOf (
        lib.types.enum [
          "agents"
          "claude"
          "codex"
        ]
      );
      default = [ "agents" ];
      description = "Agent directories owned by this configuration.";
    };
  };
  config = lib.mkIf cfg.enable {
    home.activation.installAgentWorkspace = lib.hm.dag.entryAfter [ "linkGeneration" ] ''
      if [[ ! -v DRY_RUN ]]; then
        ${installer}/bin/agent-workspace-install >/dev/null
      fi
    '';
  };
}
