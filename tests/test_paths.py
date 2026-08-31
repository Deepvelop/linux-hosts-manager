from pathlib import Path

from hosts_manager.paths import APP_ID, packaged_app_root, packaged_helper_path


def test_app_id():
    assert APP_ID == "com.deepvelop.HostsManager"


def test_packaged_app_root_from_source():
    root = packaged_app_root()
    assert root is not None
    assert (root / "app.py").is_file()


def test_packaged_helper_path_from_repo():
    helper = packaged_helper_path()
    assert helper is not None
    assert helper.name == "hosts-manager-helper.py"


def test_packaged_helper_prefers_system_install(tmp_path: Path, monkeypatch):
    system_helper = tmp_path / "hosts-manager-helper"
    system_helper.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr(
        "hosts_manager.paths.SYSTEM_HELPER_PATHS",
        (str(system_helper),),
    )
    assert packaged_helper_path() == system_helper
