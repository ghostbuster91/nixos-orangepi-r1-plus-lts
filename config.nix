{ pkgs
, lib
, modulesPath
, ...
}: {
  system.stateVersion = "25.05";
  boot.tmp.useTmpfs = false;
  boot.kernelModules = [ "br_netfilter" "bridge" ];
  boot.kernel.sysctl = {
    "net.ipv4.ip_forward" = 1;
    "net.ipv4.ip_nonlocal_bind" = 1;
    "net.ipv6.conf.all.forwarding" = 1;
    "net.ipv6.ip_nonlocal_bind" = 1;
    "net.bridge.bridge-nf-call-ip6tables" = 1;
    "net.bridge.bridge-nf-call-iptables" = 1;
    "net.bridge.bridge-nf-call-arptables" = 1;
    "fs.inotify.max_user_watches" = 524288;
    "net.ipv4.conf.all.rp_filter" = 0;
    "vm.max_map_count" = 2000000;
    "net.ipv4.conf.all.route_localnet" = 1;
    "net.ipv4.conf.all.send_redirects" = 0;
    "kernel.msgmnb" = 65536;
    "kernel.msgmax" = 65536;
    "net.ipv4.tcp_timestamps" = 0;
    "net.ipv4.tcp_synack_retries" = 1;
    "net.ipv4.tcp_syn_retries" = 1;
    "net.ipv4.tcp_fin_timeout" = 15;
    "net.ipv4.tcp_keepalive_time" = 1800;
    "net.ipv4.tcp_keepalive_probes" = 3;
    "net.ipv4.tcp_keepalive_intvl" = 15;
    "net.ipv4.ip_local_port_range" = "2048 65535";
    "fs.file-max" = 102400;
  };

  nix = {
    package = pkgs.nixVersions.stable;
    settings = {
      experimental-features = [ "nix-command" "flakes" ];
      trusted-users = [ "root" "admin" ];
    };
  };

  documentation.enable = false;
  nixpkgs.config.allowX11 = false;
  nixpkgs.overlays = lib.singleton (lib.const (super: {
    openjdk11 = super.openjdk11.override { headless = true; };
    openjdk17 = super.openjdk17.override { headless = true; };
    qemu_kvm = super.qemu.override {
      hostCpuOnly = true;
      numaSupport = false;
      alsaSupport = false;
      pulseSupport = false;
      pipewireSupport = false;
      sdlSupport = false;
      jackSupport = false;
      gtkSupport = false;
      vncSupport = false;
      smartcardSupport = false;
      spiceSupport = false;
      ncursesSupport = false;
      usbredirSupport = false;
      libiscsiSupport = false;
      tpmSupport = false;
    };
  }));

  users.defaultUserShell = pkgs.zsh;
  users.users.root.initialPassword = "";

  time.timeZone = "Asia/Shanghai";
  i18n = {
    defaultLocale = "en_US.UTF-8";
  };

  services.udisks2.enable = lib.mkForce false;
  environment.systemPackages = with pkgs; [
    lsof
    wget
    curl
    neovim
    jq
    iptables
    ebtables
    tcpdump
    busybox
    ethtool
    socat
    htop
    iftop
    lm_sensors
  ];

  programs.zsh = {
    enable = true;
  };
  programs.command-not-found.enable = false;
  services.openssh.enable = true;
  services.openssh.settings.PermitRootLogin = "no";

  environment = {
    localBinInPath = true;
    homeBinInPath = true;
    variables = {
      EDITOR = "nvim";
      HYPHEN_INSENSITIVE = "true";
    };
    shellAliases = {
      l = "ls -alh";
      ll = "ls -alh";
      vim = "nvim";
    };
  };

  networking = {
    useDHCP = false;
    networkmanager.enable = false;
    firewall.enable = false;
  };
  systemd.network = {
    enable = true;
    networks."lan" = {
      matchConfig.Name = "enu1";
      networkConfig.DHCP = "no";
      linkConfig.RequiredForOnline = "no";
    };
    networks."wan" = {
      matchConfig.Name = "end0";
      networkConfig.DHCP = "yes";
      linkConfig.RequiredForOnline = "yes";
    };
  };
}
