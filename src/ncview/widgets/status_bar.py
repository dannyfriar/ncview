"""Custom status bar with grouped keybinding hints."""

from __future__ import annotations

from rich.text import Text
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static


class StatusBar(Widget):
    """Compact footer showing keybindings grouped by category."""

    DEFAULT_CSS = """
    StatusBar {
        dock: bottom;
        height: 1;
        background: $primary-background;
        padding: 0 1;
    }
    StatusBar > Static {
        width: 1fr;
    }
    """

    mode = reactive("browser")

    _BROWSER_HINTS = [
        ("Nav", [("j/k", "\u2195"), ("h/l", "\u2194"), ("g/G", "top/end")]),
        ("Actions", [("Enter", "open"), ("e", "edit"), ("y", "copy"), ("d", "delete")]),
        ("Filter", [("/", "search"), (".", "hidden"), ("s", "sort")]),
        ("App", [("q", "quit")]),
    ]

    _PREVIEW_HINTS = [
        ("Nav", [("j/k", "scroll"), ("\u2303d/\u2303u", "page"), ("g/G", "top/end")]),
        ("Actions", [("e", "edit"), ("h/Esc", "close")]),
        ("Tabs", [("1/2/3", "switch")]),
        ("App", [("q", "quit")]),
    ]

    def compose(self):
        yield Static(id="status-text")

    def on_mount(self) -> None:
        self._render_hints()

    def watch_mode(self) -> None:
        self._render_hints()

    def _render_hints(self) -> None:
        hints = self._PREVIEW_HINTS if self.mode == "preview" else self._BROWSER_HINTS
        text = Text()
        for i, (section, keys) in enumerate(hints):
            if i > 0:
                text.append(" \u2502 ", style="dim")
            text.append(f"{section}: ", style="bold")
            for j, (key, desc) in enumerate(keys):
                if j > 0:
                    text.append("  ")
                text.append(key, style="bold cyan")
                text.append(f" {desc}", style="dim")
        try:
            self.query_one("#status-text", Static).update(text)
        except Exception:
            pass
