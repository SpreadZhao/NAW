{
  description = "Nix-owned agent workspaces with a Bash installer";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  outputs =
    { nixpkgs, ... }:
    let
      template = {
        path = ./templates/workspace;
        description = "Minimal declarative agent workspace";
      };
    in
    {
      lib = import ./lib { inherit nixpkgs; };
      homeManagerModules.default = import ./modules/home-manager.nix;
      templates = {
        default = template;
        workspace = template;
      };
    };
}
