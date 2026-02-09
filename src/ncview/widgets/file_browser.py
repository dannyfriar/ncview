"""DataTable-based file browser with vim keybindings and virtual scrolling."""

from __future__ import annotations

import os
import shlex
import shutil
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
        ("y", "yank_path", "Copy path"),
        ("d", "delete", "Delete"),
    ]

    def __init__(self, start_path: Path | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.current_dir = (start_path or Path.cwd()).resolve()
        self._entries: list[Path] = []
        self._show_hidden = False
        self._sort_key = SortKey.NAME
        self._search_active = False
        self._path_map: dict[str, Path] = {}

    def compose(self):
        yield DataTable(id="file-list", cursor_type="row", show_header=False)
        yield Input(placeholder="Search...", id="search-input")

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
            entries = list(self.current_dir.iterdir())
        except PermissionError:
            entries = []

        if not self._show_hidden:
            entries = [e for e in entries if not e.name.startswith(".")]

        dirs = sorted(
            [e for e in entries if e.is_dir()],
            key=self._sort_func,
        )
        files = sorted(
            [e for e in entries if not e.is_dir()],
            key=self._sort_func,
        )
        all_entries = dirs + files

        # Pre-compute sizes on the worker thread to avoid stat() on main thread
        sizes: dict[str, int] = {}
        for entry in files:
            try:
                sizes[entry.name] = entry.stat().st_size
            except OSError:
                pass

        self.app.call_from_thread(self._populate_list, all_entries, sizes)

    def _sort_func(self, path: Path):
        if self._sort_key == SortKey.SIZE:
            try:
                return path.stat().st_size
            except OSError:
                return 0
        elif self._sort_key == SortKey.MODIFIED:
            try:
                return -path.stat().st_mtime
            except OSError:
                return 0
        return path.name.lower()

    def _populate_list(self, entries: list[Path], sizes: dict[str, int]) -> None:
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
        self.border_subtitle = f"{count_dirs} dirs, {count_files} files | sort:{sort_label} | hidden:{hidden_label}"

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
        import subprocess
        with self.app.suspend():
            subprocess.call([*shlex.split(editor), str(path)])

    def action_yank_path(self) -> None:
        """Copy the highlighted file's absolute path to the system clipboard."""
        path = self._get_highlighted_path()
        if path is None:
            return
        abs_path = str(path.resolve())
        import subprocess
        try:
            subprocess.run(["pbcopy"], input=abs_path.encode(), check=True)
        except FileNotFoundError:
            # Linux fallback
            try:
                subprocess.run(["xclip", "-selection", "clipboard"], input=abs_path.encode(), check=True)
            except FileNotFoundError:
                try:
                    subprocess.run(["xsel", "--clipboard", "--input"], input=abs_path.encode(), check=True)
                except FileNotFoundError:
                    self.notify("No clipboard tool found", severity="error")
                    return
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

