"""Custom status bar with grouped keybinding hints."""

from __future__ import annotations

from rich.text import Text
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static


class StatusBar(Widget):
    """Two-line footer showing keybindings grouped by category."""

    DEFAULT_CSS = """
    StatusBar {
        dock: bottom;
        height: 2;
        background: #0d0e0c;
        color: #f8f8f2;
        padding: 0 1;
    }
    StatusBar > Static {
        width: 1fr;
        height: 1;
    }
    """

    mode = reactive("browser")

    _BROWSER_LINE1 = [
        ("Nav", [("j/k", "\u2195"), ("h/l", "\u2194"), ("g/G", "top/end")]),
        ("Filter", [("/", "search"), (".", "hidden"), ("s", "sort")]),
        ("App", [("p", "pins"), ("i", "ipython"), ("q", "quit")]),
    ]

    _BROWSER_LINE2 = [
        ("Actions", [("Enter", "open"), ("e", "edit"), ("E", "edit path"), ("t", "touch"), ("M", "mkdir"), ("r", "rename"), ("y", "copy"), ("d", "delete")]),
    ]

    _PREVIEW_LINE1 = [
        ("Nav", [("j/k", "scroll"), ("\u2303d/\u2303u", "page"), ("g/G", "top/end")]),
        ("Tabs", [("1/2/3", "switch")]),
    ]

    _PREVIEW_LINE2 = [
        ("Actions", [("e", "edit"), ("h/Esc", "close"), ("q", "quit")]),
    ]

    def compose(self):
        yield Static(id="status-line1")
        yield Static(id="status-line2")

    def on_mount(self) -> None:
        self._render_hints()

    def watch_mode(self) -> None:
        self._render_hints()

    @staticmethod
    def _build_line(hints: list) -> Text:
        text = Text()
        for i, (section, keys) in enumerate(hints):
            if i > 0:
                text.append(" \u2502 ", style="#75715e")
            text.append(f"{section}: ", style="bold #f8f8f2")
            for j, (key, desc) in enumerate(keys):
                if j > 0:
                    text.append("  ")
                text.append(key, style="bold #66d9ef")
                text.append(f" {desc}", style="#75715e")
        return text

    def _render_hints(self) -> None:
        if self.mode == "preview":
            line1, line2 = self._PREVIEW_LINE1, self._PREVIEW_LINE2
        else:
            line1, line2 = self._BROWSER_LINE1, self._BROWSER_LINE2
        try:
            self.query_one("#status-line1", Static).update(self._build_line(line1))
            self.query_one("#status-line2", Static).update(self._build_line(line2))
        except Exception:
            pass
