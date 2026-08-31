# Existing hosts import — design

**Date:** 2026-08-31  
**Status:** Approved  
**Version:** 0.2.0

## Goal

When the system hosts file contains entries the app does not manage — at first launch and whenever the file changes externally — automatically offer to import those entries into a new enabled profile ("Existing hosts", Home icon) and move them into the Hosts Manager managed block. Lines that cannot be parsed are shown in a review dialog with the complete picture: **line number, raw content, and the fault**, plus **Edit** / **Remove** actions and a **Retry** button. No import is written without the user confirming the resulting diff.

## Requirements

1. **Real-time trigger.** A directory monitor on `/etc` (filtered to the hosts-file basename) detects external changes. The app's own writes must never re-trigger the import dialog.
2. **First-run trigger.** The same scan runs once at window startup, covering "hosts file not empty on install". Import detection lives in the app (never in `install.sh`), so the created profile lands in the user's config, not root's.
3. **Profile creation.** Import targets a profile with the reserved stable id `existing-hosts`, name `Existing hosts`, icon `home` (fallback icon resolution as with all other icons), `enabled=True`. On the first import the profile is created; on later imports (new external lines) entries are appended to that same profile. The stable id survives renames by the user, so re-imports always find the right target.
4. **Move semantics.** Imported entry lines are removed from their original position and rewritten inside the managed block, reformatted by the app. Standalone comment and blank lines stay in place untouched.
5. **Problem lines.** A line the parser cannot turn into an entry (or which duplicates/clashes, see 6) is a *problem*: the dialog shows line number, raw content, and a human-readable fault. Problems are never silently dropped or written.
6. **Edit / Remove / Retry.**
   - **Edit** opens a raw-text editor for that line. **Retry** re-parses every edited or still-unresolved problem line: a line that now parses becomes an entry (moved into the block); a line that parses as comment or blank is kept in place (this is also the "skip" path — prefix a line with `#`); a line that still fails gets an updated fault.
   - **Remove** deletes the line from the hosts file on import.
   - **Import** (the confirm button) is enabled only when zero problems remain.
7. **Duplicate and clash detection.** Within the import: a hostname appearing on two lines flags the later line ("Duplicate hostname '<x>' (also on line N)"). A hostname already present in an *enabled* existing profile flags the imported line ("Hostname '<x>' already in profile '<name>'"). These checks re-run on every Retry over the resolved entries.
8. **Confirmation before write.** Import shows the app's existing diff-confirmation dialog and writes through the existing polkit path.
9. **Manual re-run.** A "Import existing hosts" entry in the profile menu triggers the scan on demand.

## Design

### Parser extensions (`hosts_manager/parser.py`, `models.py`)

- `HostsLine` gains `lineno: int = 0` (1-based) and `fault: str = ""`.
- `parse()` fills `lineno`; `_parse_line` and `_try_parse_entry` are extended so `UNKNOWN` lines carry a reason:
  - `Not a hosts entry (expected: IP hostname)` — fewer than two tokens after inline-comment handling
  - `Invalid IP address: <ip>`
  - `Invalid hostname: <name>`
- `serialize()` is unchanged; all changes are additive.

### Importer module (`hosts_manager/importer.py`, new — pure logic, no GTK)

```python
@dataclass
class ImportProblem:
    lineno: int
    raw: str
    fault: str

@dataclass
class ImportPlan:
    entries: list[HostEntry]
    problems: list[ImportProblem]
    source_lines: set[int]     # linenos of entry lines being moved
    delete_lines: set[int]     # linenos removed by the user
    keep_lines: set[int]       # linenos kept in place (edited into comment/blank)
```

- `plan_import(document, profiles) -> ImportPlan`
  - Scans only lines outside the managed block (`split_managed` before/after sections).
  - `ENTRY` → one `HostEntry` per hostname (inline description kept); `DISABLED_ENTRY` → `HostEntry(enabled=False)`.
  - `UNKNOWN` → `ImportProblem`; duplicate/clash checks per requirement 7.
  - Lines inside the managed block are never scanned.
- `ensure_import_profile(profiles, plan) -> Profile` — returns the existing profile with id `existing-hosts` (appending `plan.entries`, forcing `enabled=True`) or creates one: `Profile(id="existing-hosts", name="Existing hosts", icon="home", enabled=True, entries=plan.entries)`. Note the profile editor generates `uuid.uuid4().hex[:8]` ids, which can never collide with the reserved id.
- `build_imported_text(document, plan, profiles) -> str`
  - Removes `source_lines ∪ delete_lines` from the document; `keep_lines` untouched.
  - Appends the import profile and delegates to the existing `merge_profiles`, which handles block placement, formatting, duplicate and unmanaged-clash validation.
  - Returns the new file text. Callers must ensure `plan.problems` is empty first.

