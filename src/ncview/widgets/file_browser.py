"""DataTable-based file browser with vim keybindings and virtual scrolling."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from enum import Enum
from pathlib import Path

from rich.text import Text
from textual import on, work
from textual.events import Key
from textual.message import Message
from textual.widget import Widget
from textual.widgets import DataTable, Input

from ncview.utils.file_info import file_icon, human_size


class SortKey(Enum):
    NAME = "name"
    SIZE = "size"
    MODIFIED = "modified"


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
        ("period", "toggle_hidden", "Toggle hidden"),
        ("s", "cycle_sort", "Cycle sort"),
        ("slash", "start_search", "Search"),
        ("e", "open_editor", "Editor"),
        ("E", "open_editor_path", "Edit path"),  # noqa: E741
        ("y", "yank_path", "Copy path"),
        ("d", "delete", "Delete"),
        ("t", "touch_file", "Touch"),
        ("r", "rename", "Rename"),
        ("M", "mkdir", "Mkdir"),  # noqa: E741
    ]

    def __init__(self, start_path: Path | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.current_dir = (start_path or Path.cwd()).resolve()
        self._entries: list[Path] = []
        self._show_hidden = False
        self._sort_key = SortKey.NAME
        self._search_active = False
        self._editor_active = False
        self._touch_active = False
        self._rename_active = False
        self._rename_path: Path | None = None
        self._mkdir_active = False
        self._path_map: dict[str, Path] = {}

    def compose(self):
        yield DataTable(id="file-list", cursor_type="row", show_header=False)
        yield Input(placeholder="Search...", id="search-input")
        yield Input(placeholder="File path to edit...", id="editor-input")
        yield Input(placeholder="New file name...", id="touch-input")
        yield Input(placeholder="Rename to...", id="rename-input")
        yield Input(placeholder="New directory name...", id="mkdir-input")

    def on_mount(self) -> None:
        self._load_directory()

    def on_key(self, event: Key) -> None:
        """Intercept keys before DataTable eats them."""
        if self._search_active:
            if event.key == "escape":
                event.prevent_default()
                event.stop()
                self._finish_search()
            return
        if self._editor_active:
            if event.key == "escape":
                event.prevent_default()
                event.stop()
                self._finish_editor()
            return
        if self._touch_active:
            if event.key == "escape":
                event.prevent_default()
                event.stop()
                self._finish_touch()
            return
        if self._rename_active:
            if event.key == "escape":
                event.prevent_default()
                event.stop()
                self._finish_rename()
            return
        if self._mkdir_active:
            if event.key == "escape":
                event.prevent_default()
                event.stop()
                self._finish_mkdir()
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

    @work(thread=True, exclusive=True)
    def _load_directory(self) -> None:
        """Load directory contents in a background thread."""
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

        # Cache stat results once per entry for sorting and sizes
        stat_cache: dict[str, os.stat_result] = {}
        if self._sort_key in (SortKey.SIZE, SortKey.MODIFIED):
            for e in scan:
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

        # Build Path lists and sizes dict
        dirs = [Path(e.path) for e in dir_entries]
        files = [Path(e.path) for e in file_entries]
        all_entries = dirs + files

        sizes: dict[str, int] = {}
        for e in file_entries:
            try:
                st = stat_cache.get(e.name) or e.stat(follow_symlinks=True)
                sizes[e.name] = st.st_size
            except OSError:
                pass

        # Git status — only if we're in a git repo, with a timeout
        git_status = self._get_git_status()

        self.app.call_from_thread(self._populate_list, all_entries, sizes, git_status)

    def _get_git_status(self) -> dict[str, str]:
        """Get git status for files in the current directory. Returns empty dict if not a repo."""
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain", "-uall", "."],
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
            # Strip leading quotes from paths with special chars
            if filepath.startswith('"') and filepath.endswith('"'):
                filepath = filepath[1:-1]
            # Only care about direct children of current dir
            name = filepath.split("/")[0]
            if name not in status_map:
                status_map[name] = xy
            else:
                # If a dir has mixed statuses, mark as modified
                status_map[name] = " M"
        return status_map

    def _populate_list(self, entries: list[Path], sizes: dict[str, int], git_status: dict[str, str] | None = None) -> None:
        """Rebuild the DataTable with current entries."""
        self._entries = entries
        self._path_map.clear()
        dt = self.query_one("#file-list", DataTable)
        dt.clear(columns=True)

        dt.add_column("Name", key="name")
        dt.add_column("Size", key="size")

        # Add parent directory entry
        if self.current_dir != Path(self.current_dir.root):
            label = Text()
            label.append("\uf07b ", style="bold #e6db74")
            label.append("..", style="bold #e6db74")
            dt.add_row(label, "", key="..")
            self._path_map[".."] = self.current_dir.parent

        for entry in entries:
            label = Text()
            # Git status marker
            if git_status and entry.name in git_status:
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
            elif git_status is not None:
                label.append("  ")
            icon = file_icon(entry)
            label.append(f"{icon} ")
            if entry.is_dir():
                label.append(entry.name + "/", style="bold #66d9ef")
                size_text = ""
            else:
                label.append(entry.name, style="#f8f8f2")
                size_text = human_size(sizes[entry.name]) if entry.name in sizes else ""
            dt.add_row(label, size_text, key=entry.name)
            self._path_map[entry.name] = entry

        sort_label = self._sort_key.value
        hidden_label = "shown" if self._show_hidden else "hidden"
        count_dirs = sum(1 for e in entries if e.is_dir())
        count_files = len(entries) - count_dirs
        total = count_dirs + count_files
        self.border_subtitle = f"{total} items ({count_dirs} dirs, {count_files} files) | sort:{sort_label} | hidden:{hidden_label}"

        # Post directory changed
        self.post_message(DirectoryChanged(self.current_dir))

        # Auto-highlight first row
        if dt.row_count > 0:
            dt.move_cursor(row=0)

    @on(DataTable.RowHighlighted)
    def _on_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        path = self._get_highlighted_path()
        if path is not None:
            self.post_message(FileHighlighted(path))

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
        path = path.resolve()
        if path.is_dir():
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

    def action_cycle_sort(self) -> None:
        keys = list(SortKey)
        idx = keys.index(self._sort_key)
        self._sort_key = keys[(idx + 1) % len(keys)]
        self._load_directory()

    def action_start_search(self) -> None:
        search_input = self.query_one("#search-input", Input)
        search_input.styles.display = "block"
        search_input.value = ""
        search_input.focus()
        self._search_active = True

    @on(Input.Submitted, "#search-input")
    def _on_search_submitted(self, event: Input.Submitted) -> None:
        query = event.value.lower()
        self._finish_search()
        if not query:
            return
        # Check ".." entry first
        dt = self.query_one("#file-list", DataTable)
        has_parent = self.current_dir != Path(self.current_dir.root)
        if has_parent and query in "..":
            dt.move_cursor(row=0)
            return
        offset = 1 if has_parent else 0
        for i, entry in enumerate(self._entries):
            if query in entry.name.lower():
                dt.move_cursor(row=i + offset)
                break

    def _finish_search(self) -> None:
        search_input = self.query_one("#search-input", Input)
        search_input.styles.display = "none"
        self._search_active = False
        self.query_one("#file-list", DataTable).focus()

    def action_open_editor(self) -> None:
        path = self._get_highlighted_path()
        if path is None or path.is_dir():
            return
        editor = os.environ.get("EDITOR", "vim")
        with self.app.suspend():
            subprocess.call([*shlex.split(editor), str(path)])

    def action_open_editor_path(self) -> None:
        path = self._get_highlighted_path()
        self._editor_active = True
        editor_input = self.query_one("#editor-input", Input)
        editor_input.value = str(path) if path and not path.is_dir() else str(self.current_dir) + "/"
        editor_input.styles.display = "block"
        editor_input.focus()

    @on(Input.Submitted, "#editor-input")
    def _on_editor_submitted(self, event: Input.Submitted) -> None:
        file_path = event.value.strip()
        self._finish_editor()
        if not file_path:
            return
        path = Path(file_path).resolve()
        if path.is_dir():
            self._navigate_to(path)
            return
        editor = os.environ.get("EDITOR", "vim")
        with self.app.suspend():
            subprocess.call([*shlex.split(editor), str(path)])

    def _finish_editor(self) -> None:
        self._editor_active = False
        self.query_one("#editor-input", Input).styles.display = "none"
        self.query_one("#file-list", DataTable).focus()

    def action_touch_file(self) -> None:
        self._touch_active = True
        touch_input = self.query_one("#touch-input", Input)
        touch_input.value = str(self.current_dir) + "/"
        touch_input.styles.display = "block"
        touch_input.focus()

    @on(Input.Submitted, "#touch-input")
    def _on_touch_submitted(self, event: Input.Submitted) -> None:
        file_path = event.value.strip()
        self._finish_touch()
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

    def _finish_touch(self) -> None:
        self._touch_active = False
        self.query_one("#touch-input", Input).styles.display = "none"
        self.query_one("#file-list", DataTable).focus()

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
        self._rename_active = True
        self._rename_path = path
        rename_input = self.query_one("#rename-input", Input)
        rename_input.value = path.name
        rename_input.styles.display = "block"
        rename_input.focus()

    @on(Input.Submitted, "#rename-input")
    def _on_rename_submitted(self, event: Input.Submitted) -> None:
        new_name = event.value.strip()
        old_path = self._rename_path
        self._finish_rename()
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

    def _finish_rename(self) -> None:
        self._rename_active = False
        self._rename_path = None
        self.query_one("#rename-input", Input).styles.display = "none"
        self.query_one("#file-list", DataTable).focus()

    def action_mkdir(self) -> None:
        self._mkdir_active = True
        mkdir_input = self.query_one("#mkdir-input", Input)
        mkdir_input.value = ""
        mkdir_input.styles.display = "block"
        mkdir_input.focus()

    @on(Input.Submitted, "#mkdir-input")
    def _on_mkdir_submitted(self, event: Input.Submitted) -> None:
        dir_name = event.value.strip()
        self._finish_mkdir()
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

    def _finish_mkdir(self) -> None:
        self._mkdir_active = False
        self.query_one("#mkdir-input", Input).styles.display = "none"
        self.query_one("#file-list", DataTable).focus()

    def action_yank_path(self) -> None:
        """Copy the highlighted file's absolute path to the system clipboard."""
        path = self._get_highlighted_path()
        if path is None:
            return
        abs_path = str(path.resolve())
        import base64
        import sys
        # OSC 52 escape sequence — works over SSH, handled by the local terminal
        encoded = base64.b64encode(abs_path.encode()).decode()
        sys.stdout.write(f"\033]52;c;{encoded}\a")
        sys.stdout.flush()
        self.notify(f"Copied: {abs_path}", severity="information")

    def action_delete(self) -> None:
        """Prompt to delete the highlighted file or directory."""
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

        from ncview.widgets.confirm_screen import ConfirmScreen

        def _on_result(confirmed: bool) -> None:
            if not confirmed:
                return
            try:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
                self.notify(f"Deleted {kind}: {name}", severity="information")
                self._load_directory()
            except OSError as exc:
                self.notify(f"Delete failed: {exc}", severity="error")

        self.app.push_screen(
            ConfirmScreen(
                title=f"Delete {kind}",
                message=f"Are you sure you want to delete '{name}'?",
            ),
            callback=_on_result,
        )

