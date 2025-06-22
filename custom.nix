{ config, pkgs, lib, ... }:
let
  username = "admin";
  sip-watcher = pkgs.callPackage ./sip-watcher { };
in
{
  networking.hostName = "sip-router";

  environment.systemPackages = [ sip-watcher pkgs.tshark pkgs.wireshark-cli ];

  users.users.${username} = {
    name = username;
    home = "/home/${username}";
    isNormalUser = true;
    extraGroups = [ "wheel" "network" ]; # Enable ‘sudo’ for the user.
    shell = pkgs.zsh;
    openssh.authorizedKeys.keys = [ "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFFeU4GXH+Ae00DipGGJN7uSqPJxWFmgRo9B+xjV3mK4" ];
    initialHashedPassword = "$y$j9T$aeZHaSe8QKeC0ruAi9TKo.$zooI/IZUwOupVDbMReaukiargPrF93H/wdR/.0zsrr.";
  };

  security.sudo.wheelNeedsPassword = false;

  systemd.services.sip-watcher = {
    description = "SIP watcher via pyshark";
    after = [ "network-online.target" ];
    wants = [ "network-online.target" ];

    serviceConfig = {
      ExecStart = "${lib.getExe sip-watcher}";
      Restart = "on-failure";
      User = "root"; # lub utwórz dedykowanego użytkownika
      Environment = "PYTHONUNBUFFERED=1";
      CapabilityBoundingSet = "CAP_NET_RAW CAP_NET_ADMIN";
      AmbientCapabilities = "CAP_NET_RAW CAP_NET_ADMIN";
    };

    wantedBy = [ "multi-user.target" ];
  };

  services.tailscale.enable = true;
}
