import pytest

from hosts_manager.merge import MergeConflict, merge_profiles
from hosts_manager.models import HostEntry, Profile
from hosts_manager.parser import parse


def _dev(*entries: HostEntry, enabled: bool = True) -> Profile:
    return Profile(id="development", name="Development", icon="code", enabled=enabled, entries=list(entries))


def _staging(*entries: HostEntry, enabled: bool = True) -> Profile:
    return Profile(id="staging", name="Staging", icon="stack", enabled=enabled, entries=list(entries))


def test_appends_managed_block_when_markers_missing():
    original = "127.0.0.1\tlocalhost\n# keep me\n"
    profiles = [
        _dev(HostEntry(ip="127.0.0.1", hostname="app.local", comment="Local application"))
    ]
    result = merge_profiles(parse(original), profiles)
    assert result.startswith(original)
    assert "# BEGIN Hosts Manager" in result
    assert "127.0.0.1 app.local  # Local application" in result
    assert result.endswith("# END Hosts Manager\n")


def test_replaces_existing_managed_block_only():
    original = (
        "127.0.0.1\tlocalhost\n"
        "# BEGIN Hosts Manager\n"
        "10.0.0.1 stale.local\n"
        "# END Hosts Manager\n"
        "# after\n"
    )
    profiles = [_dev(HostEntry(ip="127.0.0.1", hostname="app.local"))]
    result = merge_profiles(parse(original), profiles)
    assert "127.0.0.1\tlocalhost" in result
    assert "# after" in result
    assert "stale.local" not in result
    assert "127.0.0.1 app.local" in result


def test_writes_disabled_entries_as_comments():
    profiles = [
        _dev(
            HostEntry(ip="127.0.0.1", hostname="old.app.local", enabled=False, comment="Old server (disabled)")
        )
    ]
    result = merge_profiles(parse(""), profiles)
    assert "# 127.0.0.1 old.app.local  # Old server (disabled)" in result


def test_includes_only_enabled_profiles():
    profiles = [
        _dev(HostEntry(ip="127.0.0.1", hostname="dev.local")),
        _staging(HostEntry(ip="10.0.0.1", hostname="stg.local"), enabled=False),
    ]
    result = merge_profiles(parse(""), profiles)
    assert "dev.local" in result
    assert "stg.local" not in result


def test_conflict_when_two_enabled_profiles_share_hostname():
    profiles = [
        _dev(HostEntry(ip="127.0.0.1", hostname="api.local")),
        _staging(HostEntry(ip="192.168.1.10", hostname="api.local")),
    ]
    with pytest.raises(MergeConflict) as exc:
        merge_profiles(parse("127.0.0.1 localhost\n"), profiles)
    assert "api.local" in str(exc.value)


def test_same_hostname_allowed_if_one_profile_disabled():
    profiles = [
        _dev(HostEntry(ip="127.0.0.1", hostname="api.local")),
        _staging(HostEntry(ip="192.168.1.10", hostname="api.local"), enabled=False),
    ]
    result = merge_profiles(parse("127.0.0.1 localhost\n"), profiles)
    assert "127.0.0.1 api.local" in result
    assert "192.168.1.10" not in result


def test_adopts_unmanaged_line_in_place():
    original = "127.0.0.1 localhost\n# keep me\n"
    profiles = [_dev(HostEntry(ip="127.0.0.1", hostname="localhost"))]
    result = merge_profiles(parse(original), profiles)
    assert result.startswith("127.0.0.1 localhost\n# keep me\n")
    assert "# BEGIN Hosts Manager" in result
    assert "localhost" not in result.split("# BEGIN Hosts Manager", 1)[1]


def test_adopted_line_disable_rewrites_in_place():
    original = "127.0.0.1 localhost\n"
    profiles = [_dev(HostEntry(ip="127.0.0.1", hostname="localhost", enabled=False))]
    result = merge_profiles(parse(original), profiles)
    assert result.startswith("# 127.0.0.1 localhost\n")


