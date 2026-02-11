"""TOML viewer — collapsible tree with vim-style navigation."""

from __future__ import annotations

import tomllib

from rich.text import Text
from textual import work
from textual.widgets import Static

from ncview.viewers.base import BaseViewer
from ncview.viewers.json_viewer import JsonTree

MAX_DEPTH = 50
MAX_NODES = 50_000


class TomlViewer(BaseViewer):
    """Displays TOML files as a navigable collapsible tree."""

    DEFAULT_CSS = """
    TomlViewer {
        height: 1fr;
    }
    TomlViewer > #toml-info {
        height: auto;
        padding: 0 1;
        background: #0d0e0c;
        color: #f8f8f2;
    }
    TomlViewer > JsonTree {
        height: 1fr;
    }
    """

    def __init__(self, path, **kwargs) -> None:
        super().__init__(path, **kwargs)
        self._node_count = 0

    @staticmethod
    def supported_extensions() -> set[str]:
        return {".toml"}

    @staticmethod
    def priority() -> int:
        return 5

    def compose(self):
        yield Static(id="toml-info")
        yield JsonTree("root", id="toml-tree")

    async def load_content(self) -> None:
        self._parse_toml()

    @work(thread=True, exclusive=True)
    def _parse_toml(self) -> None:
        try:
            raw = self.path.read_bytes()
            data = tomllib.loads(raw.decode(errors="replace"))
        except Exception as e:
            self.app.call_from_thread(self._show_error, f"Invalid TOML: {e}")
            return
        self.app.call_from_thread(self._populate_tree, data)

    def _show_error(self, message: str) -> None:
        tree = self.query_one("#toml-tree", JsonTree)
        tree.root.set_label(Text(message, style="bold red"))

    def _populate_tree(self, data) -> None:
        tree = self.query_one("#toml-tree", JsonTree)
        info = self.query_one("#toml-info", Static)

        size = self.path.stat().st_size
        size_str = f"{size / 1024 / 1024:.1f} MB" if size >= 1024 * 1024 else f"{size / 1024:.1f} KB"
        info_text = Text()
        info_text.append(self.path.name, style="bold")
        info_text.append(f"  ({size_str})", style="#75715e")
        info_text.append("  j/k: move  l: expand  h: collapse  space: toggle", style="#75715e")
        info.update(info_text)

        tree.root.set_label(Text(self._describe_type(data), style="bold"))
        self._node_count = 0
        self._build_tree(tree.root, data)
        tree.root.expand()
        tree.focus()

    def _describe_type(self, data) -> str:
        if isinstance(data, dict):
            return f"{self.path.name}  {{}} {len(data)} keys"
        elif isinstance(data, list):
            return f"{self.path.name}  [] {len(data)} items"
        return self.path.name

    def _build_tree(self, node, data, key: str | None = None, depth: int = 0) -> None:
        if self._node_count >= MAX_NODES:
            node.add_leaf(Text(f"... truncated ({MAX_NODES:,} node limit)", style="italic #75715e"))
            return
        if depth >= MAX_DEPTH:
            node.add_leaf(Text(f"... depth limit ({MAX_DEPTH})", style="italic #75715e"))
            return
        self._node_count += 1
        if isinstance(data, dict):
            label = self._make_label(key, f"{{}} {len(data)} keys")
            branch = node.add(label)
            for k, v in data.items():
                self._build_tree(branch, v, key=str(k), depth=depth + 1)
        elif isinstance(data, list):
            label = self._make_label(key, f"[] {len(data)} items")
            branch = node.add(label)
            for i, item in enumerate(data):
                self._build_tree(branch, item, key=str(i), depth=depth + 1)
        else:
            label = self._format_value(key, data)
            node.add_leaf(label)

    def _make_label(self, key: str | None, type_info: str) -> Text:
        text = Text()
        if key is not None:
            text.append(key, style="bold #f8f8f2")
            text.append(": ", style="#75715e")
        text.append(type_info, style="italic #75715e")
        return text

    def _format_value(self, key: str | None, value) -> Text:
        text = Text()
        if key is not None:
            text.append(key, style="bold #f8f8f2")
            text.append(": ", style="#75715e")
        if isinstance(value, str):
            text.append(f'"{value}"', style="#a6e22e")
        elif isinstance(value, bool):
            text.append(str(value).lower(), style="#e6db74")
        elif isinstance(value, (int, float)):
            text.append(str(value), style="#ae81ff")
        elif value is None:
            text.append("null", style="italic #75715e")
        else:
            text.append(repr(value), style="#f8f8f2")
        return text
