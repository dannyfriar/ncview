"""Modal screen for selecting a pinned directory."""

from __future__ import annotations

from pathlib import Path

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, ListItem, ListView, Static

from ncview.utils.clipboard import copy_to_clipboard
from ncview.utils.pins import Pin, add_pin, load_pins, remove_pin


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
    PinsScreen > Vertical > .pin-add-field {
        display: none;
        margin: 0 0 0 0;
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
        ("a", "add_pin", "Add pin"),
        ("e", "edit_pin", "Edit pin"),
        ("y", "yank_pin", "Copy path"),
        ("d", "delete_pin", "Unpin"),
        ("escape", "cancel", "Cancel"),
        ("q", "cancel", "Cancel"),
        ("ctrl+c", "quit", "Quit"),
    ]

    def __init__(self, current_dir: Path | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._pins: list[Pin] = []
        self._current_dir = current_dir
        self._adding = False
        self._edit_old_path: str | None = None

    def compose(self) -> ComposeResult:
        self._pins = load_pins()
        items = [ListItem(Label(_pin_label(pin)), name=pin["path"]) for pin in self._pins]
        with Vertical():
            yield Static("Pinned Directories", id="pins-title")
            if not self._pins:
                yield Static("No pinned directories yet.", id="pins-empty")
            yield ListView(*items, id="pins-list")
            yield Input(placeholder="Directory path", id="pin-add-path", classes="pin-add-field")
            yield Input(placeholder="Display name (optional, Enter to save)", id="pin-add-name", classes="pin-add-field")
            hint = Text()
            hint.append("j/k", style="bold #66d9ef")
            hint.append(" nav  ", style="#75715e")
            hint.append("Enter/l", style="bold #66d9ef")
            hint.append(" open  ", style="#75715e")
            hint.append("a", style="bold #66d9ef")
            hint.append(" add  ", style="#75715e")
            hint.append("e", style="bold #66d9ef")
            hint.append(" edit  ", style="#75715e")
            hint.append("y", style="bold #66d9ef")
            hint.append(" yank  ", style="#75715e")
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
        if self._adding:
            return
        try:
            self.query_one("#pins-list", ListView).action_cursor_down()
        except Exception:
            pass

    def action_cursor_up(self) -> None:
        if self._adding:
            return
        try:
            self.query_one("#pins-list", ListView).action_cursor_up()
        except Exception:
            pass

    def action_select_pin(self) -> None:
        if self._adding:
            return
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

    def action_yank_pin(self) -> None:
        """Copy the highlighted pin's path to the clipboard via OSC 52."""
        if self._adding:
            return
        try:
            lv = self.query_one("#pins-list", ListView)
        except Exception:
            return
        if lv.highlighted_child is None:
            return
        pin_path = lv.highlighted_child.name
        if not pin_path:
            return
        copy_to_clipboard(pin_path)
        self.app.notify(f"Copied: {pin_path}", severity="information")

    def action_edit_pin(self) -> None:
        """Edit the highlighted pin's path and name."""
        if self._adding:
            return
        try:
            lv = self.query_one("#pins-list", ListView)
        except Exception:
            return
        if lv.highlighted_child is None:
            return
        pin_path = lv.highlighted_child.name
        if not pin_path:
            return
        # Find the current name
        pin_name = ""
        for pin in self._pins:
            if pin["path"] == pin_path:
                pin_name = pin["name"]
                break
        self._edit_old_path = pin_path
        self._adding = True
        path_inp = self.query_one("#pin-add-path", Input)
        path_inp.value = pin_path
        path_inp.styles.display = "block"
        name_inp = self.query_one("#pin-add-name", Input)
        name_inp.value = pin_name
        name_inp.styles.display = "block"
        path_inp.focus()

    def action_add_pin(self) -> None:
        """Show the inline inputs to pin a directory."""
        if self._adding:
            return
        self._adding = True
        path_inp = self.query_one("#pin-add-path", Input)
        path_inp.value = str(self._current_dir or "")
        path_inp.styles.display = "block"
        name_inp = self.query_one("#pin-add-name", Input)
        name_inp.value = ""
        name_inp.styles.display = "block"
        path_inp.focus()

    @on(Input.Submitted, "#pin-add-path")
    def _on_path_submitted(self, event: Input.Submitted) -> None:
        """Tab-like: move focus to the name field on Enter."""
        self.query_one("#pin-add-name", Input).focus()

    @on(Input.Submitted, "#pin-add-name")
    def _on_name_submitted(self, event: Input.Submitted) -> None:
        path_str = self.query_one("#pin-add-path", Input).value.strip()
        if not path_str:
            self._finish_add()
            return
        path = Path(path_str).resolve()
        if not path.is_dir():
            self.app.notify(f"Not a directory: {path}", severity="error")
            return
        name = event.value.strip()
        # If editing and the path changed, remove the old pin first
        if self._edit_old_path and str(path) != self._edit_old_path:
            remove_pin(self._edit_old_path)
        overwritten = add_pin(str(path), name=name)
        if self._edit_old_path:
            self.app.notify(f"Updated pin: {path}", severity="information")
        elif overwritten:
            self.app.notify(f"Updated pin: {path}", severity="information")
        else:
            self.app.notify(f"Pinned: {path}", severity="information")
        self._finish_add()
        self._rebuild_list()

    def _finish_add(self) -> None:
        self._adding = False
        self._edit_old_path = None
        self.query_one("#pin-add-path", Input).styles.display = "none"
        self.query_one("#pin-add-name", Input).styles.display = "none"
        try:
            self.query_one("#pins-list", ListView).focus()
        except Exception:
            pass

    def _rebuild_list(self) -> None:
        """Reload pins and rebuild the ListView."""
        self._pins = load_pins()
        # Remove the empty message if present
        try:
            self.query_one("#pins-empty", Static).remove()
        except Exception:
            pass
        lv = self.query_one("#pins-list", ListView)
        idx = lv.index or 0
        lv.clear()
        for pin in self._pins:
            lv.append(ListItem(Label(_pin_label(pin)), name=pin["path"]))
        if lv.children:
            lv.index = min(idx, len(lv.children) - 1)
            lv.focus()

    def action_delete_pin(self) -> None:
        if self._adding:
            return
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
        if self._adding:
            self._finish_add()
            return
        self.dismiss(None)

    def action_quit(self) -> None:
        self.app.exit()
