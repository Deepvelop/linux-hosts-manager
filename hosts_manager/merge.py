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
    _raise_if_unmanaged_clash(document, flattened)

    before, _managed, after = split_managed(document)
    block = _build_managed_block(enabled)
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


def unmanaged_hostnames(document: HostsDocument) -> set[str]:
    before, _, after = split_managed(document)
    names: set[str] = set()
    for line in before + after:
        if line.kind == LineKind.ENTRY:
            names.update(line.hostnames)
    return names


def managed_entries(document: HostsDocument) -> list[tuple[str, str, bool]]:
    _, managed, _ = split_managed(document)
    entries: list[tuple[str, str, bool]] = []
    for line in managed:
        if line.kind in (LineKind.ENTRY, LineKind.DISABLED_ENTRY) and line.hostnames:
            entries.append((line.ip, line.hostnames[0], line.enabled))
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


def _raise_if_unmanaged_clash(document: HostsDocument, entries: list[HostEntry]) -> None:
    existing = {name.lower() for name in unmanaged_hostnames(document)}
    clashes = sorted({entry.hostname for entry in entries if entry.hostname.lower() in existing})
    if clashes:
        raise MergeConflict(
            clashes,
            f"Hostname(s) already present outside Hosts Manager: {', '.join(clashes)}",
        )


def _build_managed_block(profiles: list[Profile]) -> list[HostsLine]:
    lines = [HostsLine(kind=LineKind.MANAGED_BEGIN, raw=MANAGED_BEGIN)]
    contributing = [profile for profile in profiles if profile.entries]
    for index, profile in enumerate(contributing):
        lines.append(
            HostsLine(kind=LineKind.COMMENT, raw=f"# Profile: {profile.name}")
        )
        for entry in profile.entries:
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
