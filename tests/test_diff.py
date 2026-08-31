from hosts_manager.diff import DiffChange, adopted_diff, format_diff_text, managed_diff
from hosts_manager.merge import adopted_map
from hosts_manager.models import HostEntry, Profile
from hosts_manager.parser import parse


def _adopted(*entries: HostEntry) -> dict:
    return adopted_map([Profile(id="p", name="P", icon="default", enabled=True, entries=list(entries))])


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


def test_diff_keeps_both_families_of_dual_hostname():
    old = parse(
        "# BEGIN Hosts Manager\n127.0.0.1 findeep.local\n::1 findeep.local\n# END Hosts Manager\n"
    )
    new_text = (
        "# BEGIN Hosts Manager\n# 127.0.0.1 findeep.local\n::1 findeep.local\n# END Hosts Manager\n"
    )
    changes = managed_diff(old, new_text)
    assert changes == [DiffChange(kind="disable", ip="127.0.0.1", hostname="findeep.local")]


def test_diff_adds_second_family_independently():
    old = parse("# BEGIN Hosts Manager\n127.0.0.1 findeep.local\n# END Hosts Manager\n")
    new_text = (
        "# BEGIN Hosts Manager\n127.0.0.1 findeep.local\n::1 findeep.local\n# END Hosts Manager\n"
    )
    changes = managed_diff(old, new_text)
    assert changes == [DiffChange(kind="add", ip="::1", hostname="findeep.local")]


def test_diff_removes_one_family_only():
    old = parse(
        "# BEGIN Hosts Manager\n127.0.0.1 findeep.local\n::1 findeep.local\n# END Hosts Manager\n"
    )
    new_text = "# BEGIN Hosts Manager\n127.0.0.1 findeep.local\n# END Hosts Manager\n"
    changes = managed_diff(old, new_text)
    assert changes == [DiffChange(kind="remove", ip="::1", hostname="findeep.local")]


def test_adopted_diff_detects_disable():
    old = parse("127.0.0.1 localhost\n")
    new_text = "# 127.0.0.1 localhost\n"
    adopted = _adopted(HostEntry(ip="127.0.0.1", hostname="localhost", enabled=False))
    assert adopted_diff(old, new_text, adopted) == [
        DiffChange(kind="disable", ip="127.0.0.1", hostname="localhost")
    ]


def test_adopted_diff_detects_enable():
    old = parse("# 127.0.0.1 localhost\n")
    new_text = "127.0.0.1 localhost\n"
    adopted = _adopted(HostEntry(ip="127.0.0.1", hostname="localhost", enabled=True))
    assert adopted_diff(old, new_text, adopted) == [
        DiffChange(kind="enable", ip="127.0.0.1", hostname="localhost")
    ]


def test_adopted_diff_detects_ip_change():
    old = parse("127.0.0.1 localhost\n")
    new_text = "10.0.0.1 localhost\n"
    adopted = _adopted(HostEntry(ip="10.0.0.1", hostname="localhost"))
    assert adopted_diff(old, new_text, adopted) == [
        DiffChange(kind="remove", ip="127.0.0.1", hostname="localhost"),
        DiffChange(kind="add", ip="10.0.0.1", hostname="localhost"),
    ]


def test_adopted_diff_empty_when_unchanged():
    old = parse("127.0.0.1 localhost\n")
    adopted = _adopted(HostEntry(ip="127.0.0.1", hostname="localhost"))
    assert adopted_diff(old, "127.0.0.1 localhost\n", adopted) == []


def test_adopted_diff_ignores_foreign_lines():
    old = parse("10.0.0.1 stranger.local\n")
    new_text = "10.0.0.2 stranger.local\n"
    adopted = _adopted(HostEntry(ip="127.0.0.1", hostname="localhost"))
    assert adopted_diff(old, new_text, adopted) == []

