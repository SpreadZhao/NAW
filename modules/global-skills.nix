{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.programs.naw.globalSkills;
  source = import ../lib/skills.nix {
    inherit pkgs;
    inherit (cfg) skills;
  };
  directories = {
    agents = ".agents/skills";
    claude = ".claude/skills";
    codex = ".codex/skills";
  };
in
{
  options.programs.naw.globalSkills = {
    enable = lib.mkEnableOption "NAW global skill directories";
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
      description = "Agent directories managed by Home Manager.";
    };
  };
  config = lib.mkIf cfg.enable {
    home.file = lib.genAttrs (map (target: directories.${target}) (lib.unique cfg.targets)) (_: {
      inherit source;
      recursive = false;
    });
  };
}
