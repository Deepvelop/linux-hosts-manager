#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from subprocess import CalledProcessError

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Pango", "1.0")

from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango

from hosts_manager import __version__
from hosts_manager.diff import adopted_diff, managed_diff
from hosts_manager.diff_view import build_diff_box, rows_from_changes, rows_from_sync_changes
from hosts_manager.import_dialog import ImportDialog
from hosts_manager.importer import ImportPlan, build_imported_text, ensure_import_profile, plan_import
from hosts_manager.merge import MergeConflict, adopted_map, merge_profiles
from hosts_manager.models import HostEntry, HostsDocument, Profile
from hosts_manager.parser import parse
from hosts_manager.polkit import WriteSessionError, apply_hosts, can_apply, ensure_authorized, skip_polkit
from hosts_manager.profile_icons import PROFILE_ICONS, known_icon_ids, resolve_icon_name
from hosts_manager.profiles import ProfileStore
from hosts_manager.settings import AppSettings, SettingsStore
from hosts_manager.sync import SyncPlan, plan_sync
from hosts_manager.validate import ValidationError, ip_family, validate_entry
from hosts_manager.writer import WriteError, backup_dir_from_env, hosts_path_from_env

from hosts_manager.paths import APP_ID


def _load_css() -> None:
    # Drive libadwaita suggested-action / accent widgets to purple (matches app icon).
    style = Adw.StyleManager.get_default()
    if hasattr(style, "set_accent_color"):
        style.set_accent_color(Adw.AccentColor.PURPLE)

    provider = Gtk.CssProvider()
    css_path = Path(__file__).with_name("style.css")
    provider.load_from_path(str(css_path))
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(),
        provider,
        Gtk.STYLE_PROVIDER_PRIORITY_USER,
    )


def _icon(name: str, size: int = 16) -> Gtk.Image:
    # Prefer CSS -gtk-icon-size over set_pixel_size to avoid GtkImage baseline warnings.
    theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
    icon_name = resolve_icon_name(name, theme) if name in known_icon_ids() else name
    image = Gtk.Image.new_from_icon_name(icon_name)
    image.add_css_class(f"icon-size-{size}")
    image.set_valign(Gtk.Align.CENTER)
    image.set_halign(Gtk.Align.CENTER)
    return image


def _brand_icon(pixel_size: int = 22) -> Gtk.Image:
    image = Gtk.Image.new_from_icon_name(APP_ID)
    image.add_css_class(f"icon-size-{pixel_size}")
    image.add_css_class("sidebar-brand-icon")
    image.set_valign(Gtk.Align.CENTER)
    image.set_halign(Gtk.Align.CENTER)
    return image


def _icon_button(name: str, *, tooltip: str = "", size: int = 16) -> Gtk.Button:
    button = Gtk.Button()
    button.set_child(_icon(name, size))
    if tooltip:
        button.set_tooltip_text(tooltip)
    button.add_css_class("flat")
    return button


class HostsManagerWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.set_title("Hosts Manager")
        self.set_icon_name(APP_ID)
        self.set_default_size(1020, 680)
        _load_css()

        self.store = ProfileStore()
        self.settings_store = SettingsStore()
        self.settings: AppSettings = self.settings_store.load()
        self.profiles: list[Profile] = self.store.load()
        self.selected_index = 0
        self.search_text = ""
        self._pending_text: str | None = None
        self._pending_toast = "Hosts file updated"
        self._suppress_switch = False
        self._authorized = skip_polkit()
        self.apply_btn: Gtk.Button | None = None

        self._build_actions()
        overlay = Adw.ToastOverlay()
        overlay.set_child(self._build_split())
        self.set_content(overlay)
        self.toast_overlay = overlay

        if not self.store.path.exists():
            self.store.save(self.profiles)

        self._refresh_profiles()
        self._refresh_hosts()
        self._refresh_status()
        self._refresh_sync_status()
        self._hosts_monitor: Gio.FileMonitor | None = None
        self._import_open = False
        self._sync_open = False
        self._import_document: HostsDocument | None = None
        self._import_digest: str | None = None
        self._last_written_hash: str | None = None
        self._monitor_serial = 0
        self._start_hosts_monitor()
        GLib.idle_add(self._on_hosts_scan)

    def _build_actions(self) -> None:
        for name, callback in (
            ("add-host", self._on_add_host),
            ("toggle-profile", self._on_toggle_profile),
            ("rename-profile", self._on_rename_profile),
            ("delete-profile", self._on_delete_profile),
            ("add-profile", self._on_add_profile),
            ("change-icon", self._on_change_icon),
            ("about", self._on_about),
            ("settings", self._on_settings),
            ("apply", lambda *_: self._on_apply_clicked(None)),
            ("import-hosts", lambda *_: self._maybe_present_import(force=True)),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)

    def _build_split(self) -> Adw.NavigationSplitView:
        split = Adw.NavigationSplitView()
        split.set_min_sidebar_width(250)
        split.set_max_sidebar_width(300)
        sidebar_page = Adw.NavigationPage(title="Hosts Manager")
        sidebar_page.add_css_class("sidebar")
        sidebar_page.add_css_class("hosts-sidebar-page")
        sidebar_page.set_child(self._build_sidebar())
        content_page = Adw.NavigationPage(title="Hosts")
        content_page.set_child(self._build_content())
        split.set_sidebar(sidebar_page)
        split.set_content(content_page)
        return split

    def _build_sidebar(self) -> Gtk.Widget:
        shell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        shell.add_css_class("sidebar-shell")

        header = Adw.HeaderBar()
        header.add_css_class("sidebar-header")
        header.set_show_start_title_buttons(False)
        header.set_show_end_title_buttons(False)
        brand = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        brand.add_css_class("sidebar-brand")
        brand.append(_brand_icon(26))
        title = Gtk.Label(label="Hosts Manager")
        title.set_xalign(0)
        brand.append(title)
        header.set_title_widget(brand)
        shell.append(header)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        body.add_css_class("sidebar-body")
        body.set_vexpand(True)
        body.set_margin_start(10)
        body.set_margin_end(10)
        body.set_margin_top(16)

        section = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        label = Gtk.Label(label="PROFILES")
        label.add_css_class("section-label")
        label.set_hexpand(True)
        label.set_xalign(0)
        add_btn = _icon_button("list-add-symbolic", tooltip="Add profile")
        add_btn.connect("clicked", self._on_add_profile)
        section.append(label)
        section.append(add_btn)
        body.append(section)

        scrolled = Gtk.ScrolledWindow()
        scrolled.add_css_class("sidebar-scroll")
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        self.profile_list = Gtk.ListBox()
        self.profile_list.add_css_class("profile-list")
        self.profile_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.profile_list.connect("row-selected", self._on_profile_row_selected)
        scrolled.set_child(self.profile_list)
        body.append(scrolled)

        tools = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        settings_btn = _icon_button("emblem-system-symbolic", tooltip="Settings")
        settings_btn.connect("clicked", self._on_settings)
        about_btn = _icon_button("help-about-symbolic", tooltip="About")
        about_btn.connect("clicked", self._on_about)
        tools.append(settings_btn)
        tools.append(about_btn)
        body.append(tools)

        footer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        footer.add_css_class("sidebar-footer")

        self.status_badge = Gtk.Button()
        self.status_badge.add_css_class("flat")
        self.status_badge.add_css_class("status-badge")
        self.status_badge.add_css_class("status-badge-ok")
        self.status_badge.set_halign(Gtk.Align.FILL)
        self.status_badge.set_hexpand(True)
        self.status_badge.connect("clicked", self._on_status_badge_clicked)

        badge_inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        badge_inner.set_halign(Gtk.Align.FILL)
        badge_inner.set_hexpand(True)

        status_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.status_icon = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
        self.status_icon.add_css_class("icon-size-16")
        self.status_icon.set_valign(Gtk.Align.CENTER)
        self.status_icon.set_halign(Gtk.Align.CENTER)
        self.status_label = Gtk.Label(label="Checking hosts file…")
        self.status_label.set_xalign(0)
        self.status_label.set_hexpand(True)
        status_row.append(self.status_icon)
        status_row.append(self.status_label)

        path_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.path_icon = Gtk.Image.new_from_icon_name("security-high-symbolic")
        self.path_icon.add_css_class("icon-size-16")
        self.path_icon.set_valign(Gtk.Align.CENTER)
        self.path_icon.set_halign(Gtk.Align.CENTER)
        self.path_label = Gtk.Label(label=str(hosts_path_from_env()))
        self.path_label.add_css_class("sidebar-path")
        self.path_label.set_xalign(0)
        self.path_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        self.path_label.set_hexpand(True)
        path_row.append(self.path_icon)
        path_row.append(self.path_label)

        badge_inner.append(status_row)
        badge_inner.append(path_row)
        self.status_badge.set_child(badge_inner)
        footer.append(self.status_badge)
        body.append(footer)

        shell.append(body)
        return shell

    def _build_content(self) -> Gtk.Widget:
        view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        # Keep chrome on the right so the profile title stays left-aligned.
        header.set_show_start_title_buttons(False)
        header.set_show_end_title_buttons(True)
        header.set_title_widget(Gtk.Box())

        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        title_box.set_halign(Gtk.Align.START)
        title_box.set_valign(Gtk.Align.CENTER)
        title_box.add_css_class("profile-header")
        self.profile_title = Gtk.Label(label="Development")
        self.profile_title.add_css_class("title")
        self.profile_title.set_xalign(0)
        self.profile_title.set_halign(Gtk.Align.START)

        self.active_badge = Gtk.Button()
        self.active_badge.add_css_class("flat")
        self.active_badge.add_css_class("active-badge-button")
        self.active_badge.set_valign(Gtk.Align.CENTER)
        self.active_badge.set_tooltip_text(
            "Enable or disable this profile in the hosts file (asks for admin if needed)"
        )
        self.active_label = Gtk.Label(label="Active")
        self.active_label.add_css_class("active-pill")
        self.active_badge.set_child(self.active_label)
        self.active_badge.connect("clicked", self._on_active_badge_clicked)

        title_box.append(self.profile_title)
        title_box.append(self.active_badge)
        header.pack_start(title_box)

        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Search")
        self.search_entry.connect("search-changed", self._on_search_changed)
        header.pack_end(self._build_menu_button())
        header.pack_end(self.search_entry)
        view.add_top_bar(header)

        list_shell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        list_shell.set_vexpand(True)
        list_shell.add_css_class("hosts-table")

        header_row = self._build_hosts_table_header()
        list_shell.append(header_row)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        self.hosts_list = Gtk.ListBox()
        self.hosts_list.add_css_class("host-list")
        self.hosts_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.hosts_list.set_activate_on_single_click(True)
        self.hosts_list.connect("row-activated", self._on_host_row_activated)
        scrolled.set_child(self.hosts_list)
        list_shell.append(scrolled)

        view.set_content(list_shell)

        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        bar.add_css_class("apply-bar")

        add_btn = Gtk.Button()
        add_btn.add_css_class("flat")
        add_btn.add_css_class("add-host-button")
        add_btn.set_valign(Gtk.Align.CENTER)
        add_btn.set_halign(Gtk.Align.START)
        add_inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        add_inner.append(_icon("list-add-symbolic", 16))
        add_label = Gtk.Label(label="Add host")
        add_inner.append(add_label)
        add_btn.set_child(add_inner)
        add_btn.connect("clicked", self._on_add_host)
        bar.append(add_btn)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        bar.append(spacer)

        self.saved_label = Gtk.Label(label="Checking sync…")
        self.saved_label.add_css_class("sync-status")
        self.saved_label.set_valign(Gtk.Align.CENTER)
        bar.append(self.saved_label)

        self.apply_btn = Gtk.Button(label="Save")
        self.apply_btn.add_css_class("apply-button")
        self.apply_btn.set_valign(Gtk.Align.CENTER)
        self.apply_btn.connect("clicked", self._on_apply_clicked)
        bar.append(self.apply_btn)
        self._sync_apply_button()

        view.add_bottom_bar(bar)
        return view

    def _build_menu_button(self) -> Gtk.MenuButton:
        self.menu_button = Gtk.MenuButton()
        self.menu_button.set_icon_name("view-more-symbolic")
        self.menu_button.set_tooltip_text("Profile options")
        self._rebuild_menu()
        return self.menu_button

    def _rebuild_menu(self) -> None:
        menu = Gio.Menu()
        menu.append("Import Existing Hosts", "win.import-hosts")
        menu.append("Add Host", "win.add-host")
        profile = self._selected_profile()
        if profile and profile.enabled:
            menu.append("Disable Profile", "win.toggle-profile")
        else:
            menu.append("Enable Profile", "win.toggle-profile")
        menu.append("Change Icon", "win.change-icon")
        menu.append("Rename Profile", "win.rename-profile")
        menu.append("Delete Profile", "win.delete-profile")
        self.menu_button.set_menu_model(menu)

    def _selected_profile(self) -> Profile | None:
        if 0 <= self.selected_index < len(self.profiles):
            return self.profiles[self.selected_index]
        return None

    def _persist(self) -> None:
        self.store.save(self.profiles)
        self._refresh_sync_status()

    def _maybe_autosave(self, *, success_toast: str = "Hosts file updated") -> bool:
        if not self.settings.auto_save:
            return True
        return self._write_hosts(confirm=False, success_toast=success_toast)

    def _sync_apply_button(self, *, has_pending: bool | None = None) -> None:
        if self.apply_btn is None:
            return
        auto = self.settings.auto_save
        self.apply_btn.set_visible(not auto)
        if auto:
            return
        pending = False if has_pending is None else has_pending
        self.apply_btn.set_sensitive(pending)
        self.apply_btn.set_tooltip_text(
            "Write pending changes to the hosts file" if pending else "Nothing to save"
        )

    def _refresh_sync_status(self) -> None:
        path = hosts_path_from_env()
        try:
            current = path.read_text(encoding="utf-8")
        except OSError:
            self.saved_label.set_text("Cannot read hosts file")
            self._sync_apply_button(has_pending=False)
            return
        document = parse(current)
        adopted = adopted_map(self.profiles)
        try:
            new_text = merge_profiles(document, self.profiles)
        except MergeConflict as exc:
            self.saved_label.set_text(f"Conflict: {exc.hostnames[0]}")
            self._sync_apply_button(has_pending=False)
            return
        changes = managed_diff(document, new_text) + adopted_diff(document, new_text, adopted)
        if changes:
            self.saved_label.set_text(f"{len(changes)} unapplied change{'s' if len(changes) != 1 else ''}")
        elif self.settings.auto_save:
            self.saved_label.set_text("Auto-save on · in sync")
        else:
            self.saved_label.set_text("In sync with hosts file")
        self._sync_apply_button(has_pending=bool(changes))

    def _set_saved_now(self) -> None:
        # Kept for compatibility; sync status is the source of truth.
        self._refresh_sync_status()
        self.saved_at = datetime.now(timezone.utc)

    def _refresh_profiles(self) -> None:
        self.profile_list.remove_all()
        for index, profile in enumerate(self.profiles):
            row = Gtk.ListBoxRow()
            row.add_css_class("profile-row")
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            box.set_margin_start(4)
            box.set_margin_end(4)
            box.set_margin_top(6)
            box.set_margin_bottom(6)
            box.append(_icon(profile.icon))
            name = Gtk.Label(label=profile.name)
            name.set_xalign(0)
            name.set_hexpand(True)
            box.append(name)
            if profile.enabled:
                dot = Gtk.Label(label="●")
                dot.add_css_class("enabled-dot")
                dot.set_valign(Gtk.Align.CENTER)
                box.append(dot)
            row.set_child(box)
            row.index = index  # type: ignore[attr-defined]
            self.profile_list.append(row)
        row = self.profile_list.get_row_at_index(self.selected_index)
        if row:
            self.profile_list.select_row(row)
        self._rebuild_menu()

    def _refresh_hosts(self) -> None:
        self.hosts_list.remove_all()
        profile = self._selected_profile()
        if profile is None:
            return
        self.profile_title.set_text(profile.name)
        self._sync_active_label(profile.enabled)
        query = self.search_text.lower().strip()
        for index, entry in enumerate(profile.entries):
            haystack = f"{entry.hostname} {entry.ip} {entry.comment}".lower()
            if query and query not in haystack:
                continue
            self.hosts_list.append(self._host_row(profile, index, entry))

    def _sync_active_label(self, enabled: bool) -> None:
        self.active_label.set_text("Active" if enabled else "Inactive")
        self.active_label.remove_css_class("active-pill")
        self.active_label.remove_css_class("inactive-pill")
        self.active_label.add_css_class("active-pill" if enabled else "inactive-pill")

    def _build_hosts_table_header(self) -> Gtk.Widget:
        grid = self._hosts_table_grid()
        grid.add_css_class("hosts-table-header")
        grid.set_margin_top(14)
        grid.set_margin_bottom(4)

        spacer = Gtk.Label()
        spacer.add_css_class("col-toggle")
        hostname = Gtk.Label(label="Hostname")
        hostname.add_css_class("col-hostname")
        hostname.add_css_class("table-header-label")
        hostname.set_xalign(0)
        ip = Gtk.Label(label="IP")
        ip.add_css_class("col-ip")
        ip.add_css_class("table-header-label")
        ip.set_xalign(0)
        comment = Gtk.Label(label="Description")
        comment.add_css_class("col-comment")
        comment.add_css_class("table-header-label")
        comment.set_xalign(0)
        comment.set_hexpand(True)
        trailing = Gtk.Label()
        trailing.add_css_class("col-action")

        grid.attach(spacer, 0, 0, 1, 1)
        grid.attach(hostname, 1, 0, 1, 1)
        grid.attach(ip, 2, 0, 1, 1)
        grid.attach(comment, 3, 0, 1, 1)
        grid.attach(trailing, 4, 0, 1, 1)
        return grid

    def _hosts_table_grid(self) -> Gtk.Grid:
        grid = Gtk.Grid()
        grid.add_css_class("hosts-table-row")
        grid.set_column_spacing(20)
        return grid

    def _host_row(self, profile: Profile, index: int, entry: HostEntry) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        row.set_activatable(True)
        row.entry_index = index  # type: ignore[attr-defined]
        if not entry.enabled:
            row.add_css_class("disabled-entry")

        grid = self._hosts_table_grid()
        grid.set_margin_top(2)
        grid.set_margin_bottom(2)

        toggle_box = Gtk.Box()
        toggle_box.add_css_class("col-toggle")
        toggle_box.set_halign(Gtk.Align.START)
        toggle_box.set_valign(Gtk.Align.CENTER)
        switch = Gtk.Switch()
        switch.set_active(entry.enabled)
        switch.set_valign(Gtk.Align.CENTER)
        switch.set_halign(Gtk.Align.START)
        switch.connect("notify::active", self._on_entry_toggled, profile, index)
        switch.set_focus_on_click(True)
        toggle_box.append(switch)

        hostname = Gtk.Label(label=entry.hostname)
        hostname.add_css_class("hostname-label")
        hostname.add_css_class("col-hostname")
        hostname.set_xalign(0)
        hostname.set_halign(Gtk.Align.FILL)
        hostname.set_ellipsize(Pango.EllipsizeMode.END)
        if not entry.enabled:
            attrs = Pango.AttrList()
            attrs.insert(Pango.attr_strikethrough_new(True))
            hostname.set_attributes(attrs)

        ip = Gtk.Label(label=entry.ip)
        ip.add_css_class("ip-label")
        ip.add_css_class("col-ip")
        ip.set_xalign(0)
        ip.set_halign(Gtk.Align.FILL)
        ip.set_ellipsize(Pango.EllipsizeMode.END)

        comment = Gtk.Label(label=entry.comment or "—")
        comment.add_css_class("comment-label")
        comment.add_css_class("col-comment")
        comment.set_xalign(0)
        comment.set_hexpand(True)
        comment.set_halign(Gtk.Align.FILL)
        comment.set_ellipsize(Pango.EllipsizeMode.END)
        if not entry.enabled:
            comment.add_css_class("comment-italic")

        action = Gtk.Box()
        action.add_css_class("col-action")
        action.set_halign(Gtk.Align.END)
        edit = _icon_button("go-next-symbolic", tooltip="Edit host")
        edit.connect("clicked", lambda *_: self._open_entry_dialog(profile, index, entry))
        action.append(edit)

        grid.attach(toggle_box, 0, 0, 1, 1)
        grid.attach(hostname, 1, 0, 1, 1)
        grid.attach(ip, 2, 0, 1, 1)
        grid.attach(comment, 3, 0, 1, 1)
        grid.attach(action, 4, 0, 1, 1)
        row.set_child(grid)
        return row

    def _on_host_row_activated(self, _list: Gtk.ListBox, row: Gtk.ListBoxRow) -> None:
        profile = self._selected_profile()
        if profile is None:
            return
        index = int(getattr(row, "entry_index", -1))
        if index < 0 or index >= len(profile.entries):
            return
        self._open_entry_dialog(profile, index, profile.entries[index])

    def _refresh_status(self) -> None:
        path = hosts_path_from_env()
        self.path_label.set_text(str(path))
        self.status_badge.remove_css_class("status-badge-ok")
        self.status_badge.remove_css_class("status-badge-warn")
        if skip_polkit() or self._authorized:
            self.status_label.set_text("Hosts file is writable")
            self.status_icon.set_from_icon_name("emblem-ok-symbolic")
            self.status_badge.add_css_class("status-badge-ok")
            self.status_badge.set_tooltip_text("Admin access is available for this session")
        elif can_apply():
            self.status_label.set_text("Admin access needed to save")
            self.status_icon.set_from_icon_name("dialog-password-symbolic")
            self.status_badge.add_css_class("status-badge-warn")
            self.status_badge.set_tooltip_text("Click to authorize admin access")
        else:
            self.status_label.set_text("Polkit helper not available")
            self.status_icon.set_from_icon_name("dialog-warning-symbolic")
            self.status_badge.add_css_class("status-badge-warn")
            self.status_badge.set_tooltip_text("Install the app helper to enable privileged writes")

    def _on_status_badge_clicked(self, *_args) -> None:
        if skip_polkit() or self._authorized:
            return
        if self._ensure_admin():
            self.toast_overlay.add_toast(Adw.Toast(title="Admin access granted"))
            self._refresh_sync_status()
    def _on_profile_row_selected(self, _list: Gtk.ListBox, row: Gtk.ListBoxRow | None) -> None:
        if row is None:
            return
        self.selected_index = int(getattr(row, "index", 0))
        self._rebuild_menu()
        self._refresh_hosts()

    def _on_search_changed(self, entry: Gtk.SearchEntry) -> None:
        self.search_text = entry.get_text()
        self._refresh_hosts()

    def _on_entry_toggled(self, switch: Gtk.Switch, _pspec, profile: Profile, index: int) -> None:
        if self._suppress_switch:
            return
        previous = profile.entries[index].enabled
        profile.entries[index].enabled = switch.get_active()
        self._persist()
        self._refresh_hosts()
        if not self._maybe_autosave(success_toast="Host updated in hosts file"):
            profile.entries[index].enabled = previous
            self._persist()
            self._refresh_hosts()

    def _on_active_badge_clicked(self, *_args) -> None:
        self._on_toggle_profile()

    def _on_add_profile(self, *_args) -> None:
        self._open_profile_editor(profile=None)

    def _on_change_icon(self, *_args) -> None:
        profile = self._selected_profile()
        if profile is None:
            return
        self._open_icon_picker(
            selected_id=profile.icon,
            on_pick=lambda icon_id: self._apply_profile_icon(profile, icon_id),
        )

    def _apply_profile_icon(self, profile: Profile, icon_id: str) -> None:
        profile.icon = icon_id
        self._persist()
        self._refresh_profiles()

    def _open_profile_editor(self, profile: Profile | None) -> None:
        creating = profile is None
        dialog = Adw.Dialog()
        dialog.set_content_width(460)
        dialog.set_content_height(520)
        dialog.set_title("New profile" if creating else "Edit profile")

        view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        view.add_top_bar(header)

        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        page.set_margin_start(16)
        page.set_margin_end(16)
        page.set_margin_top(8)
        page.set_margin_bottom(16)

        group = Adw.PreferencesGroup()
        name_row = Adw.EntryRow(title="Name")
        name_row.set_text("New profile" if creating else profile.name)
        group.add(name_row)
        page.append(group)

        icon_label = Gtk.Label(label="Icon")
        icon_label.set_xalign(0)
        icon_label.add_css_class("section-label")
        page.append(icon_label)

        selected = {"id": "default" if creating else profile.icon}
        flow = self._build_icon_flow(selected["id"], lambda icon_id: selected.__setitem__("id", icon_id))
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        scrolled.set_child(flow)
        page.append(scrolled)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        buttons.set_halign(Gtk.Align.END)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda *_: dialog.close())
        save = Gtk.Button(label="Create" if creating else "Save")
        save.add_css_class("suggested-action")
        buttons.append(cancel)
        buttons.append(save)
        page.append(buttons)
        view.set_content(page)
        dialog.set_child(view)

        def on_save(*_args) -> None:
            name = name_row.get_text().strip() or ("New profile" if creating else profile.name)
            if creating:
                created = Profile(
                    id=uuid.uuid4().hex[:8],
                    name=name,
                    icon=selected["id"],
                    enabled=False,
                )
                self.profiles.append(created)
                self.selected_index = len(self.profiles) - 1
            else:
                profile.name = name
                profile.icon = selected["id"]
            self._persist()
            self._refresh_profiles()
            self._refresh_hosts()
            dialog.close()

        save.connect("clicked", on_save)
        dialog.present(self)

    def _open_icon_picker(self, selected_id: str, on_pick) -> None:
        dialog = Adw.Dialog()
        dialog.set_content_width(440)
        dialog.set_content_height(420)
        dialog.set_title("Choose icon")

        view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        view.add_top_bar(header)

        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        page.set_margin_start(16)
        page.set_margin_end(16)
        page.set_margin_top(8)
        page.set_margin_bottom(16)

        hint = Gtk.Label(
            label="Pick an icon from the system theme (Adwaita symbolic set)."
        )
        hint.set_wrap(True)
        hint.set_xalign(0)
        hint.add_css_class("dim-label")
        page.append(hint)

        selected = {"id": selected_id}
        flow = self._build_icon_flow(selected["id"], lambda icon_id: selected.__setitem__("id", icon_id))
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        scrolled.set_child(flow)
        page.append(scrolled)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        buttons.set_halign(Gtk.Align.END)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda *_: dialog.close())
        apply = Gtk.Button(label="Apply")
        apply.add_css_class("suggested-action")
        buttons.append(cancel)
        buttons.append(apply)
        page.append(buttons)
        view.set_content(page)
        dialog.set_child(view)

        def on_apply(*_args) -> None:
            on_pick(selected["id"])
            dialog.close()

        apply.connect("clicked", on_apply)
        dialog.present(self)

    def _build_icon_flow(self, selected_id: str, on_select) -> Gtk.FlowBox:
        flow = Gtk.FlowBox()
        flow.add_css_class("icon-picker")
        flow.set_selection_mode(Gtk.SelectionMode.SINGLE)
        flow.set_max_children_per_line(6)
        flow.set_min_children_per_line(4)
        flow.set_homogeneous(True)
        flow.set_column_spacing(8)
        flow.set_row_spacing(8)

        theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
        selected_child = None
        for icon in PROFILE_ICONS:
            child = Gtk.FlowBoxChild()
            child.icon_id = icon.id  # type: ignore[attr-defined]
            button = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            button.add_css_class("icon-picker-item")
            button.set_margin_top(8)
            button.set_margin_bottom(8)
            button.set_margin_start(4)
            button.set_margin_end(4)
            image = Gtk.Image.new_from_icon_name(resolve_icon_name(icon.id, theme))
            image.add_css_class("icon-size-22")
            image.set_halign(Gtk.Align.CENTER)
            image.set_valign(Gtk.Align.CENTER)
            label = Gtk.Label(label=icon.label)
            label.add_css_class("icon-picker-label")
            label.set_ellipsize(Pango.EllipsizeMode.END)
            button.append(image)
            button.append(label)
            child.set_child(button)
            child.set_tooltip_text(icon.label)
            flow.append(child)
            if icon.id == selected_id:
                selected_child = child

        def on_child_activated(_flow, child: Gtk.FlowBoxChild) -> None:
            on_select(getattr(child, "icon_id", "default"))

        def on_selected(_flow) -> None:
            child = flow.get_selected_children()
            if child:
                on_select(getattr(child[0], "icon_id", "default"))

        flow.connect("child-activated", on_child_activated)
        flow.connect("selected-children-changed", on_selected)
        if selected_child is not None:
            flow.select_child(selected_child)
        return flow

    def _ensure_admin(self) -> bool:
        """Prompt for admin once when needed; keep the elevated session for later writes."""
        if skip_polkit() or self._authorized:
            return True
        if not can_apply():
            self._alert(
                "Cannot write hosts file",
                "The privileged helper is not available. Install the app or set HOSTS_MANAGER_SKIP_POLKIT=1 for testing.",
            )
            self._refresh_status()
            return False
        if ensure_authorized():
            self._authorized = True
            self._refresh_status()
            return True
        self._alert(
            "Admin access required",
            "Authorization is needed to update the hosts file.",
        )
        self._refresh_status()
        return False

    def _on_toggle_profile(self, *_args) -> None:
        profile = self._selected_profile()
        if profile is None:
            return
        if not self._ensure_admin():
            return
        previous = profile.enabled
        profile.enabled = not previous
        self._persist()
        self._refresh_profiles()
        self._refresh_hosts()
        self._refresh_sync_status()
        if not self._write_hosts(confirm=False, success_toast="Profile updated in hosts file"):
            profile.enabled = previous
            self._persist()
            self._refresh_profiles()
            self._refresh_hosts()
            self._refresh_sync_status()

    def _on_rename_profile(self, *_args) -> None:
        profile = self._selected_profile()
        if profile is None:
            return

        def apply_name(name: str) -> None:
            profile.name = name.strip() or profile.name
            self._persist()
            self._refresh_profiles()
            self._refresh_hosts()

        self._prompt_text("Rename profile", "Profile name", profile.name, apply_name)

    def _on_delete_profile(self, *_args) -> None:
        if len(self.profiles) <= 1:
            self._alert("Cannot delete", "At least one profile is required.")
            return
        profile = self._selected_profile()
        if profile is None:
            return
        dialog = Adw.AlertDialog(
            heading="Delete profile?",
            body=f"“{profile.name}” and its host entries will be removed from the app. /etc/hosts is not changed until you Save.",
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("delete", "Delete")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_close_response("cancel")

        def on_response(response: str) -> None:
            if response != "delete":
                return
            del self.profiles[self.selected_index]
            self.selected_index = min(self.selected_index, len(self.profiles) - 1)
            self._persist()
            self._refresh_profiles()
            self._refresh_hosts()
            self._maybe_autosave(success_toast="Profile removed from hosts file")

        self._present_alert(dialog, on_response)

    def _on_add_host(self, *_args) -> None:
        profile = self._selected_profile()
        if profile is None:
            return
        self._open_entry_dialog(profile, None, HostEntry(ip="127.0.0.1", hostname="", comment=""))

    def _open_entry_dialog(
        self,
        profile: Profile,
        index: int | None,
        entry: HostEntry,
    ) -> None:
        dialog = Adw.Dialog()
        dialog.set_content_width(440)
        dialog.set_title("Add host" if index is None else "Edit host")
        view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        view.add_top_bar(header)

        group = Adw.PreferencesGroup()
        host_row = Adw.EntryRow(title="Hostname")
        host_row.set_text(entry.hostname)
        ip_row = Adw.EntryRow(title="IP address")
        ip_row.set_text(entry.ip)
        comment_row = Adw.EntryRow(title="Description")
        comment_row.set_text(entry.comment)
        group.add(host_row)
        group.add(ip_row)
        group.add(comment_row)

        error = Gtk.Label()
        error.add_css_class("error")
        error.set_wrap(True)
        error.set_xalign(0)
        error.set_visible(False)

        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        page.set_margin_start(16)
        page.set_margin_end(16)
        page.set_margin_top(8)
        page.set_margin_bottom(16)
        page.append(group)
        page.append(error)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        buttons.set_halign(Gtk.Align.END)
        if index is not None:
            delete = Gtk.Button(label="Delete")
            delete.add_css_class("destructive-action")
            delete.connect("clicked", lambda *_: self._delete_entry(dialog, profile, index))
            buttons.append(delete)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda *_: dialog.close())
        save = Gtk.Button(label="Save")
        save.add_css_class("suggested-action")
        buttons.append(cancel)
        buttons.append(save)
        page.append(buttons)
        view.set_content(page)
        dialog.set_child(view)

        def on_save(*_args) -> None:
            draft = HostEntry(
                ip=ip_row.get_text().strip(),
                hostname=host_row.get_text().strip(),
                enabled=entry.enabled if index is not None else True,
                comment=comment_row.get_text().strip(),
            )
            try:
                validate_entry(draft)
            except ValidationError as exc:
                error.set_text(str(exc))
                error.set_visible(True)
                return
            same_family = [
                item.hostname.lower()
                for i, item in enumerate(profile.entries)
                if i != index and ip_family(item.ip) == ip_family(draft.ip)
            ]
            if draft.hostname.lower() in same_family:
                error.set_text(
                    "This profile already has that hostname on the same address family."
                )
                error.set_visible(True)
                return
            if index is None:
                profile.entries.append(draft)
            else:
                profile.entries[index] = draft
            self._persist()
            self._refresh_hosts()
            self._maybe_autosave(success_toast="Host updated in hosts file")
            dialog.close()

        save.connect("clicked", on_save)
        dialog.present(self)

    def _delete_entry(self, dialog: Adw.Dialog, profile: Profile, index: int) -> None:
        del profile.entries[index]
        self._persist()
        self._refresh_hosts()
        self._maybe_autosave(success_toast="Host removed from hosts file")
        dialog.close()

    def _on_apply_clicked(self, _button) -> None:
        self._write_hosts(confirm=True)

    def _write_hosts(self, *, confirm: bool, success_toast: str = "Hosts file updated") -> bool:
        path = hosts_path_from_env()
        try:
            current = path.read_text(encoding="utf-8")
        except OSError as exc:
            self._alert("Cannot read hosts file", str(exc))
            return False
        document = parse(current)
        adopted = adopted_map(self.profiles)
        try:
            new_text = merge_profiles(document, self.profiles)
        except MergeConflict as exc:
            self._alert("Cannot save changes", str(exc))
            return False
        changes = managed_diff(document, new_text) + adopted_diff(document, new_text, adopted)
        if not changes:
            if confirm:
                self.toast_overlay.add_toast(Adw.Toast(title="Nothing to save"))
            return True
        if confirm:
            self._pending_text = new_text
            self._pending_toast = success_toast
            dialog = Adw.AlertDialog(heading="Changes")
            dialog.set_extra_child(build_diff_box(rows_from_changes(changes)))
            dialog.add_response("cancel", "Cancel")
            dialog.add_response("apply", "Save")
            dialog.set_default_response("apply")
            dialog.set_close_response("cancel")
            dialog.set_response_appearance("apply", Adw.ResponseAppearance.SUGGESTED)

            def on_response(response: str) -> None:
                if response != "apply":
                    self._pending_text = None
                    self._pending_toast = "Hosts file updated"
                    return
                content = self._pending_text
                toast = self._pending_toast
                self._pending_text = None
                self._pending_toast = "Hosts file updated"
                if content is not None:
                    self._do_write_hosts(content, toast)

            self._present_alert(dialog, on_response)
            return True
        return self._do_write_hosts(new_text, success_toast)

    def _do_write_hosts(self, content: str, success_toast: str) -> bool:
        if not self._ensure_admin():
            return False
        try:
            apply_hosts(content)
        except (CalledProcessError, OSError, WriteError, WriteSessionError) as exc:
            detail = str(exc)
            if isinstance(exc, CalledProcessError) and exc.stderr:
                detail = exc.stderr.decode("utf-8", errors="replace").strip() or detail
            self._authorized = False
            self._alert("Save failed", detail or "Could not update the hosts file.")
            self._refresh_status()
            return False
        self._authorized = True
        self.toast_overlay.add_toast(Adw.Toast(title=success_toast))
        self._refresh_status()
        self._refresh_sync_status()
        self._last_written_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return True

    def _start_hosts_monitor(self) -> None:
        try:
            directory = hosts_path_from_env().parent
            monitor = Gio.File.new_for_path(str(directory)).monitor_directory(
                Gio.FileMonitorFlags.NONE, None
            )
            monitor.connect("changed", self._on_hosts_dir_changed)
            self._hosts_monitor = monitor
        except Exception:
            self._hosts_monitor = None

    def _on_hosts_dir_changed(self, _monitor, file, _other, event_type) -> None:
        if file is None:
            return
        if (file.get_basename() or "") != hosts_path_from_env().name:
            return
        if event_type in (
            Gio.FileMonitorEvent.CHANGES_DONE_HINT,
            Gio.FileMonitorEvent.CREATED,
            Gio.FileMonitorEvent.DELETED,
            Gio.FileMonitorEvent.RENAMED,
            Gio.FileMonitorEvent.MOVED_IN,
            Gio.FileMonitorEvent.MOVED_OUT,
        ):
            self._schedule_import_scan()

    def _schedule_import_scan(self) -> None:
        self._monitor_serial += 1
        serial = self._monitor_serial

        def scan() -> bool:
            if serial != self._monitor_serial:
                return GLib.SOURCE_REMOVE
            self._on_hosts_scan()
            return GLib.SOURCE_REMOVE

        GLib.timeout_add(400, scan)

    def _maybe_present_import(self, force: bool = False) -> None:
        if self._import_open:
            return
        path = hosts_path_from_env()
        try:
            current = path.read_text(encoding="utf-8")
        except OSError:
            return
        digest = hashlib.sha256(current.encode("utf-8")).hexdigest()
        if not force and digest == self._last_written_hash:
            return
        document = parse(current)
        plan = plan_import(document, self.profiles)
        if not plan.entries and not plan.problems:
            if force:
                self.toast_overlay.add_toast(Adw.Toast(title="Nothing to import"))
            return
        self._import_open = True
        self._import_document = document
        self._import_digest = digest
        self._last_written_hash = digest  # no re-trigger until the file changes again
        dialog = ImportDialog(document, plan, self.profiles, self._on_import_result)
        try:
            dialog.connect("close-attempt", lambda *_: self._on_import_result(None))
        except TypeError:
            pass  # libadwaita without close-attempt: Cancel is the only exit
        dialog.present(self)

    def _on_hosts_scan(self) -> None:
        if not self._maybe_present_sync():
            self._maybe_present_import()

    def _maybe_present_sync(self) -> bool:
        if self._sync_open:
            return True
        path = hosts_path_from_env()
        try:
            current = path.read_text(encoding="utf-8")
        except OSError:
            return False
        digest = hashlib.sha256(current.encode("utf-8")).hexdigest()
        if digest == self._last_written_hash:
            return False
        plan = plan_sync(parse(current), self.profiles)
        if not plan.changes:
            return False
        self._sync_open = True
        dialog = Adw.AlertDialog(heading="The hosts file changed outside the app")
        dialog.set_extra_child(build_diff_box(rows_from_sync_changes(plan.changes)))
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("apply", "Apply")
        dialog.set_default_response("apply")
        dialog.set_close_response("cancel")
        dialog.set_response_appearance("apply", Adw.ResponseAppearance.SUGGESTED)
        try:
            dialog.connect("close-attempt", lambda *_: self._finish_sync_choice(None))
        except TypeError:
            pass

        def on_response(response: str) -> None:
            self._finish_sync_choice(plan if response == "apply" else None)

        self._present_alert(dialog, on_response)
        return True

    def _finish_sync_choice(self, plan: SyncPlan | None) -> None:
        if not self._sync_open:
            return
        self._sync_open = False
        if plan is not None:
            self.profiles = plan.profiles
            self._persist()
            self._refresh_profiles()
            self._refresh_hosts()
            self._refresh_sync_status()
            path = hosts_path_from_env()
            try:
                digest = hashlib.sha256(path.read_text(encoding="utf-8")).hexdigest()
            except OSError:
                digest = None
            if digest:
                self._last_written_hash = digest
        else:
            self._refresh_sync_status()
        self._maybe_present_import()

    def _on_import_result(self, final_plan: ImportPlan | None) -> None:
        self._import_open = False
        if final_plan is None:
            return
        self._apply_import(final_plan)

    def _verify_unchanged(self) -> bool:
        """Return True when the hosts file still matches the import snapshot."""
        if self._import_digest is None:
            return False
        path = hosts_path_from_env()
        try:
            current = path.read_text(encoding="utf-8")
        except OSError as exc:
            self._alert("Cannot read hosts file", str(exc))
            return False
        digest = hashlib.sha256(current.encode("utf-8")).hexdigest()
        if digest != self._import_digest:
            self.toast_overlay.add_toast(Adw.Toast(title="Hosts file changed during import"))
            self._maybe_present_import(force=True)
            return False
        return True

    def _apply_import(self, plan: ImportPlan) -> None:
        document = self._import_document
        if document is None or self._import_digest is None:
            return
        if not self._verify_unchanged():
            return
        try:
            new_text = build_imported_text(document, plan, self.profiles)
        except (ValueError, MergeConflict) as exc:
            self._alert("Cannot import", str(exc))
            return
        changes = managed_diff(document, new_text)
        if not changes and not plan.delete_lines:
            self.toast_overlay.add_toast(Adw.Toast(title="Nothing to import"))
            return
        note = ""
        if plan.delete_lines:
            note = f"Removes {len(plan.delete_lines)} unparsable line(s) from the hosts file."
        dialog = Adw.AlertDialog(heading="Import changes")
        dialog.set_extra_child(build_diff_box(rows_from_changes(changes), note=note))
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("apply", "Save")
        dialog.set_default_response("apply")
        dialog.set_close_response("cancel")
        dialog.set_response_appearance("apply", Adw.ResponseAppearance.SUGGESTED)

        def on_response(response: str) -> None:
            if response != "apply":
                return
            if not self._verify_unchanged():
                return
            if self._do_write_hosts(new_text, "Imported existing hosts"):
                self._finish_import(plan)

        self._present_alert(dialog, on_response)

    def _finish_import(self, plan: ImportPlan) -> None:
        if plan.entries:
            ensure_import_profile(self.profiles, plan.entries)
        self._persist()
        self._refresh_profiles()
        self._refresh_hosts()
        self._refresh_sync_status()

    def _on_about(self, *_args) -> None:
        about = Adw.AboutDialog(
            application_name="Hosts Manager",
            application_icon=APP_ID,
            developer_name="Deepvelop",
            version=__version__,
            comments=(
                "Manage /etc/hosts with profile overlays. The GUI never runs as root. "
                "Active toggles write hosts immediately. Enable auto-save in Settings to write "
                "host edits without pressing Save."
            ),
            developers=["Stef van Diepen"],
            copyright="© 2026 Deepvelop",
            website="https://deepvelop.nl/",
            issue_url="https://github.com/deepvelop/linux-hosts-manager/issues",
            license_type=Gtk.License.APACHE_2_0,
        )
        about.add_link("GitHub", "https://github.com/deepvelop/linux-hosts-manager")
        about.add_credit_section(
            "Developers",
            ["Stef van Diepen"],
        )
        about.add_credit_section(
            "Organisation",
            ["Deepvelop"],
        )
        about.present(self)

    def _present_alert(self, dialog: Adw.AlertDialog, on_response) -> None:
        def handler(_dialog: Adw.AlertDialog, response: str) -> None:
            on_response(response)

        dialog.connect("response", handler)
        dialog.present(self)

    def _on_settings(self, *_args) -> None:
        backup = backup_dir_from_env()
        dialog = Adw.Dialog()
        dialog.set_title("Settings")
        dialog.set_content_width(460)
        dialog.set_content_height(420)

        view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        view.add_top_bar(header)

        page = Adw.PreferencesPage()
        page.add_css_class("settings-page")

        behavior = Adw.PreferencesGroup(title="Saving")
        auto_row = Adw.SwitchRow(
            title="Auto-save hosts file",
            subtitle="Write /etc/hosts as soon as you edit hosts or toggle entries",
        )
        auto_row.set_active(self.settings.auto_save)

        def on_auto_save(_row, _pspec) -> None:
            self.settings.auto_save = auto_row.get_active()
            self.settings_store.save(self.settings)
            self._sync_apply_button()
            self._refresh_sync_status()
            if self.settings.auto_save:
                self._maybe_autosave(success_toast="Hosts file updated")

        auto_row.connect("notify::active", on_auto_save)
        behavior.add(auto_row)
        page.add(behavior)

        paths = Adw.PreferencesGroup(title="Paths")
        hosts_row = Adw.ActionRow(title="Hosts file")
        hosts_row.set_subtitle(str(hosts_path_from_env()))
        hosts_row.set_subtitle_lines(2)
        paths.add(hosts_row)

        backup_row = Adw.ActionRow(title="Backups")
        backup_row.set_subtitle(str(backup))
        backup_row.set_subtitle_lines(2)
        open_btn = Gtk.Button(label="Open")
        open_btn.set_valign(Gtk.Align.CENTER)
        open_btn.add_css_class("flat")

        def open_backups(*_args) -> None:
            backup.mkdir(parents=True, exist_ok=True)
            Gio.AppInfo.launch_default_for_uri(backup.resolve().as_uri(), None)

        open_btn.connect("clicked", open_backups)
        backup_row.add_suffix(open_btn)
        backup_row.set_activatable_widget(open_btn)
        paths.add(backup_row)
        page.add(paths)

        about = Adw.PreferencesGroup(title="About writing")
        note_row = Adw.ActionRow(
            title="Admin access",
            subtitle=(
                "Asked once per app session. Active/Inactive always writes immediately. "
                "With auto-save off, use Save for host entry changes."
            ),
        )
        note_row.set_subtitle_lines(3)
        about.add(note_row)
        page.add(about)

        view.set_content(page)
        dialog.set_child(view)
        dialog.present(self)

    def _prompt_text(self, heading: str, placeholder: str, initial: str, on_ok) -> None:
        dialog = Adw.AlertDialog(heading=heading)
        entry = Gtk.Entry()
        entry.set_placeholder_text(placeholder)
        entry.set_text(initial)
        dialog.set_extra_child(entry)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("ok", "Save")
        dialog.set_default_response("ok")
        dialog.set_close_response("cancel")
        dialog.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)

        def on_response(response: str) -> None:
            if response == "ok":
                on_ok(entry.get_text())

        self._present_alert(dialog, on_response)

    def _alert(self, heading: str, body: str) -> None:
        dialog = Adw.AlertDialog(heading=heading, body=body)
        dialog.add_response("ok", "OK")
        dialog.present(self)


def present_window(application: Adw.Application) -> HostsManagerWindow:
    win = HostsManagerWindow(application=application)
    win.present()
    return win
