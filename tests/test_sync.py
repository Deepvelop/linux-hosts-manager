from hosts_manager.models import HostEntry, Profile
from hosts_manager.parser import parse
from hosts_manager.sync import plan_sync


def _dev(*entries: HostEntry) -> Profile:
    return Profile(id="development", name="Development", icon="code", enabled=True, entries=list(entries))


def _staging(*entries: HostEntry) -> Profile:
    return Profile(id="staging", name="Staging", icon="stack", enabled=False, entries=list(entries))


def _doc(*lines: str) -> str:
    return "\n".join(lines) + "\n"


BLOCK = (
    "# BEGIN Hosts Manager",
    "# Profile: Development",
    "127.0.0.1 app.local  # Local app",
    "# END Hosts Manager",
)


def test_noop_when_file_matches_profiles():
    doc = parse(_doc(*BLOCK))
    profiles = [_dev(HostEntry(ip="127.0.0.1", hostname="app.local", comment="Local app"))]
    plan = plan_sync(doc, profiles)
    assert plan.changes == []


def test_block_ip_edit_updates_entry():
    doc = parse(_doc(*BLOCK[:2], "10.0.0.1 app.local  # Local app", "# END Hosts Manager"))
    profiles = [_dev(HostEntry(ip="127.0.0.1", hostname="app.local", comment="Local app"))]
    plan = plan_sync(doc, profiles)
    assert [c.kind for c in plan.changes] == ["update"]
    assert plan.changes[0].ip == "10.0.0.1"
    assert plan.profiles[0].entries[0].ip == "10.0.0.1"


def test_block_comment_edit_updates_entry():
    doc = parse(_doc(*BLOCK[:2], "127.0.0.1 app.local  # New note", "# END Hosts Manager"))
    profiles = [_dev(HostEntry(ip="127.0.0.1", hostname="app.local", comment="Local app"))]
    plan = plan_sync(doc, profiles)
    assert [c.kind for c in plan.changes] == ["update"]
    assert plan.profiles[0].entries[0].comment == "New note"


def test_block_disabled_line_disables_entry():
    doc = parse(_doc(*BLOCK[:2], "# 127.0.0.1 app.local  # Local app", "# END Hosts Manager"))
    profiles = [_dev(HostEntry(ip="127.0.0.1", hostname="app.local", comment="Local app"))]
    plan = plan_sync(doc, profiles)
    assert [c.kind for c in plan.changes] == ["update"]
    assert plan.profiles[0].entries[0].enabled is False


def test_block_line_added_creates_entry():
    doc = parse(
        _doc(
            "# BEGIN Hosts Manager",
            "# Profile: Development",
            "127.0.0.1 app.local  # Local app",
            "127.0.0.1 new.local",
            "# END Hosts Manager",
        )
    )
    profiles = [_dev(HostEntry(ip="127.0.0.1", hostname="app.local", comment="Local app"))]
    plan = plan_sync(doc, profiles)
    assert [c.kind for c in plan.changes] == ["add"]
    assert plan.changes[0].hostname == "new.local"
    assert [e.hostname for e in plan.profiles[0].entries] == ["app.local", "new.local"]


def test_block_line_removed_removes_entry():
    doc = parse(_doc("# BEGIN Hosts Manager", "# Profile: Development", "# END Hosts Manager"))
    profiles = [_dev(HostEntry(ip="127.0.0.1", hostname="app.local"))]
    plan = plan_sync(doc, profiles)
    assert [c.kind for c in plan.changes] == ["remove"]
    assert plan.changes[0].hostname == "app.local"
    assert plan.profiles[0].entries == []


def test_block_hostname_rename_adds_and_removes():
    doc = parse(
        _doc(
            "# BEGIN Hosts Manager",
            "# Profile: Development",
            "127.0.0.1 renamed.local",
            "# END Hosts Manager",
        )
    )
    profiles = [_dev(HostEntry(ip="127.0.0.1", hostname="app.local"))]
    plan = plan_sync(doc, profiles)
    assert {(c.kind, c.hostname) for c in plan.changes} == {
        ("add", "renamed.local"),
        ("remove", "app.local"),
    }


