"""One-time host install of polkit helper for sandboxed packages (Flatpak)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from hosts_manager.paths import (
    SYSTEM_HELPER_PATHS,
    is_flatpak,
    packaged_app_root,
    privileged_bundle_dir,
)


def host_helper_installed() -> bool:
    return any(os.path.isfile(path) for path in SYSTEM_HELPER_PATHS)


def ensure_host_privileged_install() -> bool:
    """Install helper + polkit policy to /usr/local on the host when running as Flatpak."""
    if not is_flatpak():
        return True
    if host_helper_installed():
        return True
    bundle = privileged_bundle_dir()
    if bundle is None:
        return False
    root = packaged_app_root()
    if root is None:
        return False
    script = root / "scripts" / "install-privileged-components.sh"
    if not script.is_file():
        return False
    try:
        subprocess.run(
            ["pkexec", str(script), "/usr/local", str(bundle)],
            check=True,
            capture_output=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return False
    return host_helper_installed()
