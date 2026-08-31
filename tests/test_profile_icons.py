from hosts_manager.profile_icons import (
    PROFILE_ICONS,
    get_profile_icon,
    known_icon_ids,
    resolve_icon_name,
)


def test_catalog_has_defaults_used_by_seed_profiles():
    ids = known_icon_ids()
    assert {"default", "code", "stack", "globe"} <= ids


def test_get_profile_icon_falls_back_to_default():
    assert get_profile_icon("nope").id == "default"
    assert get_profile_icon("code").label == "Code"


def test_resolve_icon_name_without_theme_uses_first_candidate():
    assert resolve_icon_name("terminal") == "utilities-terminal-symbolic"


def test_each_icon_has_label_and_candidates():
    assert len(PROFILE_ICONS) >= 20
    for icon in PROFILE_ICONS:
        assert icon.id
        assert icon.label
        assert icon.names
