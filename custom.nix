{ pkgs, ... }:
let
  username = "admin";
in
{

  users.users.${username} = {
    name = username;
    home = "/home/${username}";
    isNormalUser = true;
    extraGroups = [ "wheel" "network" ]; # Enable ‘sudo’ for the user.
    shell = pkgs.zsh;
    openssh.authorizedKeys.keys = [ "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFFeU4GXH+Ae00DipGGJN7uSqPJxWFmgRo9B+xjV3mK4" ];
    initialHashedPassword = "$y$j9T$aeZHaSe8QKeC0ruAi9TKo.$zooI/IZUwOupVDbMReaukiargPrF93H/wdR/.0zsrr.";
  };
}
