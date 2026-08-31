"""GitHub-style diff rows for the app's confirmation dialogs."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Pango", "1.0")

from gi.repository import Gtk, Pango

from hosts_manager.diff import DiffChange
from hosts_manager.sync import SyncChange

MARKERS = {
    "add": ("+", "add"),
    "remove": ("−", "remove"),
    "change": ("~", "change"),
}


def marker_for(kind: str) -> tuple[str, str]:
    """Return (marker, css suffix) for a diff kind: add/remove/change."""
    return MARKERS[kind]


def rows_from_changes(changes: list[DiffChange]) -> list[tuple[str, str]]:
    """Map DiffChange list to (kind, text) rows for build_diff_box."""
    rows: list[tuple[str, str]] = []
    for change in changes:
        if change.kind in ("add", "remove"):
            rows.append((change.kind, f"{change.ip} {change.hostname}"))
        elif change.kind == "enable":
            rows.append(("change", f"{change.ip} {change.hostname} (enabled)"))
        elif change.kind == "disable":
            rows.append(("change", f"{change.ip} {change.hostname} (disabled)"))
    return rows


def rows_from_sync_changes(changes: list[SyncChange]) -> list[tuple[str, str]]:
    """Map SyncChange list to (kind, text) rows for build_diff_box."""
    rows: list[tuple[str, str]] = []
    for change in changes:
        kind = {"add": "add", "remove": "remove", "update": "change"}[change.kind]
        text = f"{change.ip} {change.hostname}".strip()
        rows.append((kind, text))
    return rows


def build_diff_box(rows: list[tuple[str, str]], note: str = "") -> Gtk.Widget:
    """Build a scrolled, monospace list of diff rows; optional dim note below."""
    container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    for kind, text in rows:
        marker, suffix = marker_for(kind)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.add_css_class("diff-row")
        row.add_css_class(f"diff-row-{suffix}")
        mark = Gtk.Label(label=marker)
        mark.add_css_class("diff-marker")
        mark.add_css_class(f"diff-marker-{suffix}")
        mark.set_width_chars(1)
        content = Gtk.Label(label=text)
        content.add_css_class("diff-content")
        content.set_xalign(0)
        content.set_hexpand(True)
        content.set_ellipsize(Pango.EllipsizeMode.END)
        row.append(mark)
        row.append(content)
        box.append(row)
    scrolled = Gtk.ScrolledWindow()
    scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scrolled.set_max_content_height(300)
    scrolled.set_vexpand(True)
    scrolled.set_child(box)
    container.append(scrolled)
    if note:
        label = Gtk.Label(label=note)
        label.add_css_class("dim-label")
        label.set_wrap(True)
        label.set_xalign(0)
        container.append(label)
    return container
