{
  description = "Manage agent skills and project workspaces with Nix and Home Manager";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  outputs =
    { nixpkgs, ... }:
    let
      template = {
        path = ./templates/workspace;
        description = "Project shell with agent skills and instructions";
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
