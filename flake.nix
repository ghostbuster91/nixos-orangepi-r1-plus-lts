{
  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-25.05";
    flake-utils.url = "github:numtide/flake-utils";
    deploy-rs.url = "github:serokell/deploy-rs";
  };

  outputs =
    { self
    , flake-utils
    , nixpkgs
    , deploy-rs
    ,
    }:
    let
      orangepi-r1-plus-lts-config = nixpkgs.lib.nixosSystem {
        modules = [
          ./custom.nix
          ./config.nix
          ./sd-image-aarch64-orangepi-r1plus.nix
          ./sd-image.nix
        ];
        system = "aarch64-linux";
      };
    in
    (flake-utils.lib.eachDefaultSystem (system:
    let
      pkgs = import nixpkgs { inherit system; };
    in
    {
      packages.default = orangepi-r1-plus-lts-config.config.system.build.sdImage;
      formatter = pkgs.nixpkgs-fmt;
      devShells.default = pkgs.mkShell {
        packages = [ pkgs.nixos-rebuild pkgs.deploy-rs pkgs.cloudflared ];
      };
    }))
    // {
      deploy.nodes.orangepi-r1-plus-lts-config = {
        hostname = "sip-router-2";
        profiles.system = {
          sshUser = "admin";
          user = "root";
          remoteBuild = false;
          sshOpts = [ "-oControlMaster=no" ];
          path = deploy-rs.lib.aarch64-linux.activate.nixos self.nixosConfigurations.orangepi-r1-plus-lts-config;
        };
      };

      # This is highly advised, and will prevent many possible mistakes
      checks = builtins.mapAttrs (system: deployLib: deployLib.deployChecks self.deploy) deploy-rs.lib;

      nixosConfigurations.orangepi-r1-plus-lts-config = orangepi-r1-plus-lts-config;
    };
}
