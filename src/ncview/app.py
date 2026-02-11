"""Main Textual application for ncview."""

from __future__ import annotations

from pathlib import Path

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Header

from ncview.utils.file_types import registry
from ncview.utils.history import add_to_history
from ncview.utils.pins import add_pin
from ncview.viewers.csv_viewer import CsvViewer
from ncview.viewers.fallback_viewer import FallbackViewer
from ncview.viewers.json_viewer import JsonViewer
from ncview.viewers.markdown_viewer import MarkdownViewer
from ncview.viewers.parquet_viewer import ParquetViewer
from ncview.viewers.text_viewer import TextViewer
from ncview.viewers.toml_viewer import TomlViewer
from ncview.viewers.yaml_viewer import YamlViewer
from ncview.widgets.file_browser import (
    DirectoryChanged,
    FileBrowser,
    FileHighlighted,
    FileSelected,
)
from ncview.widgets.path_bar import PathBar
from ncview.widgets.preview_panel import PreviewPanel
from ncview.widgets.status_bar import StatusBar

# Register viewers
registry.register(TextViewer)
registry.register(ParquetViewer)
registry.register(CsvViewer)
registry.register(JsonViewer)
registry.register(MarkdownViewer)
registry.register(YamlViewer)
registry.register(TomlViewer)
registry.register(FallbackViewer)


