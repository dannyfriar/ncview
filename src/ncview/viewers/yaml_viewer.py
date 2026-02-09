"""YAML viewer — collapsible tree with vim-style navigation."""

from __future__ import annotations

from rich.text import Text
from textual import work
from textual.widgets import Static

from textual.binding import Binding

from ncview.viewers.base import BaseViewer
from ncview.viewers.json_viewer import JsonTree

MAX_DEPTH = 50
MAX_NODES = 50_000


class YamlTree(JsonTree):
    """JsonTree with expand/collapse-all for YAML files."""

    BINDINGS = [
        *JsonTree.BINDINGS,
        Binding("E", "expand_all", "Expand all", priority=True),
        Binding("C", "collapse_all", "Collapse all", priority=True),
    ]

    def _expand_recursive(self, node) -> None:
        if node.allow_expand:
            node.expand()
            for child in node.children:
                self._expand_recursive(child)

    def _collapse_recursive(self, node) -> None:
        if node.allow_expand:
            for child in node.children:
                self._collapse_recursive(child)
            node.collapse()

    def action_expand_all(self) -> None:
        self._expand_recursive(self.root)

    def action_collapse_all(self) -> None:
        self._collapse_recursive(self.root)
        self.root.expand()


class YamlViewer(BaseViewer):
    """Displays YAML files as a navigable collapsible tree."""

    DEFAULT_CSS = """
    YamlViewer {
        height: 1fr;
    }
    YamlViewer > #yaml-info {
        height: auto;
        padding: 0 1;
        background: #0d0e0c;
        color: #f8f8f2;
    }
    YamlViewer > YamlTree {
        height: 1fr;
    }
    """

    @staticmethod
    def supported_extensions() -> set[str]:
        return {".yaml", ".yml"}

    @staticmethod
    def priority() -> int:
        return 5

    def compose(self):
        yield Static(id="yaml-info")
        yield YamlTree("root", id="yaml-tree")

    async def load_content(self) -> None:
        self._parse_yaml()

    @work(thread=True, exclusive=True)
    def _parse_yaml(self) -> None:
        try:
            import yaml
            raw = self.path.read_text(errors="replace")
            data = yaml.safe_load(raw)
        except Exception as e:
            self.app.call_from_thread(self._show_error, f"Invalid YAML: {e}")
            return
        self.app.call_from_thread(self._populate_tree, data)

    def _show_error(self, message: str) -> None:
        tree = self.query_one("#yaml-tree", YamlTree)
        tree.root.set_label(Text(message, style="bold red"))

    def _populate_tree(self, data) -> None:
        tree = self.query_one("#yaml-tree", YamlTree)
        info = self.query_one("#yaml-info", Static)

        size = self.path.stat().st_size
        size_str = f"{size / 1024 / 1024:.1f} MB" if size >= 1024 * 1024 else f"{size / 1024:.1f} KB"
        info_text = Text()
        info_text.append(self.path.name, style="bold")
        info_text.append(f"  ({size_str})", style="#75715e")
        info_text.append("  j/k: move  l: expand  h: collapse  space: toggle  E: expand all  C: collapse all", style="#75715e")
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
