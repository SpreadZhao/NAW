{
  description = "Configurable agent skill installation and Nix workspaces";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  outputs =
    { nixpkgs, ... }:
    let
      agentLib = import ./lib { inherit nixpkgs; };
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      eachSystem = nixpkgs.lib.genAttrs systems;
      template = {
        path = ./templates/workspace;
        description = "Agent workspace without a built-in skill catalog";
      };
    in
    {
      lib = agentLib;
      homeManagerModules.default = import ./modules/home-manager.nix agentLib;
      templates = {
        workspace = template;
        default = template;
      };
      formatter = eachSystem (system: nixpkgs.legacyPackages.${system}.nixfmt);
      checks = eachSystem (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
          python = pkgs.python3.withPackages (ps: [ ps.pyyaml ]);
          base = {
            inherit pkgs;
            catalog.one = ./tests/fixtures/one;
            skills = [ "one" ];
          };
          installer = agentLib.mkSkillInstaller base;
          processedSource = pkgs.runCommand "processed-skill-source" { } ''
            mkdir -p "$out/skills"
            cp -R ${./tests/fixtures/one} "$out/skills/one"
          '';
          fails = args: !(builtins.tryEval ((agentLib.mkSkillInstaller (base // args)).drvPath)).success;
          apiValid =
            assert
              installer.drvPath == (agentLib.mkSkillInstaller (
                base
                // {
                  skills = [
                    "one"
                    "one"
                  ];
                }
              )).drvPath;
            assert fails { skills = [ "unknown" ]; };
            assert fails { extraSkills.one = ./tests/fixtures/one; };
            assert fails { onConflict = "replace"; };
            assert fails {
              targets.claude = {
                enable = true;
                path = ".agents/skills";
              };
            };
            assert fails {
              targets.custom = {
                enable = true;
                path = "../outside";
              };
            };
            assert builtins.attrNames (agentLib.discoverSkills { source = ./tests/fixtures; }) == [ "one" ];
            assert
              builtins.attrNames (
                agentLib.discoverSkills {
                  source = {
                    outPath = toString ./tests/fixtures;
                  };
                }
              ) == [ "one" ];
            true;
        in
        {
          api =
            assert apiValid;
            installer.passthru.validation;
          processed-source =
            (agentLib.mkWorkspace {
              systems = [ system ];
              catalog = _: {
                one = {
                  source = processedSource;
                  subdir = "skills/one";
                };
              };
              skills = [ "one" ];
            }).checks.${system}.workspace;
          runtime = pkgs.runCommand "agent-workspace-runtime-check" { } ''
            export PYTHONPATH=${./runtime}
            export PYTHONDONTWRITEBYTECODE=1
            ${python}/bin/python ${./tests/test_install.py}
            mkdir -p "$out"
          '';
        }
      );
      devShells = eachSystem (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
        in
        {
          default = pkgs.mkShell {
            packages = [
              (pkgs.python3.withPackages (ps: [ ps.pyyaml ]))
              pkgs.nixfmt
              pkgs.shellcheck
            ];
          };
        }
      );
    };
}
