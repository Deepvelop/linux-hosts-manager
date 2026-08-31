#!/usr/bin/env bash
# Install the privileged helper and polkit policy to the host system.
# Usage: install-privileged-components.sh <prefix> <bundle-dir>
# Example: install-privileged-components.sh /usr/local /app/share/hosts-manager/privileged
set -euo pipefail

PREFIX="${1:?prefix required (e.g. /usr/local)}"
BUNDLE="${2:?bundle directory required}"

HELPER="$PREFIX/libexec/hosts-manager-helper"
POLICY="$PREFIX/share/polkit-1/actions/com.deepvelop.HostsManager.policy"
POLICY_IN="$BUNDLE/com.deepvelop.HostsManager.policy.in"

if [[ ! -f "$BUNDLE/hosts-manager-helper.py" ]]; then
  echo "Missing helper in $BUNDLE" >&2
  exit 1
fi
if [[ ! -f "$POLICY_IN" ]]; then
  echo "Missing policy template in $BUNDLE" >&2
  exit 1
fi

mkdir -p "$(dirname "$HELPER")" "$(dirname "$POLICY")"
install -m 755 "$BUNDLE/hosts-manager-helper.py" "$HELPER"
sed "s|@HELPER_PATH@|$HELPER|g" "$POLICY_IN" >"$POLICY"
chmod 644 "$POLICY"

echo "Installed privileged helper to $HELPER"
echo "Installed polkit policy to $POLICY"
