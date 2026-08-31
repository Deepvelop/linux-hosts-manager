#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="${PREFIX:-/usr/local}"
DESTDIR="${DESTDIR:-}"
APP_ID="com.deepvelop.HostsManager"

if [[ "${EUID:-$(id -u)}" -ne 0 && -z "$DESTDIR" ]]; then
  echo "Installing to $PREFIX requires root. Re-run with sudo or set DESTDIR for a staged install." >&2
  exit 1
fi

BASE="$DESTDIR$PREFIX"

echo "Installing Hosts Manager to $BASE"

chmod +x "$ROOT/scripts/"*.sh "$ROOT/scripts/hosts-manager-launch"
"$ROOT/scripts/stage-install.sh" "$DESTDIR" "$PREFIX" "$ROOT"

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$BASE/share/applications" || true
fi

if command -v gtk4-update-icon-cache >/dev/null 2>&1; then
  gtk4-update-icon-cache -f -t "$BASE/share/icons/hicolor" || true
fi

if command -v ulauncher >/dev/null 2>&1; then
  ulauncher --restart >/dev/null 2>&1 || true
fi

echo "Installed."
echo "  GUI:      $BASE/bin/hosts-manager"
echo "  Helper:   $BASE/libexec/hosts-manager-helper"
echo "  Policy:   $BASE/share/polkit-1/actions/${APP_ID}.policy"
echo "  Desktop:  $BASE/share/applications/${APP_ID}.desktop"
