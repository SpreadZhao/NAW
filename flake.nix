{
  description = "NAW (Nix-Agent-Workspace): project workspaces and global skills";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  outputs =
    { nixpkgs, ... }:
    let
      template = {
        path = ./templates/workspace;
        description = "Minimal NAW project workspace";
      };
    in
    {
      lib = import ./lib { inherit nixpkgs; };
      homeManagerModules.globalSkills = import ./modules/global-skills.nix;
      templates = {
        default = template;
        workspace = template;
      };
    };
}
