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
          installer = import ./installer.nix {
            inherit
              pkgs
              skills
              targets
              instructions
              ;
            scope = "workspace";
          };
        in
        {
          shell = pkgs.mkShell {
            packages = if builtins.isFunction packages then packages pkgs else packages;
            shellHook = ''
              if ! AGENT_WORKSPACE_ROOT="$(${installer}/bin/agent-workspace-install)"; then
                echo "Workspace preparation failed; resolve conflicts and enter again." >&2
                exit 1
              fi
              export AGENT_WORKSPACE_ROOT
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
