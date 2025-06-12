{ pkgs, ... }:
let
  kamailioPkg = pkgs.kamailio.overrideAttrs (old: {
    modules = [
      "sl"
      "tm"
      "rr"
      "xlog"
      "exec"
      "maxfwd"
      "pv" # ← potrzebny dla $avp i siputils
      "textops" # ← używany w has_totag
      "siputils" # ← rpid i inne operacje SIP
    ];
  });
in
{
  environment.etc."kamailio/kamailio.cfg".source = ./kamailio.cfg;

  users.users.kamailio = {
    isSystemUser = true;
    group = "kamailio";
  };
  users.groups.kamailio = { };

  systemd.services.kamailio = {
    description = "Kamailio SIP Proxy";
    wantedBy = [ "multi-user.target" ];
    after = [ "network.target" ];
    requires = [ "network.target" ];

    serviceConfig = {
      Type = "simple";
      ExecStart = "${kamailioPkg}/bin/kamailio -DD -f /etc/kamailio/kamailio.cfg";
      Restart = "on-failure";
      User = "kamailio";
      Group = "kamailio";
      AmbientCapabilities = [ "CAP_NET_BIND_SERVICE" ];
    };
  };
  systemd.tmpfiles.rules = [
    "d /var/run/kamailio 0750 kamailio kamailio -"
  ];
}
