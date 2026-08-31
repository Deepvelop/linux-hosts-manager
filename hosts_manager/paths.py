"""Install layout detection for source, system, Snap, and Flatpak builds."""

from __future__ import annotations

import os
from pathlib import Path

APP_ID = "com.deepvelop.HostsManager"

SYSTEM_HELPER_PATHS = (
    "/usr/local/libexec/hosts-manager-helper",
    "/usr/libexec/hosts-manager-helper",
)

SYSTEM_APP_ROOTS = (
    Path("/usr/local/share/hosts-manager"),
    Path("/usr/share/hosts-manager"),
)


def is_flatpak() -> bool:
    return bool(os.environ.get("FLATPAK_ID"))


def is_snap() -> bool:
    return bool(os.environ.get("SNAP"))


def packaged_app_root() -> Path | None:
    if snap := os.environ.get("SNAP"):
        candidate = Path(snap) / "usr" / "share" / "hosts-manager"
        if (candidate / "app.py").is_file():
            return candidate
    if is_flatpak():
        candidate = Path("/app/share/hosts-manager")
        if (candidate / "app.py").is_file():
            return candidate
    for candidate in SYSTEM_APP_ROOTS:
        if (candidate / "app.py").is_file():
            return candidate
    source = Path(__file__).resolve().parent.parent
    if (source / "app.py").is_file():
        return source
    return None


def packaged_helper_path() -> Path | None:
    if snap := os.environ.get("SNAP"):
        candidate = Path(snap) / "usr" / "libexec" / "hosts-manager-helper"
        if candidate.is_file():
            return candidate
    if is_flatpak():
        candidate = Path("/app/libexec/hosts-manager-helper")
        if candidate.is_file():
            return candidate
    for path in SYSTEM_HELPER_PATHS:
        if os.path.isfile(path):
            return Path(path)
    repo_helper = Path(__file__).resolve().parents[1] / "helper" / "hosts-manager-helper.py"
    if repo_helper.is_file():
        return repo_helper
    return None


def privileged_bundle_dir() -> Path | None:
    root = packaged_app_root()
    if root is None:
        return None
    candidate = root / "privileged"
    if candidate.is_dir():
        return candidate
    return None
