{ pkgs }:
pkgs.python3Packages.buildPythonApplication {
  pname = "sip-watcher";
  version = "1.0.0";

  src = ./.;

  # Plik z twoim skryptem
  entryPoints = [ "sip_watcher=sip_watcher:main" ];

  propagatedBuildInputs = with pkgs.python3Packages; [
    paho-mqtt pyshark
  ];

  # Potrzebny do działania skryptu
  nativeBuildInputs = [
    pkgs.tshark
  ];

  # Skopiuj skrypt bez setuptools – nie potrzebujemy setup.py
  installPhase = ''
    mkdir -p $out/bin
    cp sip_watcher.py $out/bin/sip-watcher
    chmod +x $out/bin/sip-watcher
  '';

  meta = with pkgs.lib; {
    description = "SIP watcher that sends MQTT events based on call state";
    license = licenses.mit;
    maintainers = [ ];
    platforms = platforms.linux;
  };
}

