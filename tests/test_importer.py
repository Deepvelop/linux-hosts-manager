import pytest

from hosts_manager.importer import (
    IMPORT_PROFILE_ID,
    ImportPlan,
    build_imported_text,
    ensure_import_profile,
    plan_import,
    replan_with_edits,
)
from hosts_manager.models import HostEntry, Profile
from hosts_manager.parser import parse


def _profiles(*entries: HostEntry, enabled: bool = True) -> list[Profile]:
    return [
        Profile(
            id="development",
            name="Development",
            icon="code",
            enabled=enabled,
            entries=list(entries),
        )
    ]


def test_plan_collects_unmanaged_entries():
    doc = parse("127.0.0.1 localhost\n10.0.0.1 app.local  # App\n::1 ip6-localhost\n")
    plan = plan_import(doc, [])
    assert [(e.ip, e.hostname, e.enabled) for e in plan.entries] == [
        ("127.0.0.1", "localhost", True),
        ("10.0.0.1", "app.local", True),
        ("::1", "ip6-localhost", True),
    ]
    assert plan.source_lines == {1, 2, 3}
    assert plan.problems == []


def test_plan_imports_disabled_entries_as_disabled():
    doc = parse("# 127.0.0.1 old.local  # Old server\n")
    plan = plan_import(doc, [])
    assert plan.entries == [
        HostEntry(ip="127.0.0.1", hostname="old.local", enabled=False, comment="Old server")
    ]


def test_plan_ignores_managed_block_lines():
    doc = parse(
        "10.0.0.1 outside.local\n"
        "# BEGIN Hosts Manager\n"
        "10.0.0.2 inside.local\n"
        "# END Hosts Manager\n"
    )
    plan = plan_import(doc, [])
    assert [e.hostname for e in plan.entries] == ["outside.local"]
    assert plan.source_lines == {1}


def test_plan_flags_unknown_lines_with_fault():
    doc = parse("garbage here\n127.0.0.1 app.local\n")
    plan = plan_import(doc, [])
    assert len(plan.problems) == 1
    problem = plan.problems[0]
    assert problem.lineno == 1
    assert problem.raw == "garbage here"
    assert problem.fault == "Invalid IP address: garbage"
    assert [e.hostname for e in plan.entries] == ["app.local"]


def test_plan_flags_duplicate_hostname_on_later_line():
    doc = parse("127.0.0.1 app.local\n10.0.0.1 app.local\n")
    plan = plan_import(doc, [])
    assert [e.hostname for e in plan.entries] == ["app.local"]
    assert plan.source_lines == {1}
    assert len(plan.problems) == 1
    assert plan.problems[0].lineno == 2
    assert plan.problems[0].fault == "Duplicate hostname 'app.local' (also on line 1)"


def test_plan_flags_clash_with_enabled_profile():
    doc = parse("127.0.0.1 app.local\n")
    plan = plan_import(doc, _profiles(HostEntry(ip="127.0.0.1", hostname="app.local")))
    assert plan.entries == []
    assert len(plan.problems) == 1
    assert plan.problems[0].fault == "Hostname 'app.local' already in profile 'Development'"


def test_plan_ignores_disabled_profiles_for_clash():
    doc = parse("127.0.0.1 app.local\n")
    profiles = _profiles(HostEntry(ip="127.0.0.1", hostname="app.local"), enabled=False)
    plan = plan_import(doc, profiles)
    assert plan.problems == []
    assert [e.hostname for e in plan.entries] == ["app.local"]


def test_ensure_import_profile_creates_once_and_appends():
    profiles: list[Profile] = []
    profile, created = ensure_import_profile(
        profiles, [HostEntry(ip="127.0.0.1", hostname="one.local")]
    )
    assert created is True
    assert profile.id == IMPORT_PROFILE_ID
    assert profile.name == "Existing hosts"
    assert profile.icon == "home"
    assert profile.enabled is True
    assert len(profiles) == 1

    profile.enabled = False  # simulate the user disabling it
    same, created = ensure_import_profile(
        profiles, [HostEntry(ip="10.0.0.1", hostname="two.local")]
    )
    assert created is False
    assert same is profile
    assert len(profiles) == 1
    assert [e.hostname for e in same.entries] == ["one.local", "two.local"]
    assert same.enabled is True  # re-import forces enabled


def test_build_imported_text_moves_entries_into_block():
    doc = parse("127.0.0.1 localhost\n# keep comment\n10.0.0.1 app.local\n")
    plan = plan_import(doc, [])
    result = build_imported_text(doc, plan, [])
    assert "127.0.0.1 localhost" not in result.split("# BEGIN Hosts Manager", 1)[0]  # moved out of its original spot
    assert "# keep comment" in result
    assert "# BEGIN Hosts Manager" in result
    assert "# Profile: Existing hosts" in result
    assert "127.0.0.1 localhost" in result.split("# BEGIN Hosts Manager", 1)[1]
    assert "10.0.0.1 app.local" in result.split("# BEGIN Hosts Manager", 1)[1]


def test_build_imported_text_removes_deleted_lines():
    doc = parse("garbage here\n127.0.0.1 app.local\n")
    plan = plan_import(doc, [])
    plan.problems.clear()
    plan.delete_lines.add(1)
    result = build_imported_text(doc, plan, [])
    assert "garbage here" not in result
    assert "127.0.0.1 app.local" in result


def test_build_imported_text_refuses_unresolved_problems():
    doc = parse("garbage here\n")
    plan = plan_import(doc, [])
    with pytest.raises(ValueError):
        build_imported_text(doc, plan, [])


def test_replan_with_edits_applies_fixes():
    original = parse("garbage here\n127.0.0.1 app.local\n")
    plan = plan_import(original, [])
    new_plan = replan_with_edits(original, plan, {1: "127.0.0.1 fixed.local"}, [])
    assert [e.hostname for e in new_plan.entries] == ["fixed.local", "app.local"]
    assert new_plan.problems == []
    assert new_plan.source_lines == {1, 2}
    assert new_plan.keep_lines == set()


def test_replan_marks_comment_edits_as_kept():
    original = parse("garbage here\n127.0.0.1 app.local\n")
    plan = plan_import(original, [])
    new_plan = replan_with_edits(original, plan, {1: "# just a note"}, [])
    assert [e.hostname for e in new_plan.entries] == ["app.local"]
    assert new_plan.problems == []
    assert new_plan.keep_lines == {1}


def test_replan_respects_deleted_lines():
    original = parse("garbage here\n127.0.0.1 app.local\n")
    plan = plan_import(original, [])
    plan.problems.clear()
    plan.delete_lines.add(1)
    new_plan = replan_with_edits(original, plan, {}, [])
    assert [e.hostname for e in new_plan.entries] == ["app.local"]
    assert new_plan.problems == []
    assert new_plan.delete_lines == {1}


def test_replan_empty_edit_turns_line_blank_and_keeps_it():
    original = parse("garbage here\n127.0.0.1 app.local\n")
    plan = plan_import(original, [])
    new_plan = replan_with_edits(original, plan, {1: ""}, [])
    assert [e.hostname for e in new_plan.entries] == ["app.local"]
    assert new_plan.problems == []
    assert new_plan.keep_lines == {1}


def test_replan_rejects_multi_line_edit():
    original = parse("garbage here\n127.0.0.1 app.local\n")
    plan = plan_import(original, [])
    with pytest.raises(ValueError, match="at most one line"):
        replan_with_edits(
            original, plan, {1: "127.0.0.1 first.local\n10.0.0.1 second.local"}, []
        )
