import json
from pathlib import Path

from hosts_manager.settings import AppSettings, SettingsStore, default_settings_path


def test_default_settings_path_uses_xdg(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert default_settings_path() == tmp_path / "hosts-manager" / "settings.json"


def test_load_defaults_when_missing(tmp_path: Path):
    store = SettingsStore(tmp_path / "settings.json")
    settings = store.load()
    assert settings.auto_save is False
    assert not store.path.exists()


def test_round_trip_auto_save(tmp_path: Path):
    path = tmp_path / "hosts-manager" / "settings.json"
    store = SettingsStore(path)
    store.save(AppSettings(auto_save=True))
    loaded = store.load()
    assert loaded.auto_save is True
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data == {"auto_save": True}


def test_corrupt_settings_fall_back_to_defaults(tmp_path: Path):
    path = tmp_path / "settings.json"
    path.write_text("{not-json", encoding="utf-8")
    assert SettingsStore(path).load().auto_save is False
