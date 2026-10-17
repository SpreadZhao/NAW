{
  description = "NAW project workspace";
  inputs.naw.url = "github:SpreadZhao/NAW";
  outputs =
    { naw, ... }:
    naw.lib.mkWorkspace {
      skills = { };
      targets = [ "agents" ];
      instructions = "";
      packages = pkgs: [
        pkgs.git
        pkgs.ripgrep
      ];
    };
}
