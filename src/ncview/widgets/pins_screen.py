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
    label.append("\U0001f4cc ", style="bold")
    if pin["name"]:
        label.append(pin["name"], style="bold")
        label.append("  ", style="dim")
        label.append(pin["path"], style="dim")
    else:
        label.append(pin["path"], style="bold blue")
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
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }
    PinsScreen > Vertical > #pins-title {
        text-style: bold;
        color: $accent;
        width: 1fr;
        content-align: center middle;
    }
    PinsScreen > Vertical > #pins-empty {
        width: 1fr;
        content-align: center middle;
        margin: 1 0;
        color: $text-muted;
    }
    PinsScreen > Vertical > ListView {
        height: auto;
        max-height: 20;
        margin: 1 0;
    }
    PinsScreen > Vertical > ListView > ListItem {
        height: 1;
        padding: 0 1;
    }
    PinsScreen > Vertical > #pins-hint {
        width: 1fr;
        content-align: center middle;
        color: $text-muted;
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
            hint.append("j/k", style="bold cyan")
            hint.append(" nav  ", style="dim")
            hint.append("Enter/l", style="bold cyan")
            hint.append(" open  ", style="dim")
            hint.append("d", style="bold cyan")
            hint.append(" unpin  ", style="dim")
            hint.append("q/Esc", style="bold cyan")
            hint.append(" close", style="dim")
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
