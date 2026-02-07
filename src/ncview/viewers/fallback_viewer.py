"""Fallback viewer — shows file metadata for unknown/binary files."""

from __future__ import annotations

from pathlib import Path

from rich.table import Table
from textual.widgets import Static

from ncview.utils.file_info import file_metadata
from ncview.viewers.base import BaseViewer


class FallbackViewer(BaseViewer):
    """Shows file metadata when no specialized viewer matches."""

    DEFAULT_CSS = """
    FallbackViewer {
        height: 1fr;
        padding: 1 2;
    }
    """

    @staticmethod
    def supported_extensions() -> set[str]:
        return set()

    @staticmethod
    def priority() -> int:
        return -100

    def compose(self):
        yield Static(id="fallback-content")

    async def load_content(self) -> None:
        meta = file_metadata(self.path)
        table = Table(title="File Info", show_header=False, expand=True)
        table.add_column("Key", style="bold cyan", ratio=1)
        table.add_column("Value", ratio=3)
        for key, value in meta.items():
            table.add_row(key, value)
        self.query_one("#fallback-content", Static).update(table)