def test_unknown_section_creates_profile():
    doc = parse(
        _doc(
            "# BEGIN Hosts Manager",
            "# Profile: Handmade",
            "127.0.0.1 handmade.local",
            "# END Hosts Manager",
        )
    )
    plan = plan_sync(doc, [_dev()])
    created = next(p for p in plan.profiles if p.name == "Handmade")
    assert created.icon == "default"
    assert created.enabled is True
    assert [e.hostname for e in created.entries] == ["handmade.local"]
    assert [c.kind for c in plan.changes] == ["add"]


def test_profile_section_deleted_removes_block_entries():
    doc = parse(_doc("# BEGIN Hosts Manager", "# END Hosts Manager"))
    profiles = [
        _dev(HostEntry(ip="127.0.0.1", hostname="app.local")),
        _staging(HostEntry(ip="10.0.0.1", hostname="stg.local")),
    ]
    plan = plan_sync(doc, profiles)
    assert {c.kind for c in plan.changes} == {"remove"}
    assert {c.hostname for c in plan.changes} == {"app.local", "stg.local"}


def test_empty_profile_untouched():
    doc = parse(_doc(*BLOCK))
    profiles = [
        _dev(HostEntry(ip="127.0.0.1", hostname="app.local", comment="Local app")),
        _staging(),
    ]
    plan = plan_sync(doc, profiles)
    assert plan.changes == []
    assert any(p.name == "Staging" for p in plan.profiles)


def test_adopted_line_ip_edit_updates_entry():
    doc = parse("10.0.0.2 localhost\n" + _doc(*BLOCK))
    profiles = [
        _dev(
            HostEntry(ip="127.0.0.1", hostname="app.local", comment="Local app"),
            HostEntry(ip="127.0.0.1", hostname="localhost"),
        )
    ]
    plan = plan_sync(doc, profiles)
    assert any(
        c.kind == "update" and c.hostname == "localhost" and c.ip == "10.0.0.2"
        for c in plan.changes
    )
    localhost = next(e for e in plan.profiles[0].entries if e.hostname == "localhost")
    assert localhost.ip == "10.0.0.2"


def test_adopted_single_hostname_toggle_syncs_enabled():
    doc = parse("# 127.0.0.1 localhost\n" + _doc(*BLOCK))
    profiles = [
        _dev(
            HostEntry(ip="127.0.0.1", hostname="app.local", comment="Local app"),
            HostEntry(ip="127.0.0.1", hostname="localhost"),
        )
    ]
    plan = plan_sync(doc, profiles)
    localhost = next(e for e in plan.profiles[0].entries if e.hostname == "localhost")
    assert localhost.enabled is False
    assert any(c.hostname == "localhost" and c.kind == "update" for c in plan.changes)


def test_adopted_multi_hostname_enabled_not_synced():
    doc = parse("# ::1 ip6-localhost ip6-loopback\n" + _doc(*BLOCK))
    profiles = [
        _dev(
            HostEntry(ip="127.0.0.1", hostname="app.local", comment="Local app"),
            HostEntry(ip="::1", hostname="ip6-localhost"),
            HostEntry(ip="::1", hostname="ip6-loopback"),
        )
    ]
    plan = plan_sync(doc, profiles)
    for name in ("ip6-localhost", "ip6-loopback"):
        entry = next(e for e in plan.profiles[0].entries if e.hostname == name)
        assert entry.enabled is True  # app-controlled, not taken from the shared line


def test_plan_sync_does_not_mutate_input_profiles():
    doc = parse(_doc(*BLOCK[:2], "10.0.0.1 app.local", "# END Hosts Manager"))
    profiles = [_dev(HostEntry(ip="127.0.0.1", hostname="app.local", comment="Local app"))]
    plan_sync(doc, profiles)
    assert profiles[0].entries[0].ip == "127.0.0.1"
    assert profiles[0].entries[0].comment == "Local app"
