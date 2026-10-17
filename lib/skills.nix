{ pkgs, skills }:
pkgs.runCommand "naw-skills" { } (
  ''
    mkdir -p "$out"
  ''
  + pkgs.lib.concatStrings (
    pkgs.lib.mapAttrsToList (name: source: ''
      cp -RL -- ${pkgs.lib.escapeShellArg "${source}"} "$out/"${pkgs.lib.escapeShellArg name}
    '') skills
  )
)
