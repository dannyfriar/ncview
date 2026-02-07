"""Viewer registry — maps file extensions to viewer classes."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ncview.viewers.base import BaseViewer


class ViewerRegistry:
    """Maps file extensions to viewer widget classes."""

    def __init__(self) -> None:
        self._viewers: list[type[BaseViewer]] = []

    def register(self, viewer_cls: type[BaseViewer]) -> type[BaseViewer]:
        """Register a viewer class."""
        self._viewers.append(viewer_cls)
        return viewer_cls

    def get_viewer(self, path: Path) -> type[BaseViewer]:
        """Return the best viewer class for a given file path."""
        ext = path.suffix.lower()
        best: type[BaseViewer] | None = None
        best_priority = float("-inf")

        for viewer_cls in self._viewers:
            if ext in viewer_cls.supported_extensions():
                p = viewer_cls.priority()
                if p > best_priority:
                    best = viewer_cls
                    best_priority = p

        if best is None:
            # Return fallback
            from ncview.viewers.fallback_viewer import FallbackViewer

            return FallbackViewer

        return best


# Singleton registry
registry = ViewerRegistry()
