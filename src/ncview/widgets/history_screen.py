"""Modal screen for browsing directory history."""

from __future__ import annotations

from pathlib import Path

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, ListItem, ListView, Static

from ncview.utils.clipboard import osc52_copy
from ncview.utils.history import load_history


def _history_label(path_str: str, index: int) -> Text:
    """Build a Rich label for a history entry."""
    label = Text()
    label.append(f"{index + 1:>2} ", style="bold #ae81ff")
    label.append("\uf64f ", style="bold #fd971f")  # nf-md-history
    path = Path(path_str)
    parent = str(path.parent)
    name = path.name
    if parent and parent != path_str:
        label.append(parent + "/", style="#a6e22e")
    label.append(name, style="bold #e6db74")
    return label


class HistoryScreen(ModalScreen[Path | None]):
    """Modal listing recent directories with vim-style navigation."""

    DEFAULT_CSS = """
    HistoryScreen {
        align: center middle;
    }
    HistoryScreen > Vertical {
        width: 80;
        height: auto;
        max-height: 80%;
        border: thick #fd971f;
        background: #272822;
        color: #f8f8f2;
        padding: 1 2;
    }
    HistoryScreen > Vertical > #history-title {
        text-style: bold;
        color: #fd971f;
        width: 1fr;
        content-align: center middle;
    }
    HistoryScreen > Vertical > #history-empty {
        width: 1fr;
        content-align: center middle;
        margin: 1 0;
        color: #75715e;
    }
    HistoryScreen > Vertical > ListView {
        height: auto;
        max-height: 20;
        margin: 1 0;
        background: #272822;
    }
    HistoryScreen > Vertical > ListView > ListItem {
        height: 1;
        padding: 0 1;
    }
    HistoryScreen > Vertical > #history-hint {
        width: 1fr;
        content-align: center middle;
        color: #75715e;
    }
    """

    BINDINGS = [
        ("j", "cursor_down", "Down"),
        ("k", "cursor_up", "Up"),
        ("l", "select_entry", "Select"),
        ("y", "yank_path", "Copy path"),
        ("escape", "cancel", "Cancel"),
        ("q", "cancel", "Cancel"),
        ("ctrl+c", "quit", "Quit"),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._history: list[str] = []

    def compose(self) -> ComposeResult:
        self._history = load_history()
        items = [
            ListItem(Label(_history_label(p, i)), name=p)
            for i, p in enumerate(self._history)
        ]
        with Vertical():
            yield Static("Recent Directories", id="history-title")
            if not self._history:
                yield Static("No history yet.", id="history-empty")
            yield ListView(*items, id="history-list")
            hint = Text()
            hint.append("j/k", style="bold #66d9ef")
            hint.append(" nav  ", style="#75715e")
            hint.append("Enter/l", style="bold #66d9ef")
            hint.append(" open  ", style="#75715e")
            hint.append("y", style="bold #66d9ef")
            hint.append(" yank  ", style="#75715e")
            hint.append("q/Esc", style="bold #66d9ef")
            hint.append(" close", style="#75715e")
            yield Static(hint, id="history-hint")

    def on_mount(self) -> None:
        try:
            lv = self.query_one("#history-list", ListView)
            if lv.children:
                lv.index = 0
                lv.focus()
        except Exception:
            pass

    @on(ListView.Selected, "#history-list")
    def _on_list_selected(self, event: ListView.Selected) -> None:
        self.action_select_entry()

    def action_cursor_down(self) -> None:
        try:
            self.query_one("#history-list", ListView).action_cursor_down()
        except Exception:
            pass

    def action_cursor_up(self) -> None:
        try:
            self.query_one("#history-list", ListView).action_cursor_up()
        except Exception:
            pass

    def action_select_entry(self) -> None:
        try:
            lv = self.query_one("#history-list", ListView)
        except Exception:
            self.dismiss(None)
            return
        if lv.highlighted_child is None:
            return
        path_str = lv.highlighted_child.name
        if path_str:
            self.dismiss(Path(path_str))
        else:
            self.dismiss(None)

    def action_yank_path(self) -> None:
        try:
            lv = self.query_one("#history-list", ListView)
        except Exception:
            return
        if lv.highlighted_child is None:
            return
        path_str = lv.highlighted_child.name
        if path_str:
            osc52_copy(path_str)
            self.app.notify(f"Copied: {path_str}", severity="information")

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_quit(self) -> None:
        self.app.exit()
