"""Main Textual application for ncview."""

from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Header

from ncview.utils.file_types import registry
from ncview.viewers.fallback_viewer import FallbackViewer
from ncview.viewers.json_viewer import JsonViewer
from ncview.viewers.markdown_viewer import MarkdownViewer
from ncview.viewers.parquet_viewer import ParquetViewer
from ncview.viewers.text_viewer import TextViewer
from ncview.widgets.file_browser import DirectoryChanged, FileBrowser, FileSelected
from ncview.widgets.path_bar import PathBar
from ncview.widgets.preview_panel import PreviewPanel
from ncview.widgets.status_bar import StatusBar

# Register viewers
registry.register(TextViewer)
registry.register(ParquetViewer)
registry.register(JsonViewer)
registry.register(MarkdownViewer)
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
        ("1", "viewer_tab('1')", "Tab 1"),
        ("2", "viewer_tab('2')", "Tab 2"),
        ("3", "viewer_tab('3')", "Tab 3"),
    ]

    def __init__(self, start_path: Path | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._start_path = start_path or Path.cwd()
        self._preview_path: Path | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield PathBar(self._start_path, id="path-bar")
        yield FileBrowser(self._start_path, id="browser")
        yield PreviewPanel(id="preview")
        yield StatusBar(id="status-bar")

    def on_mount(self) -> None:
        browser = self.query_one("#browser", FileBrowser)
        browser.border_title = "Files"
        browser.focus()
        preview = self.query_one("#preview", PreviewPanel)
        preview.border_title = "Preview"

    def _preview_is_open(self) -> bool:
        return self.query_one("#preview", PreviewPanel).has_class("visible")

    @on(FileSelected)
    async def _on_file_selected(self, event: FileSelected) -> None:
        """User pressed Enter/l on a file — show preview."""
        if not event.path.is_file():
            return
        preview = self.query_one("#preview", PreviewPanel)
        browser = self.query_one("#browser", FileBrowser)

        await preview.show_file(event.path)
        self._preview_path = event.path

        # Hide browser, show preview full-width
        browser.styles.display = "none"
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
        """Return from preview to browser."""
        preview = self.query_one("#preview", PreviewPanel)
        browser = self.query_one("#browser", FileBrowser)

        await preview.clear()
        self._preview_path = None

        preview.remove_class("visible")
        browser.styles.display = "block"
        browser.query_one("#file-list").focus()
        self.query_one("#status-bar", StatusBar).mode = "browser"

    async def action_close_preview(self) -> None:
        if self._preview_is_open():
            await self._close_preview()

    async def action_close_preview_or_parent(self) -> None:
        """h/backspace: close preview if open, otherwise go to parent dir."""
        if self._preview_is_open():
            await self._close_preview()
        # If preview is not open, let the FileBrowser handle h/backspace itself

    def action_show_pins(self) -> None:
        """Show the pinned directories popup."""
        if self._preview_is_open():
            return
        from ncview.widgets.pins_screen import PinsScreen

        def _on_pin_selected(path: Path | None) -> None:
            if path is not None:
                browser = self.query_one("#browser", FileBrowser)
                browser._navigate_to(path)

        self.push_screen(PinsScreen(), callback=_on_pin_selected)

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
        """Switch parquet viewer tabs with 1/2/3 keys."""
        if not self._preview_is_open():
            return
        from ncview.viewers.parquet_viewer import ParquetViewer
        from textual.widgets import TabbedContent, DataTable
        try:
            pv = self.query_one(ParquetViewer)
        except Exception:
            return
        tc = pv.query_one(TabbedContent)
        tab_map = {"1": "data-tab", "2": "schema-tab", "3": "stats-tab"}
        tab_id = tab_map.get(tab_num)
        if tab_id:
            tc.active = tab_id
            # Refocus DataTable when switching to data tab
            if tab_id == "data-tab":
                try:
                    pv.query_one(DataTable).focus()
                except Exception:
                    pass

    @on(DirectoryChanged)
    def _on_directory_changed(self, event: DirectoryChanged) -> None:
        path_bar = self.query_one("#path-bar", PathBar)
        path_bar.update_path(event.path)


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
