#!/usr/bin/env python3
"""Privileged writer for /etc/hosts. Invoked via pkexec; never run the GUI as root."""

from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

ROOT_CANDIDATES = (
    Path(__file__).resolve().parent.parent,
    Path("/app/share/hosts-manager"),
    Path("/usr/share/hosts-manager"),
    Path("/usr/local/share/hosts-manager"),
)


def _ensure_package_path() -> None:
    for candidate in ROOT_CANDIDATES:
        if (candidate / "hosts_manager").is_dir():
            sys.path.insert(0, str(candidate))
            return


def _probe() -> int:
    """Confirm elevated access without modifying /etc/hosts."""
    _ensure_package_path()
    from hosts_manager.writer import hosts_path_from_env

    path = hosts_path_from_env()
    if os.geteuid() == 0:
        return 0
    if path.exists() and os.access(path, os.W_OK):
        return 0
    print("Administrator privileges are required", file=sys.stderr)
    return 1


def _write_once(payload: bytes) -> int:
    _ensure_package_path()
    from hosts_manager.writer import WriteError, write_hosts

    try:
        content = payload.decode("utf-8")
    except UnicodeDecodeError:
        print("Hosts content must be UTF-8", file=sys.stderr)
        return 1
    try:
        write_hosts(content)
    except WriteError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Failed to write hosts file: {exc}", file=sys.stderr)
        return 1
    return 0


def _session() -> int:
    """Stay elevated and accept multiple length-prefixed writes until EOF / zero length."""
    _ensure_package_path()
    from hosts_manager.writer import WriteError, write_hosts

    sys.stdout.buffer.write(b"READY\n")
    sys.stdout.buffer.flush()
    while True:
        header = sys.stdin.buffer.read(4)
        if len(header) < 4:
            return 0
        length = struct.unpack(">I", header)[0]
        if length == 0:
            return 0
        payload = sys.stdin.buffer.read(length)
        if len(payload) < length:
            sys.stdout.buffer.write(b"ERR Incomplete payload\n")
            sys.stdout.buffer.flush()
            return 1
        try:
            content = payload.decode("utf-8")
            write_hosts(content)
            sys.stdout.buffer.write(b"OK\n")
        except UnicodeDecodeError:
            sys.stdout.buffer.write(b"ERR Hosts content must be UTF-8\n")
        except WriteError as exc:
            sys.stdout.buffer.write(f"ERR {exc}\n".encode("utf-8"))
        except OSError as exc:
            sys.stdout.buffer.write(f"ERR Failed to write hosts file: {exc}\n".encode("utf-8"))
        sys.stdout.buffer.flush()


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--probe" in args:
        return _probe()
    if "--session" in args:
        return _session()

    payload = sys.stdin.buffer.read()
    return _write_once(payload)


if __name__ == "__main__":
    sys.exit(main())
