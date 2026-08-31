from __future__ import annotations

import atexit
import os
import shutil
import struct
import subprocess
import threading
from pathlib import Path

from hosts_manager.bootstrap import ensure_host_privileged_install
from hosts_manager.paths import SYSTEM_HELPER_PATHS, packaged_helper_path
from hosts_manager.writer import backup_dir_from_env, hosts_path_from_env, write_hosts

_session: subprocess.Popen[bytes] | None = None
_session_lock = threading.Lock()


def skip_polkit() -> bool:
    value = os.environ.get("HOSTS_MANAGER_SKIP_POLKIT", "")
    return value.lower() in {"1", "true", "yes"}


def helper_executable() -> str:
    override = os.environ.get("HOSTS_MANAGER_HELPER")
    if override:
        return override
    for path in SYSTEM_HELPER_PATHS:
        if os.path.isfile(path):
            return path
    packaged = packaged_helper_path()
    if packaged is not None:
        return str(packaged)
    repo_helper = Path(__file__).resolve().parents[1] / "helper" / "hosts-manager-helper.py"
    return str(repo_helper)


def helper_available() -> bool:
    return os.path.isfile(helper_executable())


def pkexec_available() -> bool:
    return shutil.which("pkexec") is not None


def can_apply() -> bool:
    if skip_polkit():
        return True
    if not pkexec_available():
        return False
    if helper_available():
        return True
    return ensure_host_privileged_install() and helper_available()


class WriteSessionError(RuntimeError):
    """Elevated write session failed."""


def ensure_authorized() -> bool:
    """Prompt for admin rights once and keep a session helper open."""
    if skip_polkit():
        return True
    if not can_apply():
        return False
    try:
        _ensure_session()
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, OSError, WriteSessionError):
        return False


def _close_session() -> None:
    global _session
    with _session_lock:
        proc = _session
        _session = None
        if proc is None:
            return
        try:
            if proc.stdin and proc.poll() is None:
                proc.stdin.write(struct.pack(">I", 0))
                proc.stdin.flush()
        except OSError:
            pass
        try:
            proc.terminate()
        except OSError:
            pass
        try:
            proc.wait(timeout=2)
        except (subprocess.TimeoutExpired, OSError):
            try:
                proc.kill()
            except OSError:
                pass


def _ensure_session() -> subprocess.Popen[bytes]:
    global _session
    with _session_lock:
        if _session is not None and _session.poll() is None:
            return _session
        _session = None
        proc = subprocess.Popen(
            ["pkexec", helper_executable(), "--session"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert proc.stdout is not None
        line = proc.stdout.readline()
        if proc.poll() is not None or line.strip() != b"READY":
            err = b""
            if proc.stderr is not None:
                err = proc.stderr.read()
            detail = err.decode("utf-8", errors="replace").strip() or "Administrator authorization was cancelled"
            raise WriteSessionError(detail)
        _session = proc
        return proc


atexit.register(_close_session)


def _session_write(content: str) -> None:
    proc = _ensure_session()
    assert proc.stdin is not None and proc.stdout is not None
    payload = content.encode("utf-8")
    try:
        proc.stdin.write(struct.pack(">I", len(payload)))
        proc.stdin.write(payload)
        proc.stdin.flush()
        response = proc.stdout.readline()
    except OSError as exc:
        _close_session()
        raise WriteSessionError(str(exc)) from exc

    if not response:
        _close_session()
        raise WriteSessionError("Privileged helper closed unexpectedly")
    text = response.decode("utf-8", errors="replace").rstrip("\n")
    if text == "OK":
        return
    if text.startswith("ERR "):
        _close_session()
        raise WriteSessionError(text[4:] or "Could not update the hosts file")
    _close_session()
    raise WriteSessionError(text or "Unexpected helper response")


def apply_hosts(content: str) -> None:
    if skip_polkit():
        write_hosts(content, hosts_path_from_env(), backup_dir_from_env())
        return
    _session_write(content)
