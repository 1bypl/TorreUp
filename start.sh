#!/usr/bin/env bash
# TorreUp — launcher dla Fedora / Debian / Ubuntu
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${TORREUP_PYTHON:-python3}"
HOST="${TORREUP_HOST:-127.0.0.1}"
PORT="${TORREUP_PORT:-7788}"

if ! command -v "$PY" >/dev/null 2>&1; then
  echo "Błąd: nie znaleziono Pythona 3 ($PY)."
  echo "  Fedora:   sudo dnf install python3"
  echo "  Debian:   sudo apt install python3"
  echo "  Ubuntu:   sudo apt install python3"
  exit 1
fi

if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)'; then
  echo "Błąd: TorreUp wymaga Pythona 3.8 lub nowszego."
  exit 1
fi

echo "  TorreUp — http://${HOST}:${PORT}"
echo "  Zatrzymaj: Ctrl+C"

# Otwórz przeglądarkę (jeśli dostępna i nie wyłączono)
if [ "${TORREUP_NO_BROWSER:-0}" != "1" ] && command -v xdg-open >/dev/null 2>&1; then
  ( sleep 1; xdg-open "http://${HOST}:${PORT}" >/dev/null 2>&1 || true ) &
fi

exec "$PY" "$DIR/torreup.py"
