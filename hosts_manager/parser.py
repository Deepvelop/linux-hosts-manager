from __future__ import annotations

from hosts_manager.models import (
    MANAGED_BEGIN,
    MANAGED_END,
    HostsDocument,
    HostsLine,
    LineKind,
)
from hosts_manager.validate import validate_hostname, validate_ip


def parse(text: str) -> HostsDocument:
    trailing_newline = text.endswith("\n") or text == ""
    raw_lines = text.splitlines()
    return HostsDocument(
        lines=[_parse_line(raw) for raw in raw_lines],
        trailing_newline=trailing_newline,
    )


def serialize(document: HostsDocument) -> str:
    body = "\n".join(line.raw for line in document.lines)
    if document.trailing_newline:
        if body:
            return body + "\n"
        return "\n" if document.lines else ""
    return body


def format_entry_line(ip: str, hostname: str, comment: str = "", enabled: bool = True) -> str:
    line = f"{ip} {hostname}"
    if comment:
        line = f"{line}  # {comment}"
    if not enabled:
        line = f"# {line}"
    return line


def _parse_line(raw: str) -> HostsLine:
    stripped = raw.strip()
    if stripped == "":
        return HostsLine(kind=LineKind.BLANK, raw=raw)
    if stripped == MANAGED_BEGIN:
        return HostsLine(kind=LineKind.MANAGED_BEGIN, raw=raw)
    if stripped == MANAGED_END:
        return HostsLine(kind=LineKind.MANAGED_END, raw=raw)

    if stripped.startswith("#"):
        remainder = stripped[1:].lstrip()
        parsed = _try_parse_entry(remainder)
        if parsed is not None:
            ip, hostnames, comment = parsed
            return HostsLine(
                kind=LineKind.DISABLED_ENTRY,
                raw=raw,
                ip=ip,
                hostnames=hostnames,
                comment=comment,
                enabled=False,
            )
        return HostsLine(kind=LineKind.COMMENT, raw=raw)

    parsed = _try_parse_entry(stripped)
    if parsed is not None:
        ip, hostnames, comment = parsed
        return HostsLine(
            kind=LineKind.ENTRY,
            raw=raw,
            ip=ip,
            hostnames=hostnames,
            comment=comment,
            enabled=True,
        )
    return HostsLine(kind=LineKind.UNKNOWN, raw=raw)


def _try_parse_entry(body: str) -> tuple[str, list[str], str] | None:
    if not body:
        return None
    comment = ""
    if " #" in body or body.startswith("#"):
        # Inline comment: split on the last-ish hosts-file convention (first unquoted #)
        hash_at = _inline_comment_index(body)
        if hash_at is not None:
            comment = body[hash_at + 1 :].strip()
            body = body[:hash_at].rstrip()
    tokens = body.split()
    if len(tokens) < 2:
        return None
    ip, hostnames = tokens[0], tokens[1:]
    try:
        validate_ip(ip)
        for hostname in hostnames:
            validate_hostname(hostname)
    except Exception:
        return None
    return ip, hostnames, comment


def _inline_comment_index(body: str) -> int | None:
    """Return the index of an inline '#' that starts a comment, if any."""
    # Hosts files use: IP hostname [# comment]
    # A '#' attached to a token (rare) is still treated as comment start.
    for i, ch in enumerate(body):
        if ch == "#":
            if i == 0:
                return None
            if body[i - 1].isspace():
                return i
    return None
