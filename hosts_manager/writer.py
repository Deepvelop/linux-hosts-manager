from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from hosts_manager.models import LineKind
from hosts_manager.parser import parse
from hosts_manager.validate import ValidationError, validate_hostname, validate_ip

MAX_BYTES = 1 * 1024 * 1024
KEEP_BACKUPS = 10
DEFAULT_HOSTS_PATH = Path("/etc/hosts")
DEFAULT_BACKUP_DIR = Path("/var/backups/hosts-manager")


class WriteError(ValueError):
    pass


def hosts_path_from_env() -> Path:
    override = os.environ.get("HOSTS_MANAGER_HOSTS_PATH")
    return Path(override) if override else DEFAULT_HOSTS_PATH


def backup_dir_from_env() -> Path:
    override = os.environ.get("HOSTS_MANAGER_BACKUP_DIR")
    return Path(override) if override else DEFAULT_BACKUP_DIR


def write_hosts(
    content: str,
    hosts_path: Path | None = None,
    backup_dir: Path | None = None,
) -> None:
    hosts_path = hosts_path or hosts_path_from_env()
    backup_dir = backup_dir or backup_dir_from_env()
    payload = content.encode("utf-8")
    _validate_payload(content, payload)
    _backup_existing(hosts_path, backup_dir)
    _atomic_write(hosts_path, payload)


def _validate_payload(content: str, payload: bytes) -> None:
    if not payload:
        raise WriteError("Refusing to write empty hosts file")
    if len(payload) > MAX_BYTES:
        raise WriteError("Proposed hosts file is too large")
    document = parse(content)
    try:
        for line in document.lines:
            if line.kind in (LineKind.ENTRY, LineKind.DISABLED_ENTRY):
                validate_ip(line.ip)
                for hostname in line.hostnames:
                    validate_hostname(hostname)
            elif line.kind == LineKind.UNKNOWN:
                _reject_malformed_entry(line.raw)
    except ValidationError as exc:
        raise WriteError(str(exc)) from exc


def _reject_malformed_entry(raw: str) -> None:
    tokens = raw.strip().split()
    if len(tokens) < 2:
        return
    try:
        validate_ip(tokens[0])
    except ValidationError:
        if _looks_like_ip(tokens[0]):
            raise WriteError(f"Invalid IP address in hosts entry: {tokens[0]}")
        return
    raise WriteError(f"Invalid hosts entry: {raw.strip()}")


def _looks_like_ip(token: str) -> bool:
    if ":" in token:
        return True
    parts = token.split(".")
    return len(parts) == 4 and all(part.isdigit() for part in parts)


def _backup_existing(hosts_path: Path, backup_dir: Path) -> None:
    if not hosts_path.exists():
        return
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    dest = backup_dir / f"hosts.{stamp}"
    dest.write_bytes(hosts_path.read_bytes())
    _prune_backups(backup_dir)


def _prune_backups(backup_dir: Path) -> None:
    backups = sorted(backup_dir.glob("hosts.*"))
    extra = len(backups) - KEEP_BACKUPS
    for path in backups[: max(extra, 0)]:
        path.unlink(missing_ok=True)


def _atomic_write(hosts_path: Path, payload: bytes) -> None:
    hosts_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix="hosts.", dir=str(hosts_path.parent))
    try:
        written = 0
        while written < len(payload):
            written += os.write(fd, payload[written:])
        os.fsync(fd)
    except Exception:
        os.close(fd)
        os.unlink(tmp_name)
        raise
    os.close(fd)
    os.replace(tmp_name, str(hosts_path))
    os.chmod(hosts_path, 0o644)
    if os.geteuid() == 0:
        os.chown(hosts_path, 0, 0)
