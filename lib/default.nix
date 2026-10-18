{ nixpkgs }:
{
  mkWorkspace =
    {
      systems ? [
        "x86_64-linux"
        "aarch64-linux"
      ],
      skills ? { },
      targets ? [ "agents" ],
      instructions ? "",
      packages ? (_: [ ]),
      shellHook ? "",
    }:
    let
      perSystem = nixpkgs.lib.genAttrs systems (
        system:
        let
          pkgs = import nixpkgs {
            inherit system;
            config.allowUnfree = true;
          };
          installer = import ./workspace.nix {
            inherit
              pkgs
              skills
              targets
              instructions
              ;
          };
        in
        {
          shell = pkgs.mkShell {
            packages = if builtins.isFunction packages then packages pkgs else packages;
            shellHook = ''
              if ! NAW_WORKSPACE_ROOT="$(${installer}/bin/naw-workspace-activate)"; then
                echo "NAW setup failed; fix the error above and re-enter the shell." >&2
                exit 1
              fi
              export NAW_WORKSPACE_ROOT
            ''
            + shellHook;
          };
          check = installer.passthru.bundle;
        }
      );
    in
    {
      devShells = nixpkgs.lib.mapAttrs (_: value: { default = value.shell; }) perSystem;
      checks = nixpkgs.lib.mapAttrs (_: value: { workspace = value.check; }) perSystem;
    };
}
