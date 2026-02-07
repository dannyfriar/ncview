"""Preview panel — swaps viewer widgets based on selected file."""

from __future__ import annotations

from pathlib import Path

from textual.containers import VerticalScroll
from textual.widget import Widget

from ncview.utils.file_types import registry
from ncview.viewers.base import BaseViewer


class PreviewPanel(Widget):
    """Hosts the currently active file viewer."""

    DEFAULT_CSS = """
    PreviewPanel {
        height: 1fr;
        width: 1fr;
    }
    PreviewPanel > VerticalScroll {
        height: 1fr;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._current_viewer: BaseViewer | None = None
        self._current_path: Path | None = None

    def compose(self):
        yield VerticalScroll(id="preview-scroll")

    async def show_file(self, path: Path) -> None:
        """Load the appropriate viewer for the given file."""
        if path.is_dir():
            return
        self._current_path = path

        # Remove old viewer
        if self._current_viewer is not None:
            await self._current_viewer.remove()
            self._current_viewer = None

        # Create and mount new viewer
        viewer_cls = registry.get_viewer(path)
        viewer = viewer_cls(path)
        self._current_viewer = viewer
        scroll = self.query_one("#preview-scroll", VerticalScroll)
        await scroll.mount(viewer)

        self.border_title = f"Preview: {path.name}"

    async def clear(self) -> None:
        """Remove current viewer."""
        if self._current_viewer is not None:
            await self._current_viewer.remove()
            self._current_viewer = None
            self._current_path = None