class NcviewApp(App):
    """Terminal file browser with vim keybindings."""

    TITLE = "ncview"
    CSS_PATH = "ncview.tcss"

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("ctrl+c", "quit", "Quit"),
        ("escape", "close_preview", "Back"),
        ("h", "close_preview_or_parent", "Back"),
        ("backspace", "close_preview_or_parent", "Back"),
        ("left", "close_preview_or_parent", "Back"),
        ("j", "preview_scroll_down", "Down"),
        ("k", "preview_scroll_up", "Up"),
        ("ctrl+d", "preview_page_down", "Page down"),
        ("ctrl+u", "preview_page_up", "Page up"),
        ("g", "preview_scroll_top", "Top"),
        ("G", "preview_scroll_bottom", "Bottom"),
        ("e", "preview_open_editor", "Editor"),
        ("p", "show_pins", "Pins"),
        ("P", "toggle_split", "Split preview"),  # noqa: E741
        ("H", "show_history", "History"),  # noqa: E741
        ("i", "open_ipython", "IPython"),
        ("1", "viewer_tab('1')", "Tab 1"),
        ("2", "viewer_tab('2')", "Tab 2"),
        ("3", "viewer_tab('3')", "Tab 3"),
    ]

    def __init__(self, start_path: Path | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._start_path = start_path or Path.cwd()
        self._preview_path: Path | None = None
        self._split_view = False
        self._split_pending_path: Path | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield PathBar(self._start_path, id="path-bar")
        with Horizontal(id="main-content"):
            yield FileBrowser(self._start_path, id="browser")
            yield PreviewPanel(id="preview")
        yield StatusBar(id="status-bar")

    def on_mount(self) -> None:
        # Ensure Home pin exists
        add_pin(str(Path.home()), name="\uf015 Home")
        browser = self.query_one("#browser", FileBrowser)
        browser.border_title = "Files"
        browser.focus()
        preview = self.query_one("#preview", PreviewPanel)
        preview.border_title = "Preview"

    def _preview_is_open(self) -> bool:
        """True when in full-screen preview mode (not split)."""
        return self.query_one("#preview", PreviewPanel).has_class("visible")

    # --- Split preview ---

    async def action_toggle_split(self) -> None:
        """Toggle the split preview pane."""
        if self._preview_is_open():
            return
        self._split_view = not self._split_view
        preview = self.query_one("#preview", PreviewPanel)
        browser = self.query_one("#browser", FileBrowser)
        if self._split_view:
            browser.styles.width = "45%"
            preview.styles.display = "block"
            preview.styles.width = "55%"
            # Load preview for currently highlighted file
            path = browser._get_highlighted_path()
            if path and path.is_file():
                self._split_pending_path = path
                self._debounce_split_preview()
        else:
            await preview.clear()
            browser.styles.width = "1fr"
            preview.styles.display = "none"
            preview.styles.width = "1fr"
            browser.query_one("#file-list").focus()

    @on(FileHighlighted)
    def _on_file_highlighted(self, event: FileHighlighted) -> None:
        """In split mode, update the preview as the cursor moves."""
        if not self._split_view or self._preview_is_open():
            return
        if not event.path.is_file():
            return
        self._split_pending_path = event.path
        self._debounce_split_preview()

    @work(exclusive=True, group="split-preview")
    async def _debounce_split_preview(self) -> None:
        """Load the split preview after a short debounce."""
        import asyncio
        await asyncio.sleep(0.1)
        path = self._split_pending_path
        if path and path.is_file() and self._split_view and not self._preview_is_open():
            preview = self.query_one("#preview", PreviewPanel)
            await preview.show_file(path)

    # --- Full-screen preview ---

    @on(FileSelected)
    async def _on_file_selected(self, event: FileSelected) -> None:
        """User pressed Enter/l on a file — show full-screen preview."""
        if not event.path.is_file():
            return
        preview = self.query_one("#preview", PreviewPanel)
        browser = self.query_one("#browser", FileBrowser)

        await preview.show_file(event.path)
        self._preview_path = event.path

        # Hide browser, show preview full-width
        browser.styles.display = "none"
        preview.styles.display = "block"
        preview.styles.width = "1fr"
        preview.add_class("visible")
        self.query_one("#status-bar", StatusBar).mode = "preview"

        # Focus the right widget so vim keys work
        from textual.widgets import DataTable
        from ncview.viewers.json_viewer import JsonTree
        try:
            dt = preview.query_one(DataTable)
            dt.focus()
        except Exception:
            try:
                jt = preview.query_one(JsonTree)
                jt.focus()
            except Exception:
                preview.query_one("#preview-scroll", VerticalScroll).focus()

    async def _close_preview(self) -> None:
        """Return from full-screen preview to browser (or split view)."""
        preview = self.query_one("#preview", PreviewPanel)
        browser = self.query_one("#browser", FileBrowser)
        self._preview_path = None
        preview.remove_class("visible")

        if self._split_view:
            # Return to split layout
            browser.styles.display = "block"
            browser.styles.width = "45%"
            preview.styles.width = "55%"
            # Update preview for currently highlighted file
            path = browser._get_highlighted_path()
            if path and path.is_file():
                self._split_pending_path = path
                self._debounce_split_preview()
        else:
            # Return to browser-only
            await preview.clear()
            browser.styles.display = "block"
            browser.styles.width = "1fr"
            preview.styles.display = "none"
            preview.styles.width = "1fr"

        browser.query_one("#file-list").focus()
        self.query_one("#status-bar", StatusBar).mode = "browser"

    async def action_close_preview(self) -> None:
        if self._preview_is_open():
            await self._close_preview()
        elif self._split_view:
            await self.action_toggle_split()

    async def action_close_preview_or_parent(self) -> None:
        """h/backspace: close preview if open, otherwise go to parent dir."""
        if self._preview_is_open():
            await self._close_preview()
        # If preview is not open, let the FileBrowser handle h/backspace itself

    # --- Other actions ---

    def action_show_pins(self) -> None:
        """Show the pinned directories popup."""
        if self._preview_is_open():
            return
        from ncview.widgets.pins_screen import PinsScreen

        browser = self.query_one("#browser", FileBrowser)

        def _on_pin_selected(path: Path | None) -> None:
            if path is not None:
                browser._navigate_to(path)

        self.push_screen(PinsScreen(current_dir=browser.current_dir), callback=_on_pin_selected)

    def action_open_ipython(self) -> None:
        """Open an IPython shell in the current browsed directory."""
        if self._preview_is_open():
            return
        import shutil
        import subprocess
        ipython = shutil.which("ipython")
        if not ipython:
            self.notify("ipython not found on PATH", severity="error")
            return
        browser = self.query_one("#browser", FileBrowser)
        with self.suspend():
            subprocess.call([ipython], cwd=str(browser.current_dir))

    def action_preview_scroll_down(self) -> None:
        if self._preview_is_open():
            self.query_one("#preview-scroll", VerticalScroll).scroll_down()

    def action_preview_scroll_up(self) -> None:
        if self._preview_is_open():
            self.query_one("#preview-scroll", VerticalScroll).scroll_up()

    def action_preview_page_down(self) -> None:
        if self._preview_is_open():
            self.query_one("#preview-scroll", VerticalScroll).scroll_page_down()

    def action_preview_page_up(self) -> None:
        if self._preview_is_open():
            self.query_one("#preview-scroll", VerticalScroll).scroll_page_up()

    def action_preview_scroll_top(self) -> None:
        if self._preview_is_open():
            self.query_one("#preview-scroll", VerticalScroll).scroll_home()

    def action_preview_scroll_bottom(self) -> None:
        if self._preview_is_open():
            self.query_one("#preview-scroll", VerticalScroll).scroll_end()

    async def action_preview_open_editor(self) -> None:
        if not self._preview_is_open() or self._preview_path is None:
            return
        import os
        import shlex
        import subprocess
        editor = os.environ.get("EDITOR", "vim")
        with self.suspend():
            subprocess.call([*shlex.split(editor), str(self._preview_path)])
        await self._close_preview()

    def action_viewer_tab(self, tab_num: str) -> None:
        """Switch viewer tabs with 1/2/3 keys (parquet and CSV viewers)."""
        if not self._preview_is_open():
            return
        from textual.widgets import TabbedContent, DataTable
        # Find any viewer with tabbed content
        preview = self.query_one("#preview", PreviewPanel)
        try:
            tc = preview.query_one(TabbedContent)
        except Exception:
            return
        # Map tab numbers to tab IDs — try parquet first, then CSV
        pq_map = {"1": "data-tab", "2": "schema-tab", "3": "stats-tab"}
        csv_map = {"1": "csv-data-tab", "2": "csv-schema-tab", "3": "csv-stats-tab"}
        tab_id = pq_map.get(tab_num)
        if tab_id:
            try:
                tc.active = tab_id
            except Exception:
                # Not a parquet viewer, try CSV tab IDs
                tab_id = csv_map.get(tab_num)
                if tab_id:
                    try:
                        tc.active = tab_id
                    except Exception:
                        return
        # Refocus DataTable when switching to data tab
        if tab_num == "1":
            try:
                preview.query_one(DataTable).focus()
            except Exception:
                pass

    def action_show_history(self) -> None:
        """Show the directory history popup."""
        if self._preview_is_open():
            return
        from ncview.widgets.history_screen import HistoryScreen

        browser = self.query_one("#browser", FileBrowser)

        def _on_selected(path: Path | None) -> None:
            if path is not None:
                browser._navigate_to(path)

        self.push_screen(HistoryScreen(), callback=_on_selected)

    @on(DirectoryChanged)
    def _on_directory_changed(self, event: DirectoryChanged) -> None:
        path_bar = self.query_one("#path-bar", PathBar)
        path_bar.update_path(event.path)
        add_to_history(str(event.path))


def run(start: str = ".") -> None:
    """Run the ncview app."""
    path = Path(start).resolve()
    if not path.exists():
        import sys
        print(f"Error: {path} does not exist", file=sys.stderr)
        sys.exit(1)
    if path.is_file():
        path = path.parent
    app = NcviewApp(start_path=path)
    app.run()
