from __future__ import annotations

from dataclasses import dataclass

from hosts_manager.merge import managed_entries
from hosts_manager.models import HostsDocument
from hosts_manager.parser import parse


@dataclass(frozen=True)
class DiffChange:
    kind: str  # "add", "remove", "enable", or "disable"
    ip: str
    hostname: str


def format_diff_text(changes: list[DiffChange]) -> str:
    lines: list[str] = []
    for change in changes:
        if change.kind == "add":
            lines.append(f"+ {change.ip} {change.hostname}")
        elif change.kind == "remove":
            lines.append(f"- {change.ip} {change.hostname}")
        elif change.kind == "enable":
            lines.append(f"~ {change.ip} {change.hostname} (enabled)")
        elif change.kind == "disable":
            lines.append(f"~ {change.ip} {change.hostname} (disabled)")
        else:
            lines.append(f"* {change.ip} {change.hostname}")
    return "\n".join(lines)


def managed_diff(old_document: HostsDocument, new_text: str) -> list[DiffChange]:
    old_map = managed_entries(old_document)
    new_map = managed_entries(parse(new_text))

    changes: list[DiffChange] = []
    for key in sorted(set(old_map) | set(new_map)):
        old = old_map.get(key)
        new = new_map.get(key)
        if old is None and new is not None:
            ip, hostname, _enabled = new
            changes.append(DiffChange(kind="add", ip=ip, hostname=hostname))
        elif new is None and old is not None:
            ip, hostname, _enabled = old
            changes.append(DiffChange(kind="remove", ip=ip, hostname=hostname))
        elif old is not None and new is not None:
            old_ip, hostname, old_enabled = old
            new_ip, _, new_enabled = new
            if old_ip != new_ip:
                changes.append(DiffChange(kind="remove", ip=old_ip, hostname=hostname))
                changes.append(DiffChange(kind="add", ip=new_ip, hostname=hostname))
            elif old_enabled != new_enabled:
                kind = "enable" if new_enabled else "disable"
                changes.append(DiffChange(kind=kind, ip=new_ip, hostname=hostname))
    return changes
