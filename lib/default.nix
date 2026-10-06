{ nixpkgs }:
let
  inherit (nixpkgs) lib;
  safeName =
    name:
    builtins.isString name
    && builtins.stringLength name <= 64
    && builtins.match "[a-z0-9]+(-[a-z0-9]+)*" name != null;
  safeRelative =
    value:
    builtins.isString value
    && value != ""
    && !(lib.hasPrefix "/" value)
    && lib.all (
      part:
      !(builtins.elem part [
        ""
        "."
        ".."
      ])
    ) (lib.splitString "/" value);
  pythonFor = pkgs: pkgs.python3.withPackages (ps: [ ps.pyyaml ]);
  presets = {
    agents = {
      enable = true;
      path = ".agents/skills";
    };
    claude = {
      enable = false;
      path = ".claude/skills";
    };
    codex = {
      enable = false;
      path = ".codex/skills";
    };
  };
  normalize =
    {
      catalog,
      skills,
      extraSkills,
      targets,
      claude,
    }:
    let
      collisions = lib.intersectLists (builtins.attrNames catalog) (builtins.attrNames extraSkills);
      merged = catalog // extraSkills;
      selected = lib.unique (skills ++ builtins.attrNames extraSkills);
      unknown = lib.subtractLists (builtins.attrNames merged) selected;
      targetConfigs =
        lib.mapAttrs
          (_: t: {
            enable = t.enable or true;
            inherit (t) path;
          })
          (
            lib.recursiveUpdate (
              presets
              // {
                claude = presets.claude // {
                  enable = claude;
                };
              }
            ) targets
          );
      records = map (
        name:
        let
          value = merged.${name};
          record =
            if lib.isDerivation value || builtins.isPath value || builtins.isString value then
              { source = value; }
            else
              value;
          subdir = record.subdir or ".";
          skillTargets = record.targets or (builtins.attrNames targetConfigs);
        in
        assert lib.assertMsg (safeName name) "agent-workspace: invalid skill name ${name}";
        assert lib.assertMsg (
          subdir == "." || safeRelative subdir
        ) "agent-workspace: invalid subdir for ${name}";
        assert lib.assertMsg (
          builtins.isList skillTargets
          && lib.all (target: builtins.isString target && builtins.hasAttr target targetConfigs) skillTargets
        ) "agent-workspace: unknown target for ${name}";
        {
          inherit name;
          source = "${record.source}" + lib.optionalString (subdir != ".") "/${subdir}";
          targets = lib.unique skillTargets;
        }
      ) selected;
      destinations = lib.concatMap (
        record:
        map (target: "${targetConfigs.${target}.path}/${record.name}") (
          lib.filter (target: targetConfigs.${target}.enable) record.targets
        )
      ) records;
    in
    assert lib.assertMsg (
      collisions == [ ]
    ) "agent-workspace: duplicate catalog/extraSkills names: ${lib.concatStringsSep ", " collisions}";
    assert lib.assertMsg (
      unknown == [ ]
    ) "agent-workspace: unknown skills: ${lib.concatStringsSep ", " unknown}";
    assert lib.assertMsg (lib.all (t: builtins.isBool t.enable && safeRelative t.path) (
      builtins.attrValues targetConfigs
    )) "agent-workspace: target paths must be safe relative paths";
    assert lib.assertMsg (
      builtins.length destinations == builtins.length (lib.unique destinations)
    ) "agent-workspace: target collisions";
    assert lib.assertMsg (lib.all (
      a: !(lib.any (b: a != b && lib.hasPrefix "${b}/" a) destinations)
    ) destinations) "agent-workspace: overlapping destinations";
    {
      skills = records;
      targets = targetConfigs;
    };

  mkSkillInstaller =
    {
      pkgs,
      catalog ? { },
      skills ? [ ],
      extraSkills ? { },
      targets ? { },
      mode ? "symlink",
      scope ? "global",
      onConflict ? (if scope == "workspace" then "error" else "skip"),
      cleanup ? (scope == "workspace"),
      claude ? false,
      instructions ? "",
      manageInstructions ? (scope == "workspace"),
      manageGitignore ? (scope == "workspace"),
      root ? null,
    }:
    let
      resolvedCatalog = if builtins.isFunction catalog then catalog pkgs else catalog;
      selected = normalize {
        catalog = resolvedCatalog;
        inherit
          skills
          extraSkills
          targets
          claude
          ;
      };
      python = pythonFor pkgs;
      bundle = pkgs.runCommand "agent-workspace-skills" { } (
        ''
          mkdir -p "$out/skills"
          export PYTHONPATH=${../runtime}
        ''
        + lib.concatMapStringsSep "\n" (entry: ''
          ${python}/bin/python -c 'from pathlib import Path; from install import check_skill; import sys; check_skill(Path(sys.argv[1]), sys.argv[2])' \
            ${lib.escapeShellArg entry.source} ${lib.escapeShellArg entry.name}
          ln -s ${lib.escapeShellArg entry.source} "$out/skills/${entry.name}"
        '') selected.skills
      );
      manifest = pkgs.writeText "agent-workspace-manifest.json" (
        builtins.toJSON (
          selected
          // {
            schemaVersion = 3;
            inherit
              scope
              onConflict
              cleanup
              mode
              claude
              instructions
              manageInstructions
              manageGitignore
              root
              ;
            bundle = toString bundle;
          }
        )
      );
      program = pkgs.writeShellApplication {
        name = "agent-workspace-install";
        runtimeInputs = [ pkgs.nix ];
        text = ''exec ${python}/bin/python ${../runtime/install.py} ${manifest} "$@"'';
      };
      validation = pkgs.runCommand "agent-workspace-selection-check" { } ''
        ${python}/bin/python ${../runtime/install.py} ${manifest} --validate
        mkdir -p "$out"
      '';
    in
    assert lib.assertMsg (builtins.elem scope [
      "workspace"
      "global"
    ]) "agent-workspace: invalid scope";
    assert lib.assertMsg (builtins.elem mode [
      "symlink"
      "copy"
    ]) "agent-workspace: invalid mode";
    assert lib.assertMsg (builtins.elem onConflict [
      "error"
      "skip"
    ]) "agent-workspace: invalid onConflict";
    assert lib.assertMsg (
      builtins.isBool cleanup
      && builtins.isBool claude
      && builtins.isBool manageInstructions
      && builtins.isBool manageGitignore
    ) "agent-workspace: flags must be booleans";
    assert lib.assertMsg (
      root == null || (builtins.isString root && lib.hasPrefix "/" root)
    ) "agent-workspace: root must be an absolute string";
    builtins.deepSeq selected (program // { passthru = { inherit bundle manifest validation; }; });

  mkWorkspace =
    {
      systems ? [
        "x86_64-linux"
        "aarch64-linux"
      ],
      catalog ? { },
      skills ? [ ],
      extraSkills ? { },
      targets ? { },
      mode ? "symlink",
      onConflict ? "error",
      cleanup ? true,
      packages ? (_: [ ]),
      claude ? false,
      instructions ? "",
      manageInstructions ? true,
      manageGitignore ? true,
      workspaceRoot ? null,
      autoActivate ? true,
      shellHook ? "",
    }:
    let
      perSystem = lib.genAttrs systems (
        system:
        let
          pkgs = import nixpkgs {
            inherit system;
            config.allowUnfree = true;
          };
          installer = mkSkillInstaller {
            inherit
              pkgs
              catalog
              skills
              extraSkills
              targets
              mode
              onConflict
              cleanup
              claude
              instructions
              manageInstructions
              manageGitignore
              ;
            scope = "workspace";
            root = workspaceRoot;
          };
        in
        {
          shell = pkgs.mkShell {
            packages = if builtins.isFunction packages then packages pkgs else packages;
            shellHook =
              lib.optionalString autoActivate ''
                if ! agent_workspace_root="$(${installer}/bin/agent-workspace-install)"; then
                  echo "Workspace preparation failed; resolve conflicts and enter again." >&2
                  exit 1
                fi
                export AGENT_WORKSPACE_ROOT="$agent_workspace_root"
                unset agent_workspace_root
              ''
              + shellHook;
          };
          check = installer.passthru.validation;
        }
      );
    in
    {
      devShells = lib.mapAttrs (_: value: { default = value.shell; }) perSystem;
      checks = lib.mapAttrs (_: value: { workspace = value.check; }) perSystem;
    };

  discoverSkills =
    {
      source,
      subdir ? ".",
      maxDepth ? 100,
    }:
    let
      root = "${source}" + lib.optionalString (subdir != ".") "/${subdir}";
      walk =
        directory: depth:
        if builtins.pathExists (directory + "/SKILL.md") then
          let
            lines = lib.splitString "\n" (
              lib.replaceStrings [ "\r" ] [ "" ] (builtins.readFile (directory + "/SKILL.md"))
            );
            readHeader =
              remaining:
              if remaining == [ ] then
                throw "agent-workspace: unterminated frontmatter in ${directory}"
              else if builtins.head remaining == "---" then
                [ ]
              else
                [ (builtins.head remaining) ] ++ readHeader (builtins.tail remaining);
            header = readHeader (builtins.tail lines);
            names = lib.filter (value: value != null) (
              map (line: builtins.match "name:[[:space:]]*['\"]?([a-z0-9-]+)['\"]?[[:space:]]*" line) header
            );
          in
          assert lib.assertMsg (
            builtins.head lines == "---" && builtins.length names == 1
          ) "agent-workspace: cannot discover name in ${toString directory}";
          [
            {
              name = builtins.head (builtins.head names);
              value = {
                source = directory;
              };
            }
          ]
        else if depth >= maxDepth then
          [ ]
        else
          let
            entries = builtins.readDir directory;
          in
          lib.concatMap (
            name: if entries.${name} == "directory" then walk (directory + "/${name}") (depth + 1) else [ ]
          ) (builtins.attrNames entries);
      entries = walk root 0;
    in
    assert lib.assertMsg (
      subdir == "." || safeRelative subdir
    ) "agent-workspace: unsafe discovery subdir";
    assert lib.assertMsg (
      builtins.isInt maxDepth && maxDepth >= 0 && maxDepth <= 100
    ) "agent-workspace: maxDepth must be 0..100";
    assert lib.assertMsg (
      builtins.length entries == builtins.length (lib.unique (map (entry: entry.name) entries))
    ) "agent-workspace: duplicate discovered skill names";
    builtins.listToAttrs entries;
in
{
  inherit mkSkillInstaller mkWorkspace discoverSkills;
}
