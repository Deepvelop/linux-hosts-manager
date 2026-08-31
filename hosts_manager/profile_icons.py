"""Curated profile icons mapped to GTK/Adwaita symbolic names.

Uses the system icon theme (same idea as Font Awesome: a pickable set of
glyphs) so the app stays native on GNOME without shipping a web font.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProfileIcon:
    id: str
    label: str
    names: tuple[str, ...]  # preference order for IconTheme.has_icon


PROFILE_ICONS: tuple[ProfileIcon, ...] = (
    ProfileIcon("default", "Server", ("network-server-symbolic", "computer-symbolic")),
    ProfileIcon("code", "Code", ("code-symbolic", "applications-engineering-symbolic", "text-x-generic-symbolic")),
    ProfileIcon("stack", "Layers", ("view-paged-symbolic", "view-list-symbolic", "folder-symbolic")),
    ProfileIcon("globe", "Globe", ("network-workgroup-symbolic", "web-browser-symbolic", "network-wired-symbolic")),
    ProfileIcon("terminal", "Terminal", ("utilities-terminal-symbolic", "utilities-terminal")),
    ProfileIcon("database", "Database", ("drive-harddisk-symbolic", "drive-harddisk", "media-floppy-symbolic")),
    ProfileIcon("cloud", "Cloud", ("network-wireless-symbolic", "network-cellular-symbolic", "weather-overcast-symbolic")),
    ProfileIcon("api", "API", ("network-transmit-receive-symbolic", "network-transmit-symbolic")),
    ProfileIcon("web", "Web", ("web-browser-symbolic", "applications-internet")),
    ProfileIcon("folder", "Folder", ("folder-symbolic", "folder")),
    ProfileIcon("home", "Home", ("user-home-symbolic", "go-home-symbolic")),
    ProfileIcon("star", "Star", ("starred-symbolic", "emblem-favorite-symbolic")),
    ProfileIcon("wrench", "Tools", ("applications-system-symbolic", "emblem-system-symbolic")),
    ProfileIcon("shield", "Shield", ("security-high-symbolic", "channel-secure-symbolic")),
    ProfileIcon("lock", "Lock", ("system-lock-screen-symbolic", "changes-prevent-symbolic")),
    ProfileIcon("key", "Key", ("dialog-password-symbolic", "channel-secure-symbolic")),
    ProfileIcon("mail", "Mail", ("mail-unread-symbolic", "emblem-mail")),
    ProfileIcon("chat", "Chat", ("user-available-symbolic", "internet-group-chat")),
    ProfileIcon("users", "Users", ("system-users-symbolic", "avatar-default-symbolic")),
    ProfileIcon("box", "Package", ("package-x-generic-symbolic", "system-file-manager-symbolic")),
    ProfileIcon("bug", "Bug", ("applications-debugging-symbolic", "dialog-warning-symbolic")),
    ProfileIcon("rocket", "Launch", ("media-playback-start-symbolic", "go-jump-symbolic")),
    ProfileIcon("lab", "Lab", ("applications-science-symbolic", "emoji-science-symbolic")),
    ProfileIcon("game", "Game", ("applications-games-symbolic", "input-gaming-symbolic")),
    ProfileIcon("music", "Music", ("audio-x-generic-symbolic", "folder-music-symbolic")),
    ProfileIcon("image", "Image", ("image-x-generic-symbolic", "folder-pictures-symbolic")),
    ProfileIcon("doc", "Document", ("x-office-document-symbolic", "text-x-generic-symbolic")),
    ProfileIcon("settings", "Settings", ("preferences-system-symbolic", "emblem-system-symbolic")),
    ProfileIcon("clock", "Clock", ("preferences-system-time-symbolic", "alarm-symbolic")),
    ProfileIcon("map", "Map", ("mark-location-symbolic", "maps-symbolic")),
)

_BY_ID = {icon.id: icon for icon in PROFILE_ICONS}


def get_profile_icon(icon_id: str) -> ProfileIcon:
    return _BY_ID.get(icon_id, _BY_ID["default"])


def resolve_icon_name(icon_id: str, theme=None) -> str:
    """Return the first GTK icon name available in the theme."""
    profile_icon = get_profile_icon(icon_id)
    if theme is None:
        return profile_icon.names[0]
    for name in profile_icon.names:
        if theme.has_icon(name):
            return name
    return "network-server-symbolic"


def known_icon_ids() -> set[str]:
    return set(_BY_ID)
