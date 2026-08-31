"""Import review dialog: fix or remove unparsable hosts lines, then import."""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Pango", "1.0")

from gi.repository import Adw, Gtk, Pango

from hosts_manager.importer import ImportPlan, replan_with_edits
from hosts_manager.models import HostEntry, HostsDocument, Profile


class ImportDialog(Adw.Dialog):
    """Review dialog for importing unmanaged hosts lines."""

    def __init__(
        self,
        document: HostsDocument,
        plan: ImportPlan,
        profiles: list[Profile],
        on_result: Callable[[ImportPlan | None], None],
    ) -> None:
        super().__init__()
        self.set_title("Import existing hosts")
        self.set_content_width(640)
        self.set_content_height(560)
        self._document = document
        self._plan = plan
        self._profiles = profiles
        self._on_result = on_result
        self._edited_raws: dict[int, str] = {}
        self._build()
        self._render()

    def _build(self) -> None:
        view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        view.add_top_bar(header)

        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        page.set_margin_start(16)
        page.set_margin_end(16)
        page.set_margin_top(8)
        page.set_margin_bottom(16)

        self._summary = Gtk.Label()
        self._summary.set_wrap(True)
        self._summary.set_xalign(0)
        page.append(self._summary)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        self._list = Gtk.ListBox()
        self._list.set_selection_mode(Gtk.SelectionMode.NONE)
        scrolled.set_child(self._list)
        page.append(scrolled)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._retry_btn = Gtk.Button(label="Retry")
        self._retry_btn.connect("clicked", self._on_retry)
        buttons.append(self._retry_btn)
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        buttons.append(spacer)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", self._on_cancel)
        buttons.append(cancel)
        self._import_btn = Gtk.Button(label="Import")
        self._import_btn.add_css_class("suggested-action")
        self._import_btn.connect("clicked", self._on_import)
        buttons.append(self._import_btn)
        page.append(buttons)

        view.set_content(page)
        self.set_child(view)

    def _render(self) -> None:
        entry_count = len(self._plan.entries)
        problem_count = len(self._plan.problems)
        self._summary.set_text(
            f"Found {entry_count} host entr{'y' if entry_count == 1 else 'ies'} and "
            f"{problem_count} problem line{'s' if problem_count != 1 else ''} in the hosts file. "
            "Entries will be added to the enabled 'Existing hosts' profile and moved "
            "into the Hosts Manager block."
        )
        self._list.remove_all()
        for entry in self._plan.entries:
            self._list.append(self._entry_row(entry))
        for problem in self._plan.problems:
            self._list.append(self._problem_row(problem))
        self._retry_btn.set_sensitive(
            bool(self._edited_raws) or bool(self._plan.delete_lines)
        )
        self._import_btn.set_sensitive(not self._plan.problems)

    def _entry_row(self, entry: HostEntry) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        row.set_activatable(False)
        text = f"{entry.ip} {entry.hostname}"
        if entry.comment:
            text = f"{text}  # {entry.comment}"
        label = Gtk.Label(label=text)
        label.add_css_class("import-raw")
        label.set_xalign(0)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_margin_start(12)
        label.set_margin_end(12)
        label.set_margin_top(8)
        label.set_margin_bottom(8)
        if not entry.enabled:
            row.add_css_class("disabled-entry")
        row.set_child(label)
        return row

    def _problem_row(self, problem) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        row.set_activatable(False)
        grid = Gtk.Grid()
        grid.set_column_spacing(10)
        grid.set_margin_start(12)
        grid.set_margin_end(12)
        grid.set_margin_top(8)
        grid.set_margin_bottom(8)

        lineno = Gtk.Label(label=str(problem.lineno))
        lineno.add_css_class("import-lineno")
        lineno.set_valign(Gtk.Align.START)
        grid.attach(lineno, 0, 0, 1, 1)

        content = Gtk.Label()
        content.set_xalign(0)
        content.set_ellipsize(Pango.EllipsizeMode.END)
        content.set_hexpand(True)
        if problem.lineno in self._edited_raws:
            content.set_label(self._edited_raws[problem.lineno])
            content.add_css_class("import-raw")
        else:
            content.set_label(problem.raw)
            content.add_css_class("import-raw")
        content.set_tooltip_text(problem.raw)
        grid.attach(content, 1, 0, 1, 1)

        if problem.lineno in self._edited_raws:
            fault_text = "Edited — press Retry to apply"
        else:
            fault_text = problem.fault
        fault = Gtk.Label(label=fault_text)
        fault.add_css_class("import-fault")
        fault.set_wrap(True)
        fault.set_xalign(0)
        fault.set_valign(Gtk.Align.START)
        grid.attach(fault, 2, 0, 1, 1)

        edit = Gtk.Button(label="Edit")
        edit.connect("clicked", lambda *_: self._open_edit(problem))
        edit.set_valign(Gtk.Align.START)
        grid.attach(edit, 3, 0, 1, 1)

        remove = Gtk.Button(label="Remove")
        remove.add_css_class("destructive-action")
        remove.connect("clicked", lambda *_: self._on_remove(problem))
        remove.set_valign(Gtk.Align.START)
        grid.attach(remove, 4, 0, 1, 1)

        row.set_child(grid)
        return row

    def _on_remove(self, problem) -> None:
        self._plan.problems.remove(problem)
        self._plan.delete_lines.add(problem.lineno)
        self._render()

    def _open_edit(self, problem) -> None:
        dialog = Adw.Dialog()
        dialog.set_title(f"Edit line {problem.lineno}")
        dialog.set_content_width(520)

        view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        view.add_top_bar(header)

        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        page.set_margin_start(16)
        page.set_margin_end(16)
        page.set_margin_top(8)
        page.set_margin_bottom(16)

        hint = Gtk.Label(
            label="Expected shape: IP hostname [# description]. "
            "A line starting with # is kept in the hosts file as a comment."
        )
        hint.set_wrap(True)
        hint.set_xalign(0)
        hint.add_css_class("dim-label")
        page.append(hint)

        buffer = Gtk.TextBuffer()
        buffer.set_text(self._edited_raws.get(problem.lineno, problem.raw))
        view_text = Gtk.TextView(buffer=buffer)
        view_text.add_css_class("import-raw")
        view_text.set_monospace(True)
        view_text.set_wrap_mode(Gtk.WrapMode.CHAR)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_min_content_height(80)
        scrolled.set_child(view_text)
        page.append(scrolled)

        error = Gtk.Label()
        error.add_css_class("error")
        error.set_wrap(True)
        error.set_xalign(0)
        error.set_visible(False)
        page.append(error)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        buttons.set_halign(Gtk.Align.END)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda *_: dialog.close())
        save = Gtk.Button(label="Save")
        save.add_css_class("suggested-action")

        def on_save(*_args) -> None:
            text = buffer.get_text(
                buffer.get_start_iter(), buffer.get_end_iter(), False
            ).strip()
            if "\n" in text:
                error.set_text("Edit a single line only.")
                error.set_visible(True)
                return
            error.set_visible(False)
            self._edited_raws[problem.lineno] = text
            dialog.close()
            self._render()

        save.connect("clicked", on_save)
        buttons.append(cancel)
        buttons.append(save)
        page.append(buttons)
        view.set_content(page)
        dialog.set_child(view)
        dialog.present(self)

    def _on_retry(self, *_args) -> None:
        self._plan = replan_with_edits(
            self._document, self._plan, self._edited_raws, self._profiles
        )
        self._edited_raws = {}
        self._render()

    def _on_import(self, *_args) -> None:
        self._on_result(self._plan)
        self.close()

    def _on_cancel(self, *_args) -> None:
        self._on_result(None)
        self.close()
