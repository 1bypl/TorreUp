#!/usr/bin/env bash
# TorreUp — instalator użytkownika (Fedora / Debian / Ubuntu)
# Użycie: ./install.sh [--service]
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPDATA="${XDG_DATA_HOME:-$HOME/.local/share}"
BIN="$HOME/.local/bin"
SYSTEMD="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
with_service=0
[ "${1:-}" = "--service" ] && with_service=1

echo "Instalacja TorreUp z: $DIR"

# 1. wpis w menu aplikacji
mkdir -p "$APPDATA/applications" "$APPDATA/icons"
sed -e "s|__EXEC__|${DIR}/start.sh|" \
    -e "s|__ICON__|${DIR}/web/img/ghost.svg|" \
    "$DIR/torreup.desktop" > "$APPDATA/applications/torreup.desktop"
chmod +x "$APPDATA/applications/torreup.desktop"
cp -f "$DIR/web/img/ghost.svg" "$APPDATA/icons/torreup.svg"
echo "  ✓ menu aplikacji:  $APPDATA/applications/torreup.desktop"

# 2. polecenie 'torreup' w katalogu użytkownika
mkdir -p "$BIN"
ln -sfn "$DIR/start.sh" "$BIN/torreup"
chmod +x "$DIR/start.sh" "$DIR/torreup.py"
echo "  ✓ polecenie:       $BIN/torreup"

# 3. opcjonalna usługa systemd (uruchamiana ręcznie: systemctl --user start torreup)
if [ "$with_service" -eq 1 ]; then
  mkdir -p "$SYSTEMD"
  cat > "$SYSTEMD/torreup.service" <<EOF
[Unit]
Description=TorreUp - lokalna przeglądarka torrentów
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${DIR}
ExecStart=${DIR}/start.sh
Environment=TORREUP_NO_BROWSER=1
Restart=on-failure
RestartSec=3
PrivateTmp=true
NoNewPrivileges=true

[Install]
WantedBy=default.target
EOF
  if command -v systemctl >/dev/null 2>&1 && systemctl --user is-system-running >/dev/null 2>&1; then
    systemctl --user daemon-reload 2>/dev/null || true
    echo "  ✓ usługa systemd: $SYSTEMD/torreup.service"
    echo "    start: systemctl --user start torreup"
    echo "    autostart: systemctl --user enable torreup"
  else
    echo "  ✓ plik usługi zapisany: $SYSTEMD/torreup.service"
    echo "    (brak aktywnej sesji systemd --user — uruchom program przez start.sh)"
  fi
fi

# 4. odświeżenie bazy desktop (jeśli narzędzie dostępne)
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APPDATA/applications" 2>/dev/null || true
fi

echo
echo "Gotowe. Uruchom jedną z metod:"
echo "  • menu aplikacji → TorreUp"
echo "  • $BIN/torreup"
echo "  • ręcznie: $DIR/start.sh"
echo
case ":$PATH:" in
  *":$BIN:"*) ;;
  *) echo "Uwaga: $BIN nie jest w PATH. Dodaj do ~/.bashrc lub ~/.profile:"
     echo '  export PATH="$HOME/.local/bin:$PATH"' ;;
esac
