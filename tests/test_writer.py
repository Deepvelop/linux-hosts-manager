from pathlib import Path

import pytest

from hosts_manager.writer import MAX_BYTES, WriteError, write_hosts


def test_writes_content_and_creates_backup(tmp_path: Path):
    hosts = tmp_path / "hosts"
    backups = tmp_path / "backups"
    hosts.write_text("127.0.0.1 localhost\n", encoding="utf-8")
    new = "127.0.0.1 localhost\n# BEGIN Hosts Manager\n127.0.0.1 app.local\n# END Hosts Manager\n"
    write_hosts(new, hosts_path=hosts, backup_dir=backups)
    assert hosts.read_text(encoding="utf-8") == new
    backup_files = list(backups.glob("hosts.*"))
    assert len(backup_files) == 1
    assert backup_files[0].read_text(encoding="utf-8") == "127.0.0.1 localhost\n"


def test_refuses_empty_content(tmp_path: Path):
    hosts = tmp_path / "hosts"
    hosts.write_text("127.0.0.1 localhost\n", encoding="utf-8")
    with pytest.raises(WriteError, match="empty"):
        write_hosts("", hosts_path=hosts, backup_dir=tmp_path / "backups")
    assert hosts.read_text(encoding="utf-8") == "127.0.0.1 localhost\n"


def test_refuses_invalid_entry(tmp_path: Path):
    hosts = tmp_path / "hosts"
    hosts.write_text("127.0.0.1 localhost\n", encoding="utf-8")
    with pytest.raises(WriteError):
        write_hosts("999.0.0.1 bad.local\n", hosts_path=hosts, backup_dir=tmp_path / "backups")
    assert hosts.read_text(encoding="utf-8") == "127.0.0.1 localhost\n"


def test_allows_unknown_and_comment_lines(tmp_path: Path):
    hosts = tmp_path / "hosts"
    hosts.write_text("127.0.0.1 localhost\n", encoding="utf-8")
    new = "127.0.0.1 localhost\n# keep\ngarbage\n"
    write_hosts(new, hosts_path=hosts, backup_dir=tmp_path / "backups")
    assert hosts.read_text(encoding="utf-8") == new


def test_keeps_only_last_ten_backups(tmp_path: Path):
    hosts = tmp_path / "hosts"
    backups = tmp_path / "backups"
    hosts.write_text("127.0.0.1 localhost\n", encoding="utf-8")
    for i in range(12):
        write_hosts(
            f"127.0.0.1 localhost\n# gen {i}\n",
            hosts_path=hosts,
            backup_dir=backups,
        )
    assert len(list(backups.glob("hosts.*"))) == 10


def test_refuses_oversized_content(tmp_path: Path):
    hosts = tmp_path / "hosts"
    hosts.write_text("127.0.0.1 localhost\n", encoding="utf-8")
    huge = "127.0.0.1 localhost\n" + ("# x\n" * ((MAX_BYTES // 4) + 1))
    with pytest.raises(WriteError, match="large"):
        write_hosts(huge, hosts_path=hosts, backup_dir=tmp_path / "backups")
