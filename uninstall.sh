#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="${PREFIX:-/usr/local}"
DESTDIR="${DESTDIR:-}"
APP_ID="com.deepvelop.HostsManager"
PURGE_USER_DATA=0

usage() {
  cat <<EOF
Usage: sudo ./uninstall.sh [options]

Remove Hosts Manager from \$PREFIX (default: /usr/local).

Options:
  --purge-user-data   Also remove ~/.config/hosts-manager (profiles and settings)
  -h, --help          Show this help

Environment:
  PREFIX=/usr/local   Install prefix used during installation
  DESTDIR=            Staging root for non-system uninstalls
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --purge-user-data)
      PURGE_USER_DATA=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ "${EUID:-$(id -u)}" -ne 0 && -z "$DESTDIR" ]]; then
  echo "Removing from $PREFIX requires root. Re-run with sudo or set DESTDIR for a staged uninstall." >&2
  exit 1
fi

BASE="$DESTDIR$PREFIX"

echo "Uninstalling Hosts Manager from $BASE"

chmod +x "$ROOT/scripts/stage-uninstall.sh"
"$ROOT/scripts/stage-uninstall.sh" "$DESTDIR" "$PREFIX"

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$BASE/share/applications" || true
fi

if command -v gtk4-update-icon-cache >/dev/null 2>&1 && [[ -d "$BASE/share/icons/hicolor" ]]; then
  gtk4-update-icon-cache -f -t "$BASE/share/icons/hicolor" || true
fi

if command -v ulauncher >/dev/null 2>&1; then
  ulauncher --restart >/dev/null 2>&1 || true
fi

if [[ "$PURGE_USER_DATA" -eq 1 ]]; then
  user_home="${SUDO_USER:+$(getent passwd "$SUDO_USER" | cut -d: -f6)}"
  user_home="${user_home:-$HOME}"
  config_dir="$user_home/.config/hosts-manager"
  if [[ -d "$config_dir" ]]; then
    if [[ -n "${SUDO_USER:-}" ]]; then
      sudo -u "$SUDO_USER" rm -rf "$config_dir"
    else
      rm -rf "$config_dir"
    fi
    echo "Removed user data: $config_dir"
  fi
fi

echo "Uninstalled."
if [[ "$PURGE_USER_DATA" -eq 0 ]]; then
  echo "User settings and profiles remain in ~/.config/hosts-manager"
  echo "Re-run with --purge-user-data to remove them."
fi
