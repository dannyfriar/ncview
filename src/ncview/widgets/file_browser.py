"""DataTable-based file browser with vim keybindings and virtual scrolling."""

from __future__ import annotations

import os
import re
import shlex
import shutil
import stat
import subprocess
from enum import Enum
from pathlib import Path

from rich.text import Text
from textual import on, work
from textual.coordinate import Coordinate
from textual.events import Key
from textual.message import Message
from textual.widget import Widget
from textual.widgets import DataTable, Input

from ncview.utils.clipboard import copy_to_clipboard
from ncview.utils.file_info import file_icon, human_size


class SortKey(Enum):
    NAME = "name"
    SIZE = "size"
    MODIFIED = "modified"


def _format_perms(mode: int) -> str:
    """Format st_mode into rwxrwxrwx string."""
    bits = (
        (stat.S_IRUSR, "r"), (stat.S_IWUSR, "w"), (stat.S_IXUSR, "x"),
        (stat.S_IRGRP, "r"), (stat.S_IWGRP, "w"), (stat.S_IXGRP, "x"),
        (stat.S_IROTH, "r"), (stat.S_IWOTH, "w"), (stat.S_IXOTH, "x"),
    )
    return "".join(c if mode & b else "-" for b, c in bits)


class InputMode(Enum):
    NONE = "none"
    SEARCH = "search"
    EDITOR = "editor"
    TOUCH = "touch"
    RENAME = "rename"
    MKDIR = "mkdir"
    FILTER = "filter"


_INPUT_IDS: dict[InputMode, str] = {
    InputMode.SEARCH: "search-input",
    InputMode.EDITOR: "editor-input",
    InputMode.TOUCH: "touch-input",
    InputMode.RENAME: "rename-input",
    InputMode.MKDIR: "mkdir-input",
    InputMode.FILTER: "filter-input",
}


class FileHighlighted(Message):
    """Posted when a file is highlighted (cursor moved) in the browser."""

    def __init__(self, path: Path) -> None:
        super().__init__()
        self.path = path


class FileSelected(Message):
    """Posted when user explicitly opens a file (Enter/l)."""

    def __init__(self, path: Path) -> None:
        super().__init__()
        self.path = path


class DirectoryChanged(Message):
    """Posted when the browser navigates to a new directory."""

    def __init__(self, path: Path) -> None:
        super().__init__()
        self.path = path


