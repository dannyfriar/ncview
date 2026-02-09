"""Yes/No confirmation modal screen."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Center, Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, Static


class ConfirmScreen(ModalScreen[bool]):
    """Modal screen prompting the user for yes/no confirmation."""

    DEFAULT_CSS = """
    ConfirmScreen {
        align: center middle;
    }
    ConfirmScreen > Vertical {
        width: 60;
        height: auto;
        border: thick #f92672;
        background: #1a1b18;
        color: #f8f8f2;
        padding: 1 2;
    }
    ConfirmScreen > Vertical > #confirm-title {
        text-style: bold;
        color: #f92672;
        width: 1fr;
        content-align: center middle;
    }
    ConfirmScreen > Vertical > #confirm-message {
        width: 1fr;
        content-align: center middle;
        margin: 1 0;
    }
    ConfirmScreen > Vertical > #confirm-hint {
        width: 1fr;
        content-align: center middle;
        color: #75715e;
    }
    """

    BINDINGS = [
        ("y", "confirm", "Yes"),
        ("n", "cancel", "No"),
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, title: str, message: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._title = title
        self._message = message

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(self._title, id="confirm-title")
            yield Static(self._message, id="confirm-message")
            hint = Text()
            hint.append("y", style="bold #66d9ef")
            hint.append(" yes  ", style="#75715e")
            hint.append("n/Esc", style="bold #66d9ef")
            hint.append(" no", style="#75715e")
            yield Static(hint, id="confirm-hint")

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)