### Import dialog (`hosts_manager/import_dialog.py`, new)

`ImportDialog(Adw.Dialog)`, built in the app's existing visual style (PreferencesGroups, suggested-action buttons, icon helpers). `window.py` stays out of the dialog internals; it presents the dialog and reacts to its result.

- Title: **Import existing hosts**.
- Summary line: "Found N host entries and M problem lines in /etc/hosts. Entries will be added to the enabled 'Existing hosts' profile and moved into the Hosts Manager block."
- One row per imported line:
  - Resolved entry rows: entry summary (ip + hostname + description), styled like the host table.
  - Problem rows: line-number badge, monospace raw content (ellipsized, full text in tooltip), fault text, **Edit** and **Remove** buttons.
  - Kept rows (edited into comment/blank): dimmed, "kept in place".
- **Edit** opens a raw-text editor dialog (monospace `Gtk.TextView`, prefilled with the line's current raw text; a hint explains the expected `IP hostname [# description]` shape and the `#`-to-keep trick).
- **Retry** re-parses each edited/unresolved problem line through the parser, then re-runs duplicate/clash checks over the resolved entries. Rows update in place; faults refresh. Retry is enabled once at least one edit or removal has been made.
- Footer: **Retry**, **Cancel**, **Import** (suggested-action, enabled only when zero problems remain).
- Result object handed back to the window: final `ImportPlan` (with populated `delete_lines`/`keep_lines`) or `None` on cancel.

### Monitoring & window integration (`hosts_manager/window.py`)

- `Gio.File.new_for_path(<hosts dir>).monitor_directory(Gio.FileMonitorFlags.NONE)`; events filtered to the hosts-file basename. Handles editors that replace the file via rename. Monitor creation wrapped in try/except — on failure the app works without real-time watching (first-run and menu-triggered scans still function).
- Debounce: act on `CHANGES_DONE_HINT` when present, coalesce further events with a short GLib timeout before scanning.
- Own-write suppression: after every successful `_do_write_hosts`, record the hash of the written content. The monitor handler re-reads the file and compares hashes before doing anything; equality means our own write (or a no-op change) — ignored.
- `_maybe_present_import(force=False)`: skips while the dialog is open; reads + parses the hosts file; `plan_import(document, self.profiles)`; presents the dialog when there is anything to import (entries or problems). Called once at window startup (after profile/store init) and from the monitor handler; `force=True` from the new **Import existing hosts** menu action (re-runs even when the current plan is empty — reports "nothing to import" as a toast).
- Import flow: dialog result → re-read the file and verify the hash matches the plan snapshot (mismatch → toast "hosts file changed during import" and re-open fresh) → `build_imported_text` → existing diff-confirmation dialog → `_do_write_hosts`. On success: `ensure_import_profile(self.profiles, plan)` (appends the profile if newly created), persist, refresh, record the written-content hash.

### Edge cases

- Empty file, or only comments/blanks outside the block → nothing to import, no dialog.
- File changed mid-import → abort with toast, rescan.
- Multiple rapid events → coalesced; one scan per debounce window, verified by hash.
- Import while unauthorized → existing `_ensure_admin` prompt at write time; on failure nothing is persisted.
- `HOSTS_MANAGER_HOSTS_PATH` test env → monitoring targets that file's directory, so the smoke-test flow keeps working.

## Testing

- **Parser**: line numbers on every line; fault strings for each malformed class (bad IP, bad hostname, too few tokens); existing round-trip tests untouched.
- **Importer** (pure fixtures):
  - clean unmanaged entries → entries only, no problems
  - mixed valid/bad/blank/comment lines → correct split; standalone comments not in `source_lines`
  - disabled entries import as `enabled=False`
  - duplicate hostnames flag the later line; enabled-profile clashes flag the imported line
  - lines inside the managed block are excluded
  - `build_imported_text`: originals and deleted lines removed, block appended with the import profile, standalone comments kept, trailing newline preserved
- **Dialog logic** stays thin (state transitions + parse calls); covered through importer unit tests and the existing manual smoke-test flow (`HOSTS_MANAGER_SKIP_POLKIT=1` + temp hosts file).
- Full suite must stay green: `.venv/bin/pytest -q`.

## Docs

- README: feature bullet under Features, new "Importing existing hosts" section under "How it works".
- No packaging changes; monitoring is in-process.

## Non-goals

- Monitoring other files or paths beyond the configured hosts file.
- Importing standalone comments into profiles (profile model keeps entries only).
- A settings toggle to disable watching (the dialog only appears when unmanaged entries exist; Cancel suppresses until the next external change).
- Editing problem lines with the structured host editor — raw-text editing is the interface for fixes.
