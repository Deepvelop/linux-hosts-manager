#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gio, Gtk

from hosts_manager.paths import APP_ID, packaged_app_root
from hosts_manager.window import present_window


def _icon_search_paths() -> list[Path]:
    """Return icon theme roots for source and installed layouts."""
    # Source checkout: icons/hicolor/scalable/apps/<APP_ID>.svg
    paths: list[Path] = [ROOT / "icons" / "hicolor", ROOT / "icons"]

    app_root = packaged_app_root()
    if app_root is not None and app_root.resolve() != ROOT.resolve():
        # Installed: …/share/hosts-manager → …/share/icons/hicolor
        share = app_root.parent
        paths.extend([share / "icons" / "hicolor", share / "icons"])

    return paths


def _register_icons() -> None:
    display = Gdk.Display.get_default()
    theme = Gtk.IconTheme.get_for_display(display)
    for path in _icon_search_paths():
        if path.is_dir():
            theme.add_search_path(str(path))
    Gtk.Window.set_default_icon_name(APP_ID)


class HostsManagerApplication(Adw.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.connect("activate", self.on_activate)
        self.connect("startup", self.on_startup)

    def on_startup(self, _app) -> None:
        _register_icons()
        style = Adw.StyleManager.get_default()
        if hasattr(style, "set_accent_color"):
            style.set_accent_color(Adw.AccentColor.PURPLE)

    def on_activate(self, _app) -> None:
        _register_icons()
        win = self.props.active_window
        if win is None:
            win = present_window(self)
        win.present()


def main(argv: list[str] | None = None) -> int:
    app = HostsManagerApplication()
    return app.run(argv if argv is not None else sys.argv)


if __name__ == "__main__":
    sys.exit(main())
