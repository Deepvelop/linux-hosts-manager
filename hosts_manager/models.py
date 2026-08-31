from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


MANAGED_BEGIN = "# BEGIN Hosts Manager"
MANAGED_END = "# END Hosts Manager"


class LineKind(Enum):
    BLANK = "blank"
    COMMENT = "comment"
    ENTRY = "entry"
    DISABLED_ENTRY = "disabled_entry"
    UNKNOWN = "unknown"
    MANAGED_BEGIN = "managed_begin"
    MANAGED_END = "managed_end"


@dataclass
class HostEntry:
    ip: str
    hostname: str
    enabled: bool = True
    comment: str = ""


@dataclass
class HostsLine:
    kind: LineKind
    raw: str
    ip: str = ""
    hostnames: list[str] = field(default_factory=list)
    comment: str = ""
    enabled: bool = True


@dataclass
class HostsDocument:
    lines: list[HostsLine]
    trailing_newline: bool = True


@dataclass
class Profile:
    id: str
    name: str
    icon: str = "default"
    enabled: bool = False
    entries: list[HostEntry] = field(default_factory=list)