class FileBrowser(Widget):
    """Flat directory listing with vim keybindings."""

    DEFAULT_CSS = """
    FileBrowser {
        height: 1fr;
        width: 1fr;
    }
    FileBrowser > DataTable {
        height: 1fr;
    }
    FileBrowser > Input {
        dock: bottom;
        display: none;
    }
    """

    BINDINGS = [
        ("j", "cursor_down", "Down"),
        ("k", "cursor_up", "Up"),
        ("l", "enter_or_open", "Open"),
        ("h", "parent_dir", "Parent"),
        ("g", "jump_top", "Top"),
        ("G", "jump_bottom", "Bottom"),  # noqa: E741
        ("full_stop", "toggle_hidden", "Toggle hidden"),
        ("s", "cycle_sort", "Cycle sort"),
        ("slash", "start_search", "Search"),
        ("e", "open_editor", "Editor"),
        ("E", "open_editor_path", "Edit path"),  # noqa: E741
        ("n", "search_next", "Next match"),
        ("N", "search_prev", "Prev match"),  # noqa: E741
        ("y", "yank_path", "Copy path"),
        ("d", "delete", "Delete"),
        ("t", "touch_file", "Touch"),
        ("r", "rename", "Rename"),
        ("M", "mkdir", "Mkdir"),  # noqa: E741
        ("~", "go_home", "Home"),
        ("ctrl+o", "go_back", "Back"),
        ("S", "open_shell", "Shell"),  # noqa: E741
        ("x", "toggle_perms", "Permissions"),
        ("f", "start_filter", "Filter"),
        ("V", "visual_toggle", "Visual"),  # noqa: E741
    ]

    def __init__(self, start_path: Path | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.current_dir = (start_path or Path.cwd()).absolute()
        self._load_gen = 0
        self._entries: list[Path] = []
        self._show_hidden = False
        self._sort_key = SortKey.NAME
        self._input_mode = InputMode.NONE
        self._rename_path: Path | None = None
        self._path_map: dict[str, Path] = {}
        self._search_query = ""
        self._search_matches: list[int] = []
        self._search_index = -1
        self._base_subtitle = ""
        self._dir_stack: list[Path] = []
        self._show_perms = False
        self._focus_name: str | None = None
        self._dir_mtime: float = 0.0
        self._filter_pattern: str = ""
        self._visual_mode = False
        self._visual_anchor: int = -1
        self._base_labels: list = []  # Original row labels (before selection markers)
        self._row_keys: list[str] = []  # Row keys in display order

    def compose(self):
        yield DataTable(id="file-list", cursor_type="row", show_header=False)
        yield Input(placeholder="Search...", id="search-input")
        yield Input(placeholder="File path to edit...", id="editor-input")
        yield Input(placeholder="New file name...", id="touch-input")
        yield Input(placeholder="Rename to...", id="rename-input")
        yield Input(placeholder="New directory name...", id="mkdir-input")
        yield Input(placeholder="Filter regex (e.g. \\.py$, test_.*, \\.(js|ts)$)...", id="filter-input")

    def on_mount(self) -> None:
        self._load_directory()
        self.set_interval(2.0, self._check_for_changes)

    def _check_for_changes(self) -> None:
        """Poll directory mtime and reload if files were added/removed."""
        try:
            mtime = os.stat(self.current_dir).st_mtime
            if mtime != self._dir_mtime and self._dir_mtime != 0.0:
                self._load_directory()
        except OSError:
            pass

    def on_key(self, event: Key) -> None:
        """Intercept keys before DataTable eats them."""
        if self._input_mode != InputMode.NONE:
            if event.key == "escape":
                event.prevent_default()
                event.stop()
                self._finish_input()
            return
        if self._visual_mode and event.key == "escape":
            event.prevent_default()
            event.stop()
            self._exit_visual_mode()
            return
        if event.key == "backspace":
            event.prevent_default()
            event.stop()
            self.action_parent_dir()
        elif event.key == "left":
            event.prevent_default()
            event.stop()
            self.action_parent_dir()
        elif event.key == "right":
            event.prevent_default()
            event.stop()
            self.action_enter_or_open()

    def _finish_input(self) -> None:
        """Hide the active input and return focus to the file list."""
        if self._input_mode == InputMode.NONE:
            return
        input_id = _INPUT_IDS[self._input_mode]
        self.query_one(f"#{input_id}", Input).styles.display = "none"
        if self._input_mode == InputMode.RENAME:
            self._rename_path = None
        self._input_mode = InputMode.NONE
        self.query_one("#file-list", DataTable).focus()

    @work(thread=True, exclusive=True)
    def _load_directory(self) -> None:
        """Load directory contents in a background thread."""
        self._load_gen += 1
        gen = self._load_gen

        try:
            self._dir_mtime = os.stat(self.current_dir).st_mtime
        except OSError:
            self._dir_mtime = 0.0

        try:
            scan = list(os.scandir(self.current_dir))
        except (PermissionError, OSError):
            scan = []

        if not self._show_hidden:
            scan = [e for e in scan if not e.name.startswith(".")]

        # Partition using cached is_dir (no extra stat)
        dir_entries = []
        file_entries = []
        for e in scan:
            try:
                if e.is_dir(follow_symlinks=True):
                    dir_entries.append(e)
                else:
                    file_entries.append(e)
            except OSError:
                file_entries.append(e)

        # Cache stat results once per entry for sorting, sizes, and permissions
        # When sorting by name with no perms, only stat file entries (dirs don't need size)
        need_all_stats = (self._sort_key != SortKey.NAME) or self._show_perms
        entries_to_stat = scan if need_all_stats else file_entries
        stat_cache: dict[str, os.stat_result] = {}
        for e in entries_to_stat:
            try:
                stat_cache[e.name] = e.stat(follow_symlinks=True)
            except OSError:
                pass

        sort_key = self._sort_key
        def _sort_func(entry: os.DirEntry) -> object:
            if sort_key == SortKey.SIZE:
                st = stat_cache.get(entry.name)
                return st.st_size if st else 0
            elif sort_key == SortKey.MODIFIED:
                st = stat_cache.get(entry.name)
                return -st.st_mtime if st else 0
            return entry.name.lower()

        dir_entries.sort(key=_sort_func)
        file_entries.sort(key=_sort_func)

        # Apply file type filter (directories always shown)
        if self._filter_pattern:
            try:
                regex = re.compile(self._filter_pattern, re.IGNORECASE)
                file_entries = [e for e in file_entries if regex.search(e.name)]
            except re.error:
                pass

        # Build Path lists, dir names set, and sizes dict
        dirs = [Path(e.path) for e in dir_entries]
        files = [Path(e.path) for e in file_entries]
        all_entries = dirs + files
        dir_names = {e.name for e in dir_entries}

        sizes: dict[str, int] = {}
        for e in file_entries:
            try:
                st = stat_cache.get(e.name) or e.stat(follow_symlinks=True)
                sizes[e.name] = st.st_size
            except OSError:
                pass

        perms: dict[str, str] = {}
        mtimes: dict[str, str] = {}
        if self._show_perms:
            from datetime import datetime
            for e in scan:
                st = stat_cache.get(e.name)
                if st:
                    perms[e.name] = _format_perms(st.st_mode)
                    mtimes[e.name] = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")

        symlinks: dict[str, str] = {}
        for e in scan:
            try:
                if e.is_symlink():
                    symlinks[e.name] = os.readlink(e.path)
            except OSError:
                pass

        # Git status — only if we're in a git repo, with a timeout
        git_status = self._get_git_status()

        # Build Rich Text rows in the background thread (Text objects are pure data)
        show_perms = bool(perms)
        rows: list[tuple] = []
        keys: list[str] = []

        # Parent directory entry
        if self.current_dir != Path(self.current_dir.root):
            label = Text()
            label.append("\uf07b ", style="bold #e6db74")
            label.append("..", style="bold #e6db74")
            row = (label, "", "", "") if show_perms else (label, "")
            rows.append(row)
            keys.append("..")

        has_git = git_status is not None
        for entry in all_entries:
            is_dir = entry.name in dir_names
            label = Text()
            # Git status marker
            if has_git and entry.name in git_status:
                xy = git_status[entry.name]
                if xy == "??":
                    label.append("? ", style="bold #a6e22e")
                elif xy[0] in "MADRC":
                    label.append("+ ", style="bold #a6e22e")
                elif xy[1] == "M":
                    label.append("~ ", style="bold #fd971f")
                elif xy[1] == "D":
                    label.append("- ", style="bold #f92672")
                else:
                    label.append("* ", style="bold #ae81ff")
            elif has_git:
                label.append("  ")
            icon = file_icon(entry, is_dir=is_dir)
            label.append(f"{icon} ")
            if is_dir:
                label.append(entry.name + "/", style="bold #66d9ef")
                size_text = ""
            else:
                label.append(entry.name, style="#f8f8f2")
                size_text = human_size(sizes[entry.name]) if entry.name in sizes else ""
            if symlinks and entry.name in symlinks:
                label.append(" \u2192 ", style="#75715e")
                label.append(symlinks[entry.name], style="#75715e")
            if show_perms:
                perm_text = perms.get(entry.name, "")
                mtime_text = mtimes.get(entry.name, "")
                rows.append((label, perm_text, mtime_text, size_text))
            else:
                rows.append((label, size_text))
            keys.append(entry.name)

        # Drop stale results if the user navigated away while we were loading
        if gen != self._load_gen:
            return
        self.app.call_from_thread(self._populate_list, gen, all_entries, dir_names, rows, keys, show_perms)

    def _get_git_status(self) -> dict[str, str]:
        """Get git status for files in the current directory. Returns empty dict if not a repo."""
        try:
            # Get the path prefix from repo root to current dir
            prefix_result = subprocess.run(
                ["git", "rev-parse", "--show-prefix"],
                cwd=str(self.current_dir),
                capture_output=True,
                text=True,
                timeout=2,
            )
            if prefix_result.returncode != 0:
                return {}
            prefix = prefix_result.stdout.strip()  # e.g. "src/ncview/"

            result = subprocess.run(
                ["git", "status", "--porcelain", "-unormal", "."],
                cwd=str(self.current_dir),
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode != 0:
                return {}
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return {}

        status_map: dict[str, str] = {}
        for line in result.stdout.splitlines():
            if len(line) < 4:
                continue
            xy = line[:2]
            filepath = line[3:]
            # Unquote git C-style quoting for paths with special chars
            if filepath.startswith('"') and filepath.endswith('"'):
                filepath = filepath[1:-1].replace('\\"', '"').replace('\\\\', '\\')
            # Strip repo-root prefix to get path relative to current dir
            if prefix and filepath.startswith(prefix):
                filepath = filepath[len(prefix):]
            # Only care about direct children of current dir
            name = filepath.split("/")[0]
            if name not in status_map:
                status_map[name] = xy
            else:
                # If a dir has mixed statuses, mark as modified
                status_map[name] = " M"
        return status_map

    def _populate_list(
        self,
        gen: int,
        entries: list[Path],
        dir_names: set[str],
        rows: list[tuple],
        keys: list[str],
        show_perms: bool,
    ) -> None:
        """Rebuild the DataTable with pre-built rows from the background thread."""
        # Discard if a newer load has already been requested
        if gen != self._load_gen:
            return
        self._entries = entries
        self._path_map.clear()
        dt = self.query_one("#file-list", DataTable)
        dt.clear(columns=True)

        dt.add_column("Name", key="name")
        if show_perms:
            dt.add_column("Perms", key="perms")
            dt.add_column("Modified", key="modified")
        dt.add_column("Size", key="size")

        # Build path map
        if self.current_dir != Path(self.current_dir.root):
            self._path_map[".."] = self.current_dir.parent
        for entry in entries:
            self._path_map[entry.name] = entry

        # Store base labels for visual-mode toggling
        self._base_labels = [row[0] for row in rows]
        self._row_keys = list(keys)

        # Exit visual mode on directory reload
        if self._visual_mode:
            self._visual_mode = False
            self._visual_anchor = -1
            self._update_visual_hint(False)

        # Batch add rows with deferred screen refresh
        with self.app.batch_update():
            for row, key in zip(rows, keys):
                dt.add_row(*row, key=key)

        sort_label = self._sort_key.value
        hidden_label = "shown" if self._show_hidden else "hidden"
        count_dirs = len(dir_names)
        count_files = len(entries) - count_dirs
        total = count_dirs + count_files
        filter_label = f" | filter:{self._filter_pattern}" if self._filter_pattern else ""
        self._base_subtitle = f"{total} items ({count_dirs} dirs, {count_files} files) | sort:{sort_label} | hidden:{hidden_label}{filter_label}"
        self._refresh_subtitle()

        # Clear search state on directory change
        self._search_query = ""
        self._search_matches = []
        self._search_index = -1
        self._update_search_hint(False)

        # Post directory changed
        self.post_message(DirectoryChanged(self.current_dir))

        # Restore cursor to previously visited directory, or default to first row
        target_row = 0
        if self._focus_name:
            for i, key in enumerate(keys):
                if key == self._focus_name:
                    target_row = i
                    break
            self._focus_name = None
        if dt.row_count > 0:
            dt.move_cursor(row=target_row)

    @on(DataTable.RowHighlighted)
    def _on_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        path = self._get_highlighted_path()
        if path is not None:
            self.post_message(FileHighlighted(path))
        if self._visual_mode:
            self._render_visual_selection()
            self._refresh_subtitle()

    def action_visual_toggle(self) -> None:
        """Enter or exit visual selection mode (vim-style)."""
        dt = self.query_one("#file-list", DataTable)
        if self._visual_mode:
            self._exit_visual_mode()
        else:
            cursor_row = dt.cursor_row
            if cursor_row is None or cursor_row < 0:
                return
            # Don't allow anchoring on ".."
            if cursor_row < len(self._row_keys) and self._row_keys[cursor_row] == "..":
                return
            self._visual_mode = True
            self._visual_anchor = cursor_row
            self._render_visual_selection()
            self._refresh_subtitle()
            self._update_visual_hint(True)

    def _exit_visual_mode(self) -> None:
        self._visual_mode = False
        self._visual_anchor = -1
        self._restore_base_labels()
        self._refresh_subtitle()
        self._update_visual_hint(False)

    def _update_visual_hint(self, active: bool) -> None:
        from ncview.widgets.status_bar import StatusBar
        try:
            self.app.query_one("#status-bar", StatusBar).visual_active = active
        except Exception:
            pass

    def _selected_range(self) -> tuple[int, int]:
        """Return (start, end) inclusive row indices for the current visual selection."""
        dt = self.query_one("#file-list", DataTable)
        cursor = dt.cursor_row if dt.cursor_row is not None else self._visual_anchor
        return (min(self._visual_anchor, cursor), max(self._visual_anchor, cursor))

    def _selected_paths(self) -> list[Path]:
        """Return paths for all currently selected rows (excluding '..')."""
        if not self._visual_mode:
            p = self._get_highlighted_path()
            return [p] if p is not None else []
        start, end = self._selected_range()
        paths: list[Path] = []
        for i in range(start, end + 1):
            if 0 <= i < len(self._row_keys):
                key = self._row_keys[i]
                if key == "..":
                    continue
                p = self._path_map.get(key)
                if p is not None:
                    paths.append(p)
        return paths

    def _render_visual_selection(self) -> None:
        """Update row labels to show selection markers for the [anchor, cursor] range."""
        if not self._base_labels:
            return
        dt = self.query_one("#file-list", DataTable)
        start, end = self._selected_range()
        for i, base in enumerate(self._base_labels):
            if start <= i <= end and i < len(self._row_keys) and self._row_keys[i] != "..":
                marked = Text("▌", style="bold #fd971f")
                marked.append(" ")
                marked.append_text(base)
                value = marked
            else:
                value = base
            try:
                dt.update_cell_at(Coordinate(i, 0), value)
            except Exception:
                pass

    def _restore_base_labels(self) -> None:
        """Reset all row labels to their unmarked form."""
        if not self._base_labels:
            return
        dt = self.query_one("#file-list", DataTable)
        for i, base in enumerate(self._base_labels):
            try:
                dt.update_cell_at(Coordinate(i, 0), base)
            except Exception:
                pass

    @on(DataTable.RowSelected)
    def _on_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle Enter key on DataTable — enter directory or open file."""
        self.action_enter_or_open()

    def _get_highlighted_path(self) -> Path | None:
        """Return the Path of the currently highlighted item."""
        dt = self.query_one("#file-list", DataTable)
        if dt.row_count == 0:
            return None
        try:
            row_key = dt.coordinate_to_cell_key(dt.cursor_coordinate).row_key.value
        except Exception:
            return None
        return self._path_map.get(row_key)

    def _navigate_to(self, path: Path) -> None:
        """Change to a new directory."""
        path = path.absolute()
        if path.is_dir() and path != self.current_dir:
            self._dir_stack.append(self.current_dir)
            # Remember current dir name so we can highlight it when going back
            if path == self.current_dir.parent:
                self._focus_name = self.current_dir.name
            else:
                self._focus_name = None
            self.current_dir = path
            self._load_directory()

    # --- Actions bound to vim keys ---

    def action_cursor_down(self) -> None:
        dt = self.query_one("#file-list", DataTable)
        dt.action_cursor_down()

    def action_cursor_up(self) -> None:
        dt = self.query_one("#file-list", DataTable)
        dt.action_cursor_up()

    def action_enter_or_open(self) -> None:
        path = self._get_highlighted_path()
        if path is None:
            return
        if path.is_dir():
            self._navigate_to(path)
        else:
            self.post_message(FileSelected(path))

    def action_parent_dir(self) -> None:
        self._navigate_to(self.current_dir.parent)

    def action_jump_top(self) -> None:
        dt = self.query_one("#file-list", DataTable)
        dt.move_cursor(row=0)

    def action_jump_bottom(self) -> None:
        dt = self.query_one("#file-list", DataTable)
        if dt.row_count > 0:
            dt.move_cursor(row=dt.row_count - 1)

    def action_toggle_hidden(self) -> None:
        self._show_hidden = not self._show_hidden
        self._load_directory()

    def action_toggle_perms(self) -> None:
        self._show_perms = not self._show_perms
        self._load_directory()

    def action_cycle_sort(self) -> None:
        keys = list(SortKey)
        idx = keys.index(self._sort_key)
        self._sort_key = keys[(idx + 1) % len(keys)]
        self._load_directory()

    def action_start_search(self) -> None:
        self._input_mode = InputMode.SEARCH
        search_input = self.query_one("#search-input", Input)
        search_input.styles.display = "block"
        search_input.value = ""
        search_input.focus()

    @on(Input.Submitted, "#search-input")
    def _on_search_submitted(self, event: Input.Submitted) -> None:
        query = event.value.lower()
        self._finish_input()
        if not query:
            self._search_query = ""
            self._search_matches = []
            self._search_index = -1
            return
        dt = self.query_one("#file-list", DataTable)
        has_parent = self.current_dir != Path(self.current_dir.root)
        offset = 1 if has_parent else 0
        # Build list of all matching row indices
        matches: list[int] = []
        if has_parent and query in "..":
            matches.append(0)
        for i, entry in enumerate(self._entries):
            if query in entry.name.lower():
                matches.append(i + offset)
        self._search_query = query
        self._search_matches = matches
        if matches:
            self._search_index = 0
            dt.move_cursor(row=matches[0])
        else:
            self._search_index = -1
        self._refresh_subtitle()
        self._update_search_hint(bool(matches))

    def action_search_next(self) -> None:
        """Jump to the next search match (n)."""
        if not self._search_matches:
            return
        self._search_index = (self._search_index + 1) % len(self._search_matches)
        dt = self.query_one("#file-list", DataTable)
        dt.move_cursor(row=self._search_matches[self._search_index])
        self._refresh_subtitle()

    def action_search_prev(self) -> None:
        """Jump to the previous search match (N)."""
        if not self._search_matches:
            return
        self._search_index = (self._search_index - 1) % len(self._search_matches)
        dt = self.query_one("#file-list", DataTable)
        dt.move_cursor(row=self._search_matches[self._search_index])
        self._refresh_subtitle()

    def _refresh_subtitle(self) -> None:
        """Rebuild border subtitle, appending search/visual info if active."""
        if self._search_matches:
            extra = f" | /{self._search_query} [{self._search_index + 1}/{len(self._search_matches)}]"
        elif self._search_query:
            extra = f" | /{self._search_query} [no matches]"
        else:
            extra = ""
        if self._visual_mode:
            count = len(self._selected_paths())
            extra += f" | VISUAL [{count}]"
        self.border_subtitle = self._base_subtitle + extra

    def _update_search_hint(self, active: bool) -> None:
        """Toggle n/N hint in the status bar."""
        from ncview.widgets.status_bar import StatusBar
        try:
            self.app.query_one("#status-bar", StatusBar).search_active = active
        except Exception:
            pass

    def action_open_editor(self) -> None:
        path = self._get_highlighted_path()
        if path is None or path.is_dir():
            return
        editor = os.environ.get("EDITOR", "vim")
        with self.app.suspend():
            subprocess.call([*shlex.split(editor), str(path)])

    def action_open_editor_path(self) -> None:
        path = self._get_highlighted_path()
        self._input_mode = InputMode.EDITOR
        editor_input = self.query_one("#editor-input", Input)
        editor_input.value = str(path) if path and not path.is_dir() else str(self.current_dir) + "/"
        editor_input.styles.display = "block"
        editor_input.focus()

    @on(Input.Submitted, "#editor-input")
    def _on_editor_submitted(self, event: Input.Submitted) -> None:
        file_path = event.value.strip()
        self._finish_input()
        if not file_path:
            return
        path = Path(file_path).absolute()
        if path.is_dir():
            self._navigate_to(path)
            return
        editor = os.environ.get("EDITOR", "vim")
        with self.app.suspend():
            subprocess.call([*shlex.split(editor), str(path)])

    def action_touch_file(self) -> None:
        self._input_mode = InputMode.TOUCH
        touch_input = self.query_one("#touch-input", Input)
        touch_input.value = str(self.current_dir) + "/"
        touch_input.styles.display = "block"
        touch_input.focus()

    @on(Input.Submitted, "#touch-input")
    def _on_touch_submitted(self, event: Input.Submitted) -> None:
        file_path = event.value.strip()
        self._finish_input()
        if not file_path:
            return
        path = Path(file_path)
        if path.exists():
            self.notify(f"Already exists: {path.name}", severity="warning")
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
            self.notify(f"Created: {path.name}", severity="information")
            self._load_directory()
        except OSError as exc:
            self.notify(f"Failed: {exc}", severity="error")

    def action_rename(self) -> None:
        """Rename the highlighted file or directory."""
        path = self._get_highlighted_path()
        if path is None:
            return
        # Don't allow renaming ".."
        dt = self.query_one("#file-list", DataTable)
        try:
            row_key = dt.coordinate_to_cell_key(dt.cursor_coordinate).row_key.value
        except Exception:
            return
        if row_key == "..":
            return
        self._input_mode = InputMode.RENAME
        self._rename_path = path
        rename_input = self.query_one("#rename-input", Input)
        rename_input.value = path.name
        rename_input.styles.display = "block"
        rename_input.focus()

    @on(Input.Submitted, "#rename-input")
    def _on_rename_submitted(self, event: Input.Submitted) -> None:
        new_name = event.value.strip()
        old_path = self._rename_path
        self._finish_input()
        if not new_name or old_path is None:
            return
        if "/" in new_name or "\\" in new_name:
            self.notify("Name cannot contain path separators", severity="error")
            return
        new_path = old_path.parent / new_name
        if new_path.exists():
            self.notify(f"Already exists: {new_name}", severity="warning")
            return
        try:
            old_path.rename(new_path)
            self.notify(f"Renamed to: {new_name}", severity="information")
            self._load_directory()
        except OSError as exc:
            self.notify(f"Rename failed: {exc}", severity="error")

    def action_mkdir(self) -> None:
        self._input_mode = InputMode.MKDIR
        mkdir_input = self.query_one("#mkdir-input", Input)
        mkdir_input.value = ""
        mkdir_input.styles.display = "block"
        mkdir_input.focus()

    @on(Input.Submitted, "#mkdir-input")
    def _on_mkdir_submitted(self, event: Input.Submitted) -> None:
        dir_name = event.value.strip()
        self._finish_input()
        if not dir_name:
            return
        new_path = self.current_dir / dir_name
        if new_path.exists():
            self.notify(f"Already exists: {dir_name}", severity="warning")
            return
        try:
            new_path.mkdir(parents=True)
            self.notify(f"Created: {dir_name}/", severity="information")
            self._load_directory()
        except OSError as exc:
            self.notify(f"Mkdir failed: {exc}", severity="error")

    def action_go_home(self) -> None:
        """Navigate to the home directory."""
        self._navigate_to(Path.home())

    def action_go_back(self) -> None:
        """Return to the previously visited directory."""
        if self._dir_stack:
            self._focus_name = self.current_dir.name
            prev = self._dir_stack.pop()
            self.current_dir = prev
            self._load_directory()

    def action_start_filter(self) -> None:
        """Open input to filter files by pattern."""
        self._input_mode = InputMode.FILTER
        filter_input = self.query_one("#filter-input", Input)
        filter_input.value = self._filter_pattern
        filter_input.styles.display = "block"
        filter_input.focus()

    @on(Input.Submitted, "#filter-input")
    def _on_filter_submitted(self, event: Input.Submitted) -> None:
        pattern = event.value.strip()
        self._finish_input()
        self._filter_pattern = pattern
        self._load_directory()

    def action_open_shell(self) -> None:
        """Drop into an interactive shell at the current directory."""
        shell = os.environ.get("SHELL", "/bin/sh")
        with self.app.suspend():
            subprocess.call([shell], cwd=str(self.current_dir))
        self._load_directory()

    def action_yank_path(self) -> None:
        """Copy the current directory path (or selected files in visual mode)."""
        if self._visual_mode:
            paths = self._selected_paths()
            if not paths:
                self.notify("No files selected", severity="warning")
                return
            text = "\n".join(str(p) for p in paths)
            hint = copy_to_clipboard(text)
            self.notify(f"Copied {len(paths)} path{'s' if len(paths) != 1 else ''}", severity="information")
            if hint:
                self.notify(hint, severity="warning")
            self._exit_visual_mode()
            return
        abs_path = str(self.current_dir)
        hint = copy_to_clipboard(abs_path)
        self.notify(f"Copied: {abs_path}", severity="information")
        if hint:
            self.notify(hint, severity="warning")

    def action_delete(self) -> None:
        """Prompt to delete the highlighted file or directory (or all selected in visual mode)."""
        from ncview.widgets.confirm_screen import ConfirmScreen

        if self._visual_mode:
            paths = self._selected_paths()
            if not paths:
                return
            count = len(paths)
            preview = ", ".join(p.name for p in paths[:3])
            if count > 3:
                preview += f", ... (+{count - 3} more)"

            def _on_result(confirmed: bool) -> None:
                if not confirmed:
                    return
                self._do_delete_many(paths)

            self.app.push_screen(
                ConfirmScreen(
                    title=f"Delete {count} items",
                    message=f"Are you sure you want to delete:\n{preview}",
                ),
                callback=_on_result,
            )
            return

        path = self._get_highlighted_path()
        if path is None:
            return
        # Don't allow deleting ".."
        dt = self.query_one("#file-list", DataTable)
        try:
            row_key = dt.coordinate_to_cell_key(dt.cursor_coordinate).row_key.value
        except Exception:
            return
        if row_key == "..":
            return

        kind = "directory" if path.is_dir() else "file"
        name = path.name

        def _on_result(confirmed: bool) -> None:
            if not confirmed:
                return
            self._do_delete(path, kind, name)

        self.app.push_screen(
            ConfirmScreen(
                title=f"Delete {kind}",
                message=f"Are you sure you want to delete '{name}'?",
            ),
            callback=_on_result,
        )

    @work(thread=True)
    def _do_delete(self, path: Path, kind: str, name: str) -> None:
        """Delete a file or directory in a background thread."""
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            self.app.call_from_thread(
                self.notify, f"Deleted {kind}: {name}", severity="information"
            )
            self.app.call_from_thread(self._load_directory)
        except OSError as exc:
            self.app.call_from_thread(
                self.notify, f"Delete failed: {exc}", severity="error"
            )

    @work(thread=True)
    def _do_delete_many(self, paths: list[Path]) -> None:
        """Delete multiple files/directories in a background thread."""
        errors: list[str] = []
        deleted = 0
        for path in paths:
            try:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
                deleted += 1
            except OSError as exc:
                errors.append(f"{path.name}: {exc}")
        if errors:
            self.app.call_from_thread(
                self.notify,
                f"Deleted {deleted}, {len(errors)} failed: {errors[0]}",
                severity="error",
            )
        else:
            self.app.call_from_thread(
                self.notify, f"Deleted {deleted} items", severity="information"
            )
        self.app.call_from_thread(self._load_directory)
