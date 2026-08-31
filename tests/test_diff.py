from hosts_manager.diff import DiffChange, format_diff_text, managed_diff
from hosts_manager.parser import parse


def test_diff_added_and_removed_managed_entries():
    old = parse(
        "127.0.0.1 localhost\n"
        "# BEGIN Hosts Manager\n"
        "192.168.1.50 old-api.local\n"
        "# END Hosts Manager\n"
    )
    new_text = (
        "127.0.0.1 localhost\n"
        "# BEGIN Hosts Manager\n"
        "# Profile: Development\n"
        "127.0.0.1 api.local\n"
        "# END Hosts Manager\n"
    )
    changes = managed_diff(old, new_text)
    assert DiffChange(kind="add", ip="127.0.0.1", hostname="api.local") in changes
    assert DiffChange(kind="remove", ip="192.168.1.50", hostname="old-api.local") in changes


def test_diff_ignores_unmanaged_lines():
    old = parse("127.0.0.1 localhost\n# BEGIN Hosts Manager\n# END Hosts Manager\n")
    new_text = "10.0.0.1 other\n# BEGIN Hosts Manager\n# END Hosts Manager\n"
    assert managed_diff(old, new_text) == []


def test_diff_empty_when_managed_entries_unchanged():
    old = parse("# BEGIN Hosts Manager\n127.0.0.1 api.local\n# END Hosts Manager\n")
    new_text = "# BEGIN Hosts Manager\n# Profile: Development\n127.0.0.1 api.local\n# END Hosts Manager\n"
    assert managed_diff(old, new_text) == []


def test_format_diff_text_uses_plus_and_minus():
    changes = [
        DiffChange(kind="add", ip="127.0.0.1", hostname="api.local"),
        DiffChange(kind="remove", ip="192.168.1.50", hostname="old-api.local"),
    ]
    assert format_diff_text(changes) == "+ 127.0.0.1 api.local\n- 192.168.1.50 old-api.local"


def test_diff_detects_disable_toggle():
    old = parse("# BEGIN Hosts Manager\n127.0.0.1 app.local\n# END Hosts Manager\n")
    new_text = "# BEGIN Hosts Manager\n# 127.0.0.1 app.local\n# END Hosts Manager\n"
    changes = managed_diff(old, new_text)
    assert changes == [DiffChange(kind="disable", ip="127.0.0.1", hostname="app.local")]


def test_diff_detects_enable_toggle():
    old = parse("# BEGIN Hosts Manager\n# 127.0.0.1 app.local\n# END Hosts Manager\n")
    new_text = "# BEGIN Hosts Manager\n127.0.0.1 app.local\n# END Hosts Manager\n"
    changes = managed_diff(old, new_text)
    assert changes == [DiffChange(kind="enable", ip="127.0.0.1", hostname="app.local")]


def test_format_diff_text_includes_enable_disable():
    changes = [
        DiffChange(kind="disable", ip="127.0.0.1", hostname="app.local"),
        DiffChange(kind="enable", ip="10.0.0.1", hostname="api.local"),
    ]
    assert (
        format_diff_text(changes)
        == "~ 127.0.0.1 app.local (disabled)\n~ 10.0.0.1 api.local (enabled)"
    )

