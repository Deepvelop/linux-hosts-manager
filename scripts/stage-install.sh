#!/usr/bin/env bash
# Install Hosts Manager into a staging directory (Snap, Flatpak, or DESTDIR installs).
# Usage: stage-install.sh <destdir> <prefix> <source-root>
# Direct:  stage-install.sh "" /usr/local /path/to/repo
# Snap:    stage-install.sh "$SNAPCRAFT_PART_INSTALL" /usr "$SNAPCRAFT_PROJECT_DIR"
# Flatpak: stage-install.sh /app "" "$PWD"
set -euo pipefail

DESTDIR="${1-}"
PREFIX="${2-}"
SRC="${3:?source root required}"
APP_ID="com.deepvelop.HostsManager"
BASE="${DESTDIR}${PREFIX}"

install_file() {
  local mode="$1"
  local dest="$2"
  local source="$3"
  mkdir -p "$(dirname "$dest")"
  install -m "$mode" "$source" "$dest"
}

echo "Staging Hosts Manager to $BASE"

install_file 0644 "$BASE/share/hosts-manager/app.py" "$SRC/app.py"
for module in __init__ models parser validate profiles settings merge diff writer polkit profile_icons window paths bootstrap; do
  install_file 0644 "$BASE/share/hosts-manager/hosts_manager/${module}.py" "$SRC/hosts_manager/${module}.py"
done
install_file 0644 "$BASE/share/hosts-manager/hosts_manager/style.css" "$SRC/hosts_manager/style.css"

install_file 0755 "$BASE/libexec/hosts-manager-helper" "$SRC/helper/hosts-manager-helper.py"
install_file 0755 "$BASE/bin/hosts-manager" "$SRC/scripts/hosts-manager-launch"
install_file 0755 "$BASE/share/hosts-manager/scripts/install-privileged-components.sh" "$SRC/scripts/install-privileged-components.sh"

mkdir -p "$BASE/share/hosts-manager/privileged"
install_file 0755 "$BASE/share/hosts-manager/privileged/hosts-manager-helper.py" "$SRC/helper/hosts-manager-helper.py"
install_file 0644 "$BASE/share/hosts-manager/privileged/com.deepvelop.HostsManager.policy.in" "$SRC/data/com.deepvelop.HostsManager.policy.in"

mkdir -p "$BASE/share/polkit-1/actions"
sed "s|@HELPER_PATH@|$BASE/libexec/hosts-manager-helper|g" \
  "$SRC/data/com.deepvelop.HostsManager.policy.in" \
  >"$BASE/share/polkit-1/actions/${APP_ID}.policy"
chmod 644 "$BASE/share/polkit-1/actions/${APP_ID}.policy"

mkdir -p "$BASE/share/applications"
sed "s|@BINDIR@|$BASE/bin|g" \
  "$SRC/data/com.deepvelop.HostsManager.desktop.in" \
  >"$BASE/share/applications/${APP_ID}.desktop"
chmod 644 "$BASE/share/applications/${APP_ID}.desktop"
install_file 0644 "$BASE/share/metainfo/${APP_ID}.metainfo.xml" "$SRC/data/${APP_ID}.metainfo.xml"
install_file 0644 "$BASE/share/icons/hicolor/scalable/apps/${APP_ID}.svg" "$SRC/icons/${APP_ID}.svg"

for size in 16 24 32 48 64 128 256; do
  icon="$SRC/icons/hicolor/${size}x${size}/apps/${APP_ID}.png"
  if [[ -f "$icon" ]]; then
    install_file 0644 "$BASE/share/icons/hicolor/${size}x${size}/apps/${APP_ID}.png" "$icon"
  fi
done

echo "Staged Hosts Manager under $BASE"
