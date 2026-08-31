from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


def default_settings_path() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "hosts-manager" / "settings.json"


@dataclass
class AppSettings:
    auto_save: bool = False


class SettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_settings_path()

    def load(self) -> AppSettings:
        if not self.path.exists():
            return AppSettings()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return AppSettings()
        if not isinstance(data, dict):
            return AppSettings()
        return AppSettings(auto_save=bool(data.get("auto_save", False)))

    def save(self, settings: AppSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"auto_save": bool(settings.auto_save)}
        self.path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
