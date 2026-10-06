agentLib:
{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.programs.agent-workspace;
  installer = agentLib.mkSkillInstaller {
    inherit pkgs;
    inherit (cfg)
      catalog
      skills
      extraSkills
      targets
      mode
      onConflict
      cleanup
      ;
    root = config.home.homeDirectory;
    scope = "global";
  };
in
{
  options.programs.agent-workspace = {
    enable = lib.mkEnableOption "declarative agent skill installation";
    catalog = lib.mkOption {
      type = lib.types.attrs;
      default = { };
      description = "Skill names mapped to source paths or source/subdir/targets records.";
    };
    skills = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [ ];
      description = "Explicit catalog selection.";
    };
    extraSkills = lib.mkOption {
      type = lib.types.attrs;
      default = { };
      description = "Additional sources selected automatically.";
    };
    targets = lib.mkOption {
      type = lib.types.attrsOf (
        lib.types.submodule (
          { name, ... }: {
            options = {
              enable = lib.mkOption {
                type = lib.types.bool;
                default =
                  {
                    agents = true;
                    claude = false;
                    codex = false;
                  }
                  .${name} or true;
                description = "Enable this target.";
              };
              path = lib.mkOption {
                type = lib.types.str;
                default =
                  {
                    agents = ".agents/skills";
                    claude = ".claude/skills";
                    codex = ".codex/skills";
                  }
                  .${name} or (throw "agent-workspace: custom target ${name} needs a path");
                description = "Destination directory relative to the home directory.";
              };
            };
          }
        )
      );
      default = { };
      description = "Agent target overrides; agents is enabled by default.";
    };
    mode = lib.mkOption {
      type = lib.types.enum [
        "symlink"
        "copy"
      ];
      default = "symlink";
      description = "Install links or writable copies.";
    };
    onConflict = lib.mkOption {
      type = lib.types.enum [
        "error"
        "skip"
      ];
      default = "skip";
      description = "Fail before writes or preserve conflicting entries.";
    };
    cleanup = lib.mkOption {
      type = lib.types.bool;
      default = false;
      description = "Remove unchanged managed entries that are no longer selected.";
    };
  };
  config = lib.mkIf cfg.enable {
    home.activation.installGlobalSkills = lib.hm.dag.entryAfter [ "linkGeneration" ] ''
      if [[ ! -v DRY_RUN ]]; then
        ${installer}/bin/agent-workspace-install >/dev/null
      fi
    '';
  };
}
