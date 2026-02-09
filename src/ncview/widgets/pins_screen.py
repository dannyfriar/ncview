"""Modal screen for selecting a pinned directory."""

from __future__ import annotations

from pathlib import Path

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, ListItem, ListView, Static

from ncview.utils.pins import Pin, load_pins, remove_pin


def _pin_label(pin: Pin) -> Text:
    """Build a Rich label for a pin entry."""
    label = Text()
    label.append("\uf08d ", style="bold #fd971f")
    if pin["name"]:
        label.append(pin["name"], style="bold #e6db74")
        label.append("  ", style="#75715e")
        label.append(pin["path"], style="#75715e")
    else:
        label.append(pin["path"], style="bold #66d9ef")
    return label


class PinsScreen(ModalScreen[Path | None]):
    """Modal listing pinned directories with vim-style navigation."""

    DEFAULT_CSS = """
    PinsScreen {
        align: center middle;
    }
    PinsScreen > Vertical {
        width: 70;
        height: auto;
        max-height: 80%;
        border: thick #ae81ff;
        background: #1a1b18;
        color: #f8f8f2;
        padding: 1 2;
    }
    PinsScreen > Vertical > #pins-title {
        text-style: bold;
        color: #ae81ff;
        width: 1fr;
        content-align: center middle;
    }
    PinsScreen > Vertical > #pins-empty {
        width: 1fr;
        content-align: center middle;
        margin: 1 0;
        color: #75715e;
    }
    PinsScreen > Vertical > ListView {
        height: auto;
        max-height: 20;
        margin: 1 0;
        background: #1a1b18;
    }
    PinsScreen > Vertical > ListView > ListItem {
        height: 1;
        padding: 0 1;
    }
    PinsScreen > Vertical > #pins-hint {
        width: 1fr;
        content-align: center middle;
        color: #75715e;
    }
    """

    BINDINGS = [
        ("j", "cursor_down", "Down"),
        ("k", "cursor_up", "Up"),
        ("l", "select_pin", "Select"),
        ("d", "delete_pin", "Unpin"),
        ("escape", "cancel", "Cancel"),
        ("q", "cancel", "Cancel"),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._pins: list[Pin] = []

    def compose(self) -> ComposeResult:
        self._pins = load_pins()
        with Vertical():
            yield Static("Pinned Directories", id="pins-title")
            if not self._pins:
                yield Static("No pinned directories.\nUse: ncview pin <path>", id="pins-empty")
            else:
                items = []
                for pin in self._pins:
                    items.append(ListItem(Label(_pin_label(pin)), name=pin["path"]))
                yield ListView(*items, id="pins-list")
            hint = Text()
            hint.append("j/k", style="bold #66d9ef")
            hint.append(" nav  ", style="#75715e")
            hint.append("Enter/l", style="bold #66d9ef")
            hint.append(" open  ", style="#75715e")
            hint.append("d", style="bold #66d9ef")
            hint.append(" unpin  ", style="#75715e")
            hint.append("q/Esc", style="bold #66d9ef")
            hint.append(" close", style="#75715e")
            yield Static(hint, id="pins-hint")

    def on_mount(self) -> None:
        try:
            lv = self.query_one("#pins-list", ListView)
            if lv.children:
                lv.index = 0
                lv.focus()
        except Exception:
            pass

    @on(ListView.Selected, "#pins-list")
    def _on_list_selected(self, event: ListView.Selected) -> None:
        self.action_select_pin()

    def action_cursor_down(self) -> None:
        try:
            self.query_one("#pins-list", ListView).action_cursor_down()
        except Exception:
            pass

    def action_cursor_up(self) -> None:
        try:
            self.query_one("#pins-list", ListView).action_cursor_up()
        except Exception:
            pass

    def action_select_pin(self) -> None:
        try:
            lv = self.query_one("#pins-list", ListView)
        except Exception:
            self.dismiss(None)
            return
        if lv.highlighted_child is None:
            return
        pin_path = lv.highlighted_child.name
        if pin_path:
            self.dismiss(Path(pin_path))
        else:
            self.dismiss(None)

    def action_delete_pin(self) -> None:
        try:
            lv = self.query_one("#pins-list", ListView)
        except Exception:
            return
        if lv.highlighted_child is None:
            return
        pin_path = lv.highlighted_child.name
        if not pin_path:
            return

        # Find the display name for the confirm message
        display = pin_path
        for pin in self._pins:
            if pin["path"] == pin_path and pin["name"]:
                display = f"{pin['name']} ({pin_path})"
                break

        from ncview.widgets.confirm_screen import ConfirmScreen

        def _on_confirmed(confirmed: bool) -> None:
            if not confirmed:
                return
            remove_pin(pin_path)
            # Rebuild the list
            idx = lv.index or 0
            lv.clear()
            self._pins = load_pins()
            if not self._pins:
                self.dismiss(None)
                return
            for pin in self._pins:
                lv.append(ListItem(Label(_pin_label(pin)), name=pin["path"]))
            if lv.children:
                lv.index = min(idx, len(lv.children) - 1)

        self.app.push_screen(
            ConfirmScreen(
                title="Unpin directory",
                message=f"Remove pin '{display}'?",
            ),
            callback=_on_confirmed,
        )

    def action_cancel(self) -> None:
        self.dismiss(None)
