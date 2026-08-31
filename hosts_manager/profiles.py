from __future__ import annotations

import json
import os
from pathlib import Path

from hosts_manager.models import HostEntry, Profile


def default_config_path() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "hosts-manager" / "profiles.json"


def default_profiles() -> list[Profile]:
    return [
        Profile(id="development", name="Development", icon="code", enabled=True),
        Profile(id="staging", name="Staging", icon="stack", enabled=False),
        Profile(id="production", name="Production", icon="globe", enabled=False),
    ]


class ProfileStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_config_path()

    def load(self) -> list[Profile]:
        if not self.path.exists():
            return default_profiles()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return [_profile_from_dict(item) for item in data.get("profiles", [])]

    def save(self, profiles: list[Profile]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"profiles": [_profile_to_dict(profile) for profile in profiles]}
        self.path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _profile_to_dict(profile: Profile) -> dict:
    return {
        "id": profile.id,
        "name": profile.name,
        "icon": profile.icon,
        "enabled": profile.enabled,
        "entries": [
            {
                "ip": entry.ip,
                "hostname": entry.hostname,
                "enabled": entry.enabled,
                "comment": entry.comment,
            }
            for entry in profile.entries
        ],
    }


def _profile_from_dict(data: dict) -> Profile:
    return Profile(
        id=data["id"],
        name=data["name"],
        icon=data.get("icon", "default"),
        enabled=bool(data.get("enabled", False)),
        entries=[
            HostEntry(
                ip=item["ip"],
                hostname=item["hostname"],
                enabled=bool(item.get("enabled", True)),
                comment=item.get("comment", ""),
            )
            for item in data.get("entries", [])
        ],
    )
