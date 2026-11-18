#!/usr/bin/env bash
# TorreUp — odinstalowanie wpisów użytkownika (pliki programu pozostają)
set -euo pipefail

APPDATA="${XDG_DATA_HOME:-$HOME/.local/share}"
BIN="$HOME/.local/bin"
SYSTEMD="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

if [ -f "$SYSTEMD/torreup.service" ]; then
  systemctl --user stop torreup 2>/dev/null || true
  systemctl --user disable torreup 2>/dev/null || true
  rm -f "$SYSTEMD/torreup.service"
  systemctl --user daemon-reload 2>/dev/null || true
  echo "  ✓ usługa systemd usunięta"
fi

rm -f "$APPDATA/applications/torreup.desktop" "$APPDATA/icons/torreup.svg" "$BIN/torreup"
echo "  ✓ wpisy menu i polecenie usunięte"
echo "  Katalog programu nie został usunięty: usuń go ręcznie, jeśli chcesz."
