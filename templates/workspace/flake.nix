{
  description = "Agent workspace";
  inputs.agent-workspace.url = "github:SpreadZhao/agent-workspace";
  outputs =
    { agent-workspace, ... }:
    agent-workspace.lib.mkWorkspace {
      skills = { };
      targets = [ "agents" ];
      instructions = "";
      packages = pkgs: [
        pkgs.git
        pkgs.ripgrep
      ];
    };
}
