from pathlib import Path
from unittest.mock import MagicMock, patch

from hosts_manager.polkit import apply_hosts, ensure_authorized, helper_executable, skip_polkit


def test_skip_polkit_when_env_set(monkeypatch):
    monkeypatch.setenv("HOSTS_MANAGER_SKIP_POLKIT", "1")
    assert skip_polkit() is True


def test_helper_prefers_env_override(tmp_path: Path, monkeypatch):
    helper = tmp_path / "helper"
    helper.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setenv("HOSTS_MANAGER_HELPER", str(helper))
    assert helper_executable() == str(helper)


def test_apply_hosts_skip_polkit_writes_fake_file(tmp_path: Path, monkeypatch):
    hosts = tmp_path / "hosts"
    backups = tmp_path / "backups"
    hosts.write_text("127.0.0.1 localhost\n", encoding="utf-8")
    monkeypatch.setenv("HOSTS_MANAGER_SKIP_POLKIT", "1")
    monkeypatch.setenv("HOSTS_MANAGER_HOSTS_PATH", str(hosts))
    monkeypatch.setenv("HOSTS_MANAGER_BACKUP_DIR", str(backups))
    new = "127.0.0.1 localhost\n# BEGIN Hosts Manager\n127.0.0.1 app.local\n# END Hosts Manager\n"
    apply_hosts(new)
    assert hosts.read_text(encoding="utf-8") == new


def test_apply_hosts_uses_session_helper_when_not_skipped(monkeypatch):
    monkeypatch.delenv("HOSTS_MANAGER_SKIP_POLKIT", raising=False)
    monkeypatch.setenv("HOSTS_MANAGER_HELPER", "/usr/libexec/hosts-manager-helper")

    import hosts_manager.polkit as polkit

    monkeypatch.setattr(polkit, "_session", None)

    stdout = MagicMock()
    stdout.readline.side_effect = [b"READY\n", b"OK\n"]
    stdin = MagicMock()
    proc = MagicMock()
    proc.poll.return_value = None
    proc.stdin = stdin
    proc.stdout = stdout
    proc.stderr = MagicMock()

    with patch("hosts_manager.polkit.subprocess.Popen", return_value=proc) as popen:
        apply_hosts("127.0.0.1 localhost\n")
        popen.assert_called_once()
        args, kwargs = popen.call_args
        assert args[0] == ["pkexec", "/usr/libexec/hosts-manager-helper", "--session"]
        assert kwargs["stdin"] is not None
        assert stdin.write.call_count >= 2
        assert stdout.readline.call_count == 2


def test_ensure_authorized_skip_polkit(monkeypatch):
    monkeypatch.setenv("HOSTS_MANAGER_SKIP_POLKIT", "1")
    assert ensure_authorized() is True


def test_ensure_authorized_opens_session(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("HOSTS_MANAGER_SKIP_POLKIT", raising=False)
    helper = tmp_path / "hosts-manager-helper"
    helper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    helper.chmod(0o755)
    monkeypatch.setenv("HOSTS_MANAGER_HELPER", str(helper))

    import hosts_manager.polkit as polkit

    monkeypatch.setattr(polkit, "_session", None)

    stdout = MagicMock()
    stdout.readline.return_value = b"READY\n"
    proc = MagicMock()
    proc.poll.return_value = None
    proc.stdin = MagicMock()
    proc.stdout = stdout
    proc.stderr = MagicMock()

    with patch("hosts_manager.polkit.subprocess.Popen", return_value=proc) as popen:
        assert ensure_authorized() is True
        args, _kwargs = popen.call_args
        assert args[0] == ["pkexec", str(helper), "--session"]


def test_helper_probe_succeeds_for_writable_fake_hosts(tmp_path: Path, monkeypatch):
    hosts = tmp_path / "hosts"
    hosts.write_text("127.0.0.1 localhost\n", encoding="utf-8")
    monkeypatch.setenv("HOSTS_MANAGER_HOSTS_PATH", str(hosts))
    from importlib.machinery import SourceFileLoader

    helper_path = Path(__file__).resolve().parents[1] / "helper" / "hosts-manager-helper.py"
    mod = SourceFileLoader("hosts_manager_helper", str(helper_path)).load_module()
    assert mod.main(["--probe"]) == 0


def test_helper_session_writes_multiple_payloads(tmp_path: Path, monkeypatch):
    hosts = tmp_path / "hosts"
    backups = tmp_path / "backups"
    hosts.write_text("127.0.0.1 localhost\n", encoding="utf-8")
    monkeypatch.setenv("HOSTS_MANAGER_HOSTS_PATH", str(hosts))
    monkeypatch.setenv("HOSTS_MANAGER_BACKUP_DIR", str(backups))

    from importlib.machinery import SourceFileLoader
    import io
    import struct

    helper_path = Path(__file__).resolve().parents[1] / "helper" / "hosts-manager-helper.py"
    mod = SourceFileLoader("hosts_manager_helper_session", str(helper_path)).load_module()

    first = b"127.0.0.1 localhost\n# BEGIN Hosts Manager\n127.0.0.1 a.local\n# END Hosts Manager\n"
    second = b"127.0.0.1 localhost\n# BEGIN Hosts Manager\n127.0.0.1 b.local\n# END Hosts Manager\n"
    payload = struct.pack(">I", len(first)) + first + struct.pack(">I", len(second)) + second + struct.pack(">I", 0)

    fake_in = io.BytesIO(payload)
    fake_out = io.BytesIO()
    monkeypatch.setattr(mod.sys, "stdin", MagicMock(buffer=fake_in))
    monkeypatch.setattr(mod.sys, "stdout", MagicMock(buffer=fake_out))

    assert mod.main(["--session"]) == 0
    assert hosts.read_text(encoding="utf-8") == second.decode()
    assert fake_out.getvalue().startswith(b"READY\n")
    assert b"OK\n" in fake_out.getvalue()
