"""Import unmanaged hosts-file lines into the 'Existing hosts' profile."""

from __future__ import annotations

from dataclasses import dataclass, field

from hosts_manager.merge import merge_profiles, split_managed
from hosts_manager.models import HostEntry, HostsDocument, HostsLine, LineKind, Profile
from hosts_manager.parser import parse

IMPORT_PROFILE_ID = "existing-hosts"
IMPORT_PROFILE_NAME = "Existing hosts"
IMPORT_PROFILE_ICON = "home"


@dataclass
class ImportProblem:
    lineno: int
    raw: str
    fault: str


@dataclass
class ImportPlan:
    entries: list[HostEntry] = field(default_factory=list)
    problems: list[ImportProblem] = field(default_factory=list)
    source_lines: set[int] = field(default_factory=set)
    delete_lines: set[int] = field(default_factory=set)
    keep_lines: set[int] = field(default_factory=set)


def plan_import(document: HostsDocument, profiles: list[Profile]) -> ImportPlan:
    """Scan lines outside the managed block; build entries and problems."""
    before, _, after = split_managed(document)
    plan = ImportPlan()
    seen: dict[str, int] = {}
    enabled_names: dict[str, str] = {}
    for profile in profiles:
        if not profile.enabled:
            continue
        for entry in profile.entries:
            enabled_names.setdefault(entry.hostname.lower(), profile.name)

    for line in [*before, *after]:
        if line.kind in (LineKind.ENTRY, LineKind.DISABLED_ENTRY):
            _add_line(
                plan,
                line,
                enabled=line.kind == LineKind.ENTRY,
                seen=seen,
                enabled_names=enabled_names,
            )
        elif line.kind == LineKind.UNKNOWN:
            plan.problems.append(
                ImportProblem(
                    lineno=line.lineno,
                    raw=line.raw,
                    fault=line.fault or "Unrecognized line",
                )
            )
    return plan


def replan_with_edits(
    original: HostsDocument,
    plan: ImportPlan,
    edited_raws: dict[int, str],
    profiles: list[Profile],
) -> ImportPlan:
    """Re-run plan_import after the user edited problem lines.

    Lines the user removed (plan.delete_lines) are dropped from the scan;
    edited raw text replaces the original line content.
    """
    lines: list[HostsLine] = []
    for line in original.lines:
        if line.lineno in plan.delete_lines:
            continue
        if line.lineno in edited_raws:
            parsed_lines = parse(edited_raws[line.lineno]).lines
            if len(parsed_lines) > 1:
                raise ValueError("Edited line must contain at most one line")
            if parsed_lines:
                reparsed = parsed_lines[0]
                reparsed.lineno = line.lineno
            else:
                reparsed = HostsLine(kind=LineKind.BLANK, raw="", lineno=line.lineno)
            lines.append(reparsed)
        else:
            lines.append(line)
    new_plan = plan_import(
        HostsDocument(lines=lines, trailing_newline=original.trailing_newline),
        profiles,
    )
    new_plan.delete_lines = set(plan.delete_lines)
    new_plan.keep_lines = set(plan.keep_lines)
    for lineno in edited_raws:
        if lineno in new_plan.source_lines:
            continue
        if any(problem.lineno == lineno for problem in new_plan.problems):
            continue
        new_plan.keep_lines.add(lineno)
    return new_plan


def ensure_import_profile(
    profiles: list[Profile], entries: list[HostEntry]
) -> tuple[Profile, bool]:
    """Return the reserved import profile, appending entries; create it on first use."""
    for profile in profiles:
        if profile.id == IMPORT_PROFILE_ID:
            profile.entries.extend(entries)
            profile.enabled = True
            return profile, False
    profile = Profile(
        id=IMPORT_PROFILE_ID,
        name=IMPORT_PROFILE_NAME,
        icon=IMPORT_PROFILE_ICON,
        enabled=True,
        entries=list(entries),
    )
    profiles.append(profile)
    return profile, True


def build_imported_text(
    document: HostsDocument, plan: ImportPlan, profiles: list[Profile]
) -> str:
    """Remove moved/deleted lines, then merge profiles (import profile included)."""
    if plan.problems:
        raise ValueError("Cannot import: unresolved problem lines remain")
    drop = plan.source_lines | plan.delete_lines
    cleaned = HostsDocument(
        lines=[line for line in document.lines if line.lineno not in drop],
        trailing_newline=document.trailing_newline,
    )
    target_profiles = list(profiles)
    ensure_import_profile(target_profiles, plan.entries)
    return merge_profiles(cleaned, target_profiles)


def _add_line(
    plan: ImportPlan,
    line: HostsLine,
    *,
    enabled: bool,
    seen: dict[str, int],
    enabled_names: dict[str, str],
) -> None:
    local_seen: dict[str, int] = {}
    for name in line.hostnames:
        prior = seen.get(name.lower()) or local_seen.get(name.lower())
        if prior is not None:
            _fail_line(plan, line, f"Duplicate hostname '{name}' (also on line {prior})")
            return
        clash = enabled_names.get(name.lower())
        if clash is not None:
            _fail_line(plan, line, f"Hostname '{name}' already in profile '{clash}'")
            return
        local_seen[name.lower()] = line.lineno
    entries = [
        HostEntry(ip=line.ip, hostname=name, enabled=enabled, comment=line.comment)
        for name in line.hostnames
    ]
    for entry in entries:
        seen[entry.hostname.lower()] = line.lineno
    plan.entries.extend(entries)
    plan.source_lines.add(line.lineno)


def _fail_line(plan: ImportPlan, line: HostsLine, fault: str) -> None:
    plan.problems.append(ImportProblem(lineno=line.lineno, raw=line.raw, fault=fault))
