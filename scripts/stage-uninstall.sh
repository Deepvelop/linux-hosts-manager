#!/usr/bin/env bash
# Remove Hosts Manager files installed by stage-install.sh.
# Usage: stage-uninstall.sh <destdir> <prefix>
# Direct:  stage-uninstall.sh "" /usr/local
# Staged:  stage-uninstall.sh /tmp/hm-test /usr/local
set -euo pipefail

DESTDIR="${1-}"
PREFIX="${2-}"
APP_ID="com.deepvelop.HostsManager"
BASE="${DESTDIR}${PREFIX}"

remove_file() {
  local path="$1"
  if [[ -f "$path" || -L "$path" ]]; then
    rm -f "$path"
    echo "Removed $path"
  fi
}

prune_empty_dir() {
  local dir="$1"
  while [[ "$dir" == "$BASE"* && -d "$dir" ]]; do
    rmdir "$dir" 2>/dev/null || break
    dir="$(dirname "$dir")"
  done
}

echo "Removing Hosts Manager from $BASE"

remove_file "$BASE/bin/hosts-manager"
remove_file "$BASE/libexec/hosts-manager-helper"
remove_file "$BASE/share/polkit-1/actions/${APP_ID}.policy"
remove_file "$BASE/share/applications/${APP_ID}.desktop"
remove_file "$BASE/share/metainfo/${APP_ID}.metainfo.xml"
remove_file "$BASE/share/icons/hicolor/scalable/apps/${APP_ID}.svg"

for size in 16 24 32 48 64 128 256; do
  remove_file "$BASE/share/icons/hicolor/${size}x${size}/apps/${APP_ID}.png"
  prune_empty_dir "$BASE/share/icons/hicolor/${size}x${size}/apps"
  prune_empty_dir "$BASE/share/icons/hicolor/${size}x${size}"
done

prune_empty_dir "$BASE/share/icons/hicolor/scalable/apps"
prune_empty_dir "$BASE/share/icons/hicolor/scalable"

if [[ -d "$BASE/share/hosts-manager" ]]; then
  rm -rf "$BASE/share/hosts-manager"
  echo "Removed $BASE/share/hosts-manager"
fi

prune_empty_dir "$BASE/share/polkit-1/actions"
prune_empty_dir "$BASE/share/applications"
prune_empty_dir "$BASE/share/metainfo"

echo "Removed Hosts Manager under $BASE"
