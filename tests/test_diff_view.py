from hosts_manager.diff import DiffChange
from hosts_manager.diff_view import marker_for, rows_from_changes, rows_from_sync_changes
from hosts_manager.sync import SyncChange


def test_marker_for_kinds():
    assert marker_for("add") == ("+", "add")
    assert marker_for("remove") == ("−", "remove")
    assert marker_for("change") == ("~", "change")


def test_rows_from_changes():
    changes = [
        DiffChange(kind="add", ip="127.0.0.1", hostname="foo.local"),
        DiffChange(kind="remove", ip="10.0.0.1", hostname="bar.local"),
        DiffChange(kind="enable", ip="::1", hostname="baz.local"),
        DiffChange(kind="disable", ip="::1", hostname="qux.local"),
    ]
    assert rows_from_changes(changes) == [
        ("add", "127.0.0.1 foo.local"),
        ("remove", "10.0.0.1 bar.local"),
        ("change", "::1 baz.local (enabled)"),
        ("change", "::1 qux.local (disabled)"),
    ]


def test_rows_from_sync_changes():
    changes = [
        SyncChange(profile="Development", kind="add", ip="127.0.0.1", hostname="foo.local"),
        SyncChange(profile="Development", kind="update", ip="10.0.0.1", hostname="bar.local"),
        SyncChange(profile="Development", kind="remove", ip="192.168.0.1", hostname="baz.local"),
    ]
    assert rows_from_sync_changes(changes) == [
        ("add", "127.0.0.1 foo.local"),
        ("change", "10.0.0.1 bar.local"),
        ("remove", "192.168.0.1 baz.local"),
    ]
