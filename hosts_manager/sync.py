"""Reconcile the app's profiles with hand-edits in the hosts file."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace

from hosts_manager.merge import adopted_map, split_managed
from hosts_manager.models import HostEntry, HostsDocument, HostsLine, LineKind, Profile
from hosts_manager.validate import ip_family


@dataclass
class SyncChange:
    profile: str
    kind: str  # "add" | "update" | "remove"
    ip: str
    hostname: str


@dataclass
class SyncPlan:
    profiles: list[Profile] = field(default_factory=list)
    changes: list[SyncChange] = field(default_factory=list)


def plan_sync(document: HostsDocument, profiles: list[Profile]) -> SyncPlan:
    """Reconcile profiles with the file; never mutates the input profiles."""
    copies = [replace(p, entries=list(p.entries)) for p in profiles]
    adopted = adopted_map(copies)
    before, managed, after = split_managed(document)

    outside = [*before, *after]
    outside_keys = _adopted_keys_present(outside, adopted)
    changes: list[SyncChange] = _apply_adopted_lines(copies, outside, adopted)

    sections = _block_sections(managed)
    known_names = {profile.name: profile for profile in copies}
    reconciled: set[str] = set()

    for name, lines in sections.items():
        target = known_names.get(name)
        if target is None:
            target = Profile(
                id=uuid.uuid4().hex[:8],
                name=name,
                icon="default",
                enabled=True,
                entries=[],
            )
            copies.append(target)
        reconciled.add(name)
        changes.extend(_reconcile_section(target, lines, outside_keys))

    # Profiles with block-owned entries but no section: file is the truth — remove them.
    for profile in copies:
        if profile.name in reconciled:
            continue
        kept: list[HostEntry] = []
        for entry in profile.entries:
            key = (entry.hostname.lower(), ip_family(entry.ip))
            if key in outside_keys:
                kept.append(entry)
                continue
            changes.append(
                SyncChange(profile=profile.name, kind="remove", ip="", hostname=entry.hostname)
            )
        profile.entries = kept

    return SyncPlan(profiles=copies, changes=changes)


def _block_sections(managed: list[HostsLine]) -> dict[str, list[HostsLine]]:
    sections: dict[str, list[HostsLine]] = {}
    current: str | None = None
    for line in managed:
        if line.kind == LineKind.COMMENT and line.raw.startswith("# Profile: "):
            current = line.raw[len("# Profile: ") :]
            sections.setdefault(current, [])
        elif current is not None and line.kind in (LineKind.ENTRY, LineKind.DISABLED_ENTRY):
            sections[current].append(line)
    return sections


def _reconcile_section(
    profile: Profile,
    lines: list[HostsLine],
    outside_keys: set[tuple[str, str]],
) -> list[SyncChange]:
    changes: list[SyncChange] = []
    adopted_entries = [
        entry
        for entry in profile.entries
        if (entry.hostname.lower(), ip_family(entry.ip)) in outside_keys
    ]
    file_entries = _entries_from_lines(lines)
    old_block = {
        (entry.hostname.lower(), ip_family(entry.ip)): entry
        for entry in profile.entries
        if (entry.hostname.lower(), ip_family(entry.ip)) not in outside_keys
    }
    new_block = {
        (entry.hostname.lower(), ip_family(entry.ip)): entry for entry in file_entries
    }
    for key in sorted(set(old_block) | set(new_block)):
        old = old_block.get(key)
        new = new_block.get(key)
        if old is None and new is not None:
            changes.append(
                SyncChange(profile=profile.name, kind="add", ip=new.ip, hostname=new.hostname)
            )
        elif new is None and old is not None:
            changes.append(
                SyncChange(profile=profile.name, kind="remove", ip="", hostname=old.hostname)
            )
        elif old is not None and new is not None:
            if (old.ip, old.comment, old.enabled) != (new.ip, new.comment, new.enabled):
                changes.append(
                    SyncChange(
                        profile=profile.name, kind="update", ip=new.ip, hostname=new.hostname
                    )
                )
    profile.entries = adopted_entries + sorted(
        file_entries, key=lambda entry: entry.hostname.lower()
    )
    return changes


def _entries_from_lines(lines: list[HostsLine]) -> list[HostEntry]:
    entries: list[HostEntry] = []
    for line in lines:
        for name in line.hostnames:
            entries.append(
                HostEntry(
                    ip=line.ip,
                    hostname=name,
                    enabled=line.kind == LineKind.ENTRY,
                    comment=line.comment,
                )
            )
    return entries


def _adopted_keys_present(
    lines: list[HostsLine], adopted: dict[tuple[str, str], HostEntry]
) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for line in lines:
        if line.kind not in (LineKind.ENTRY, LineKind.DISABLED_ENTRY):
            continue
        for name in line.hostnames:
            key = (name.lower(), ip_family(line.ip))
            if key in adopted:
                keys.add(key)
    return keys


def _apply_adopted_lines(
    profiles: list[Profile],
    outside: list[HostsLine],
    adopted: dict[tuple[str, str], HostEntry],
) -> list[SyncChange]:
    """Update adopted entries from outside lines; return the changes."""
    owner_profiles = {
        (entry.hostname.lower(), ip_family(entry.ip)): profile.name
        for profile in profiles
        for entry in profile.entries
    }
    changes: list[SyncChange] = []
    for line in outside:
        if line.kind not in (LineKind.ENTRY, LineKind.DISABLED_ENTRY):
            continue
        keys = [
            (name.lower(), ip_family(line.ip))
            for name in line.hostnames
            if (name.lower(), ip_family(line.ip)) in adopted
        ]
        if not keys:
            continue
        single = len(keys) == 1
        for key in keys:
            owner = adopted[key]
            before = (owner.ip, owner.comment, owner.enabled)
            if owner.ip != line.ip:
                owner.ip = line.ip
            if owner.comment != line.comment:
                owner.comment = line.comment
            if single and owner.enabled != (line.kind == LineKind.ENTRY):
                owner.enabled = line.kind == LineKind.ENTRY
            if (owner.ip, owner.comment, owner.enabled) != before:
                changes.append(
                    SyncChange(
                        profile=owner_profiles[key],
                        kind="update",
                        ip=owner.ip,
                        hostname=owner.hostname,
                    )
                )
    return changes
