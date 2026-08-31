from __future__ import annotations

from collections import Counter

from hosts_manager.models import (
    MANAGED_BEGIN,
    MANAGED_END,
    HostEntry,
    HostsDocument,
    HostsLine,
    LineKind,
    Profile,
)
from hosts_manager.parser import format_entry_line, serialize
from hosts_manager.validate import ip_family, validate_entry


class MergeConflict(Exception):
    def __init__(self, hostnames: list[str], message: str | None = None) -> None:
        self.hostnames = hostnames
        super().__init__(message or _conflict_message(hostnames))


def merge_profiles(document: HostsDocument, profiles: list[Profile]) -> str:
    enabled = [profile for profile in profiles if profile.enabled]
    flattened = _flatten(enabled)
    _validate_entries(flattened)
    _raise_if_duplicate_hostnames(flattened)

    adopted = adopted_map(profiles)
    before, _managed, after = split_managed(document)
    adopted_keys = _adopted_keys([*before, *after], adopted)
    before = _rewrite_adopted(before, adopted)
    after = _rewrite_adopted(after, adopted)
    block = _build_managed_block(enabled, adopted_keys)
    combined = _join_sections(before, block, after)
    return serialize(HostsDocument(lines=combined, trailing_newline=True))


def split_managed(
    document: HostsDocument,
) -> tuple[list[HostsLine], list[HostsLine], list[HostsLine]]:
    begin = next(
        (i for i, line in enumerate(document.lines) if line.kind == LineKind.MANAGED_BEGIN),
        None,
    )
    end = next(
        (i for i, line in enumerate(document.lines) if line.kind == LineKind.MANAGED_END),
        None,
    )
    if begin is None or end is None or end < begin:
        return list(document.lines), [], []
    return document.lines[:begin], document.lines[begin : end + 1], document.lines[end + 1 :]


def adopted_map(profiles: list[Profile]) -> dict[tuple[str, str], HostEntry]:
    """Map (hostname, family) -> owning entry; profiles in order, first match wins."""
    adopted: dict[tuple[str, str], HostEntry] = {}
    for profile in profiles:
        for entry in profile.entries:
            adopted.setdefault((entry.hostname.lower(), ip_family(entry.ip)), entry)
    return adopted


def _adopted_keys(
    lines: list[HostsLine], adopted: dict[tuple[str, str], HostEntry]
) -> set[tuple[str, str]]:
    """Adopted keys that are actually present among the given lines."""
    keys: set[tuple[str, str]] = set()
    for line in lines:
        if line.kind not in (LineKind.ENTRY, LineKind.DISABLED_ENTRY):
            continue
        for name in line.hostnames:
            key = (name.lower(), ip_family(line.ip))
            if key in adopted:
                keys.add(key)
    return keys


def _rewrite_adopted(
    lines: list[HostsLine], adopted: dict[tuple[str, str], HostEntry]
) -> list[HostsLine]:
    """Rewrite adopted outside-block lines in place with their owners' settings."""
    rewritten: list[HostsLine] = []
    for line in lines:
        if line.kind not in (LineKind.ENTRY, LineKind.DISABLED_ENTRY):
            rewritten.append(line)
            continue
        owners = [
            adopted[(name.lower(), ip_family(line.ip))]
            for name in line.hostnames
            if (name.lower(), ip_family(line.ip)) in adopted
        ]
        if not owners:
            rewritten.append(line)
            continue
        enabled = all(owner.enabled for owner in owners)
        ips = {owner.ip for owner in owners}
        comments = {owner.comment for owner in owners}
        if len(ips) > 1 or len(comments) > 1:
            names = sorted({owner.hostname for owner in owners})
            raise MergeConflict(
                names, f"Conflicting settings for shared line: {', '.join(names)}"
            )
        owner = owners[0]
        raw = format_entry_line(owner.ip, " ".join(line.hostnames), owner.comment, enabled)
        rewritten.append(
            HostsLine(
                kind=LineKind.ENTRY if enabled else LineKind.DISABLED_ENTRY,
                raw=raw,
                lineno=line.lineno,
                ip=owner.ip,
                hostnames=list(line.hostnames),
                comment=owner.comment,
                enabled=enabled,
            )
        )
    return rewritten


def managed_entries(document: HostsDocument) -> dict[tuple[str, str], tuple[str, str, bool]]:
    """Map (hostname, ip-family) -> (ip, hostname, enabled) for managed-block entries."""
    _, managed, _ = split_managed(document)
    entries: dict[tuple[str, str], tuple[str, str, bool]] = {}
    for line in managed:
        if line.kind in (LineKind.ENTRY, LineKind.DISABLED_ENTRY) and line.hostnames:
            hostname = line.hostnames[0]
            entries[(hostname.lower(), ip_family(line.ip))] = (
                line.ip,
                hostname,
                line.enabled,
            )
    return entries


def _flatten(profiles: list[Profile]) -> list[HostEntry]:
    entries: list[HostEntry] = []
    for profile in profiles:
        entries.extend(profile.entries)
    return entries


def _validate_entries(entries: list[HostEntry]) -> None:
    for entry in entries:
        validate_entry(entry)


def _raise_if_duplicate_hostnames(entries: list[HostEntry]) -> None:
    name_counts = Counter(entry.hostname.lower() for entry in entries)
    family_counts = Counter(
        (entry.hostname.lower(), ip_family(entry.ip)) for entry in entries
    )
    dupes = sorted(
        {name for name, count in name_counts.items() if count > 2}
        | {name for (name, _family), count in family_counts.items() if count > 1}
    )
    if dupes:
        raise MergeConflict(dupes, f"Duplicate hostname(s) in enabled profiles: {', '.join(dupes)}")


def _build_managed_block(
    profiles: list[Profile], adopted_keys: set[tuple[str, str]]
) -> list[HostsLine]:
    lines = [HostsLine(kind=LineKind.MANAGED_BEGIN, raw=MANAGED_BEGIN)]
    contributing: list[tuple[Profile, list[HostEntry]]] = []
    for profile in profiles:
        kept = [
            entry
            for entry in profile.entries
            if (entry.hostname.lower(), ip_family(entry.ip)) not in adopted_keys
        ]
        if kept:
            contributing.append((profile, kept))
    for index, (profile, entries) in enumerate(contributing):
        lines.append(HostsLine(kind=LineKind.COMMENT, raw=f"# Profile: {profile.name}"))
        for entry in entries:
            raw = format_entry_line(entry.ip, entry.hostname, entry.comment, entry.enabled)
            kind = LineKind.ENTRY if entry.enabled else LineKind.DISABLED_ENTRY
            lines.append(
                HostsLine(
                    kind=kind,
                    raw=raw,
                    ip=entry.ip,
                    hostnames=[entry.hostname],
                    comment=entry.comment,
                    enabled=entry.enabled,
                )
            )
        if index < len(contributing) - 1:
            lines.append(HostsLine(kind=LineKind.BLANK, raw=""))
    lines.append(HostsLine(kind=LineKind.MANAGED_END, raw=MANAGED_END))
    return lines


def _join_sections(
    before: list[HostsLine],
    block: list[HostsLine],
    after: list[HostsLine],
) -> list[HostsLine]:
    return list(before) + list(block) + list(after)


def _conflict_message(hostnames: list[str]) -> str:
    return f"Conflicting hostname(s): {', '.join(hostnames)}"