def test_adopted_line_ip_change_rewrites():
    original = "127.0.0.1 localhost\n"
    profiles = [_dev(HostEntry(ip="10.0.0.1", hostname="localhost"))]
    result = merge_profiles(parse(original), profiles)
    assert result.startswith("10.0.0.1 localhost\n")


def test_multi_hostname_line_disabled_when_any_adopted_hostname_disabled():
    original = "::1 ip6-localhost ip6-loopback\n"
    profiles = [
        _dev(
            HostEntry(ip="::1", hostname="ip6-localhost", enabled=True),
            HostEntry(ip="::1", hostname="ip6-loopback", enabled=False),
        )
    ]
    result = merge_profiles(parse(original), profiles)
    assert result.startswith("# ::1 ip6-localhost ip6-loopback\n")


def test_multi_hostname_line_enabled_when_all_adopted_enabled():
    original = "::1 ip6-localhost ip6-loopback\n"
    profiles = [
        _dev(
            HostEntry(ip="::1", hostname="ip6-localhost", enabled=True),
            HostEntry(ip="::1", hostname="ip6-loopback", enabled=True),
        )
    ]
    result = merge_profiles(parse(original), profiles)
    assert result.startswith("::1 ip6-localhost ip6-loopback\n")


def test_shared_line_conflicting_settings_raise():
    original = "::1 ip6-localhost ip6-loopback\n"
    profiles = [
        _dev(
            HostEntry(ip="::1", hostname="ip6-localhost", comment="a"),
            HostEntry(ip="::2", hostname="ip6-loopback"),
        )
    ]
    with pytest.raises(MergeConflict):
        merge_profiles(parse(original), profiles)


def test_foreign_hostname_no_longer_conflicts():
    original = "10.0.0.1 stranger.local\n"
    profiles = [_dev(HostEntry(ip="127.0.0.1", hostname="app.local"))]
    result = merge_profiles(parse(original), profiles)
    assert "10.0.0.1 stranger.local" in result


def test_entry_without_outside_line_still_goes_into_block():
    original = ""
    profiles = [_dev(HostEntry(ip="127.0.0.1", hostname="app.local"))]
    result = merge_profiles(parse(original), profiles)
    assert "127.0.0.1 app.local" in result.split("# BEGIN Hosts Manager", 1)[1]


def test_does_not_rewrite_unmanaged_unknown_or_comments():
    original = "127.0.0.1\tlocalhost\n# custom comment\ngarbage line\n"
    result = merge_profiles(
        parse(original),
        [_dev(HostEntry(ip="127.0.0.1", hostname="app.local"))],
    )
    before, _, _ = result.partition("# BEGIN Hosts Manager")
    assert before == original


def test_allows_dual_stack_hostname_across_families():
    profiles = [
        _dev(HostEntry(ip="127.0.0.1", hostname="findeep.local")),
        _staging(HostEntry(ip="::1", hostname="findeep.local")),
    ]
    result = merge_profiles(parse(""), profiles)
    assert "127.0.0.1 findeep.local" in result
    assert "::1 findeep.local" in result


def test_still_rejects_same_family_duplicates():
    profiles = [
        _dev(HostEntry(ip="127.0.0.1", hostname="findeep.local")),
        _staging(HostEntry(ip="10.0.0.1", hostname="findeep.local")),
    ]
    with pytest.raises(MergeConflict):
        merge_profiles(parse(""), profiles)


def test_rejects_third_entry_for_hostname():
    profiles = [
        _dev(HostEntry(ip="127.0.0.1", hostname="findeep.local")),
        _staging(HostEntry(ip="::1", hostname="findeep.local")),
        _staging(HostEntry(ip="10.0.0.1", hostname="findeep.local")),
    ]
    with pytest.raises(MergeConflict):
        merge_profiles(parse(""), profiles)


def test_disabled_profile_does_not_conflict_on_family():
    profiles = [
        _dev(HostEntry(ip="127.0.0.1", hostname="findeep.local")),
        _staging(HostEntry(ip="10.0.0.1", hostname="findeep.local"), enabled=False),
    ]
    result = merge_profiles(parse(""), profiles)
    assert "127.0.0.1 findeep.local" in result
