{
  description = "Agent workspace";
  inputs.agent-workspace.url = "github:SpreadZhao/agent-workspace";
  outputs =
    { agent-workspace, ... }:
    agent-workspace.lib.mkWorkspace {
      catalog = { };
      skills = [ ];
      # extraSkills.my-skill = ./skills/my-skill;
      packages = pkgs: [
        pkgs.git
        pkgs.ripgrep
      ];
      claude = false;
      instructions = "";
    };
}
