from __future__ import annotations

import ipaddress
import re

from hosts_manager.models import HostEntry


class ValidationError(ValueError):
    pass


_LABEL_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")


def validate_ip(ip: str) -> None:
    if not ip or not str(ip).strip():
        raise ValidationError("IP address is required")
    try:
        ipaddress.ip_address(ip.strip())
    except ValueError as exc:
        raise ValidationError(f"Invalid IP address: {ip}") from exc


def validate_hostname(hostname: str) -> None:
    name = (hostname or "").strip()
    if not name:
        raise ValidationError("Hostname is required")
    if name == "*":
        raise ValidationError("Wildcard hostnames are not allowed")
    if any(ch.isspace() for ch in name):
        raise ValidationError("Hostname must not contain spaces")
    if name.endswith("."):
        raise ValidationError("Hostname must not end with a dot")
    if len(name) > 253:
        raise ValidationError("Hostname is too long")
    labels = name.split(".")
    if not labels or any(not label for label in labels):
        raise ValidationError(f"Invalid hostname: {hostname}")
    for label in labels:
        if len(label) > 63 or not _LABEL_RE.match(label):
            raise ValidationError(f"Invalid hostname: {hostname}")


def validate_entry(entry: HostEntry) -> None:
    validate_ip(entry.ip)
    validate_hostname(entry.hostname)


def validate_hostnames(hostnames: list[str]) -> None:
    if not hostnames:
        raise ValidationError("At least one hostname is required")
    for hostname in hostnames:
        validate_hostname(hostname)


def ip_family(ip: str) -> str:
    """Return "ipv4" or "ipv6" for a hosts-file IP literal."""
    return "ipv6" if ":" in ip else "ipv4"
