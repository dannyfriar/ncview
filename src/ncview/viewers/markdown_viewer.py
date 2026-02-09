"""Markdown viewer — rendered markdown with Rich."""

from __future__ import annotations

from rich.markdown import Markdown
from rich.text import Text
from textual.widgets import Static

from ncview.viewers.base import BaseViewer

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


class MarkdownViewer(BaseViewer):
    """Displays markdown files rendered with Rich."""

    DEFAULT_CSS = """
    MarkdownViewer {
        height: 1fr;
        overflow-y: auto;
    }
    MarkdownViewer > Static {
        width: 1fr;
    }
    """

    @staticmethod
    def supported_extensions() -> set[str]:
        return {".md", ".markdown", ".mkd", ".mdx"}

    @staticmethod
    def priority() -> int:
        return 5  # Higher than TextViewer (-1) for .md files

    def compose(self):
        yield Static(id="md-content")

    async def load_content(self) -> None:
        widget = self.query_one("#md-content", Static)
        try:
            file_size = self.path.stat().st_size
            if file_size > MAX_FILE_SIZE:
                widget.update(Text(
                    f"File too large ({file_size / 1024 / 1024:.1f} MB > {MAX_FILE_SIZE // 1024 // 1024} MB limit)",
                    style="bold red",
                ))
                return
            raw = self.path.read_text(errors="replace")
            widget.update(Markdown(raw))
        except Exception as e:
            widget.update(Text(f"Error reading file: {e}", style="bold red"))
