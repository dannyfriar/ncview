"""Abstract base viewer."""

from __future__ import annotations

from abc import abstractmethod
from pathlib import Path

from textual.widget import Widget


class BaseViewer(Widget):
    """Base class for all file viewers."""

    DEFAULT_CSS = """
    BaseViewer {
        height: 1fr;
        width: 1fr;
    }
    """

    def __init__(self, path: Path, **kwargs) -> None:
        super().__init__(**kwargs)
        self.path = path

    @staticmethod
    @abstractmethod
    def supported_extensions() -> set[str]:
        """Return set of supported file extensions (e.g. {'.txt', '.py'})."""
        ...

    @staticmethod
    def priority() -> int:
        """Higher priority wins when multiple viewers match an extension."""
        return 0

    @abstractmethod
    async def load_content(self) -> None:
        """Load file content. Called after mount."""
        ...

    async def on_mount(self) -> None:
        """Trigger content loading after mount."""
        await self.load_content()
