from __future__ import annotations

from dataclasses import dataclass

from hosts_manager.merge import managed_entries, split_managed
from hosts_manager.models import HostEntry, HostsDocument, LineKind
from hosts_manager.parser import parse
from hosts_manager.validate import ip_family


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


def adopted_diff(
    old_document: HostsDocument,
    new_text: str,
    adopted: dict[tuple[str, str], HostEntry],
) -> list[DiffChange]:
    """Diff adopted lines outside the managed block, keyed by (hostname, family)."""
    old_map = _adopted_lines(old_document, adopted)
    new_map = _adopted_lines(parse(new_text), adopted)
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


def _adopted_lines(
    document: HostsDocument, adopted: dict[tuple[str, str], HostEntry]
) -> dict[tuple[str, str], tuple[str, str, bool]]:
    before, _, after = split_managed(document)
    result: dict[tuple[str, str], tuple[str, str, bool]] = {}
    for line in [*before, *after]:
        if line.kind not in (LineKind.ENTRY, LineKind.DISABLED_ENTRY):
            continue
        for name in line.hostnames:
            key = (name.lower(), ip_family(line.ip))
            if key in adopted and key not in result:
                result[key] = (line.ip, name, line.enabled)
    return result
