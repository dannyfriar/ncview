"""Breadcrumb path bar widget."""

from __future__ import annotations

from pathlib import Path

from rich.text import Text
from textual.widget import Widget
from textual.widgets import Static


class PathBar(Widget):
    """Displays the current directory as a breadcrumb trail."""

    DEFAULT_CSS = """
    PathBar {
        height: 1;
        dock: top;
        background: $primary-background;
        padding: 0 1;
    }
    PathBar > Static {
        width: 1fr;
    }
    """

    def __init__(self, path: Path | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._path = path or Path.cwd()

    def compose(self):
        yield Static(id="path-text")

    def on_mount(self) -> None:
        self.update_path(self._path)

    def update_path(self, path: Path) -> None:
        self._path = path.resolve()
        parts = self._path.parts
        text = Text()
        for i, part in enumerate(parts):
            if i > 0:
                text.append(" / ", style="dim")
            if i == len(parts) - 1:
                text.append(part, style="bold cyan")
            else:
                text.append(part, style="dim white")
        try:
            self.query_one("#path-text", Static).update(text)
        except Exception:
            pass
