{
  description = "GitHub action for committing to PRs";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        pythonEnv = pkgs.python3.withPackages (
          ps: with ps; [
            requests
          ]
        );
      in
      {
        devShells.default = pkgs.mkShell {
          buildInputs = [
            pkgs.pyright
            pythonEnv
            pkgs.ruff
            pkgs.nixfmt-rfc-style
          ];
        };
        checks = {
          ruff-lint =
            pkgs.runCommand "ruff-lint"
              {
                buildInputs = [ pkgs.ruff ];
              }
              ''
                cd ${self}
                ruff check --no-cache .
                touch $out
              '';

          ruff-format =
            pkgs.runCommand "ruff-format"
              {
                buildInputs = [ pkgs.ruff ];
              }
              ''
                cd ${self}
                ruff format --check --no-cache .
                touch $out
              '';

          pyright =
            pkgs.runCommand "pyright"
              {
                buildInputs = [
                  pkgs.pyright
                  pythonEnv
                ];
              }
              ''
                cd ${self}
                pyright .
                touch $out
              '';
        };
      }
    );
}
