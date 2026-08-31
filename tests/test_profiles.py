import json
from pathlib import Path

from hosts_manager.models import HostEntry, Profile
from hosts_manager.profiles import ProfileStore, default_profiles


def test_default_profiles_match_mockup():
    profiles = default_profiles()
    assert [p.name for p in profiles] == ["Development", "Staging", "Production"]
    assert [p.icon for p in profiles] == ["code", "stack", "globe"]
    assert [p.enabled for p in profiles] == [True, False, False]
    assert all(p.entries == [] for p in profiles)


def test_round_trip_json(tmp_path: Path):
    path = tmp_path / "profiles.json"
    store = ProfileStore(path)
    original = default_profiles()
    original[0].entries.append(
        HostEntry(ip="127.0.0.1", hostname="app.local", comment="Local application")
    )
    store.save(original)
    loaded = store.load()
    assert loaded[0].name == "Development"
    assert loaded[0].entries[0].hostname == "app.local"
    assert loaded[0].entries[0].comment == "Local application"


def test_load_seeds_defaults_when_missing(tmp_path: Path):
    path = tmp_path / "missing" / "profiles.json"
    loaded = ProfileStore(path).load()
    assert [p.name for p in loaded] == ["Development", "Staging", "Production"]
    assert not path.exists()


def test_save_creates_parent_dirs(tmp_path: Path):
    path = tmp_path / "hosts-manager" / "profiles.json"
    store = ProfileStore(path)
    store.save(default_profiles())
    data = json.loads(path.read_text(encoding="utf-8"))
    assert len(data["profiles"]) == 3
