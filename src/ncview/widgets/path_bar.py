"""Breadcrumb path bar widget."""

from __future__ import annotations

import os
import subprocess
from functools import lru_cache
from pathlib import Path

from rich.text import Text
from textual import work
from textual.widget import Widget
from textual.widgets import Static


def _git_info(directory: Path) -> tuple[str | None, bool | None]:
    """Return (branch_name, is_dirty) or (None, None) if not a repo."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "-b", "-uno"],
            cwd=str(directory),
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode != 0:
            return None, None
        lines = result.stdout.splitlines()
        if not lines or not lines[0].startswith("## "):
            return None, None
        header = lines[0][3:]
        if header.startswith("No commits yet"):
            return "main", False
        if header.startswith("HEAD (no branch)"):
            branch = "HEAD"
        else:
            branch = header.split("...")[0]
        dirty = len(lines) > 1
        return branch, dirty
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None, None


@lru_cache(maxsize=1)
def _virtualenv_name() -> str | None:
    """Return the active virtualenv name, or None."""
    venv = os.environ.get("VIRTUAL_ENV")
    if venv:
        return Path(venv).name
    conda = os.environ.get("CONDA_DEFAULT_ENV")
    if conda:
        return conda
    return None


class PathBar(Widget):
    """Displays the current directory as a breadcrumb trail."""

    DEFAULT_CSS = """
    PathBar {
        height: 1;
        dock: top;
        background: #0d0e0c;
        color: #f8f8f2;
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

    def _render_bar(
        self, path: Path, branch: str | None = None, dirty: bool | None = None,
    ) -> Text:
        """Build the bar text from path and optional git info."""
        parts = path.parts
        text = Text()
        for i, part in enumerate(parts):
            if i > 0:
                text.append(" / ", style="#75715e")
            if i == len(parts) - 1:
                text.append(part, style="bold #a6e22e")
            else:
                text.append(part, style="#75715e")

        tags = Text()
        venv = _virtualenv_name()
        if venv:
            tags.append("\ue73c ", style="bold #66d9ef")  # nf-dev-python
            tags.append(venv, style="bold #66d9ef")
        if branch:
            if venv:
                tags.append("  ", style="#75715e")
            # nf-dev-git_branch icon
            tags.append("\ue725 ", style="bold #ae81ff")
            tags.append(branch, style="bold #ae81ff")
            if dirty is True:
                tags.append(" \u25cf", style="bold #fd971f")  # dirty: orange
            elif dirty is False:
                tags.append(" \u25cf", style="bold #a6e22e")  # clean: green

        if tags:
            text.append("  ")
            text.append(tags)
        return text

    def update_path(self, path: Path) -> None:
        self._path = path.resolve()
        # Render immediately without git info (no latency)
        text = self._render_bar(self._path)
        try:
            self.query_one("#path-text", Static).update(text)
        except Exception:
            pass
        # Fetch git info in background, then re-render
        self._fetch_git_info(self._path)

    @work(thread=True, exclusive=True)
    def _fetch_git_info(self, path: Path) -> None:
        branch, dirty = _git_info(path)
        if path == self._path:
            text = self._render_bar(path, branch=branch, dirty=dirty)
            self.app.call_from_thread(self._set_text, text)

    def _set_text(self, text: Text) -> None:
        try:
            self.query_one("#path-text", Static).update(text)
        except Exception:
            pass
