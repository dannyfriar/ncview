"""JSON viewer — collapsible tree with vim-style navigation."""

from __future__ import annotations

import json
from pathlib import Path

from textual import work

from rich.text import Text
from textual.binding import Binding
from textual.widgets import Static, Tree

from ncview.viewers.base import BaseViewer

MAX_DEPTH = 50
MAX_NODES = 50_000


class JsonTree(Tree):
    """Tree with vim-style keybindings for JSON navigation."""

    BINDINGS = [
        Binding("j", "cursor_down", "Down", priority=True),
        Binding("k", "cursor_up", "Up", priority=True),
        Binding("l", "expand_node", "Expand", priority=True),
        Binding("h", "collapse_node", "Collapse", priority=True),
        Binding("space", "toggle_node", "Toggle", priority=True),
        Binding("enter", "select_cursor", "Toggle", priority=True),
        Binding("g", "scroll_home", "Top", priority=True),
        Binding("G", "scroll_end", "Bottom", priority=True),
    ]

    def action_expand_node(self) -> None:
        """Expand current node, or move into first child if already expanded."""
        node = self.cursor_node
        if node is None:
            return
        if not node.allow_expand:
            return
        if not node.is_expanded:
            node.expand()
        elif node.children:
            # Already expanded — move cursor to first child
            self.cursor_line = self.cursor_line + 1

    def action_collapse_node(self) -> None:
        """Collapse current node, or move to parent if already collapsed/leaf."""
        node = self.cursor_node
        if node is None:
            return
        if node.is_expanded and node.allow_expand:
            node.collapse()
        elif node.parent is not None:
            # Move to parent
            self.select_node(node.parent)
            node.parent.collapse()


class JsonViewer(BaseViewer):
    """Displays JSON files as a navigable collapsible tree."""

    DEFAULT_CSS = """
    JsonViewer {
        height: 1fr;
    }
    JsonViewer > #json-info {
        height: auto;
        padding: 0 1;
        background: $primary-background;
        color: $text;
    }
    JsonViewer > JsonTree {
        height: 1fr;
    }
    """

    @staticmethod
    def supported_extensions() -> set[str]:
        return {".json", ".geojson", ".jsonl"}

    @staticmethod
    def priority() -> int:
        return 5

    def compose(self):
        yield Static(id="json-info")
        yield JsonTree("root", id="json-tree")

    async def load_content(self) -> None:
        self._parse_json()

    @work(thread=True, exclusive=True)
    def _parse_json(self) -> None:
        """Parse JSON in a background thread to keep UI responsive for large files."""
        try:
            raw = self.path.read_text(errors="replace")

            if self.path.suffix.lower() == ".jsonl":
                lines = [json.loads(line) for line in raw.strip().split("\n") if line.strip()]
                data = lines
            else:
                data = json.loads(raw)
        except json.JSONDecodeError as e:
            self.app.call_from_thread(self._show_error, f"Invalid JSON: {e}")
            return
        except Exception as e:
            self.app.call_from_thread(self._show_error, f"Error: {e}")
            return

        self.app.call_from_thread(self._populate_tree, data)

    def _show_error(self, message: str) -> None:
        tree = self.query_one("#json-tree", JsonTree)
        tree.root.set_label(Text(message, style="bold red"))

    def _populate_tree(self, data) -> None:
        tree = self.query_one("#json-tree", JsonTree)
        info = self.query_one("#json-info", Static)

        size = self.path.stat().st_size
        size_str = f"{size / 1024 / 1024:.1f} MB" if size >= 1024 * 1024 else f"{size / 1024:.1f} KB"
        info_text = Text()
        info_text.append(self.path.name, style="bold")
        info_text.append(f"  ({size_str})", style="dim")
        info_text.append("  j/k: move  l: expand  h: collapse  space: toggle", style="dim")
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
        """Recursively build tree nodes from JSON data."""
        if self._node_count >= MAX_NODES:
            node.add_leaf(Text(f"... truncated ({MAX_NODES:,} node limit)", style="italic dim"))
            return
        if depth >= MAX_DEPTH:
            node.add_leaf(Text(f"... depth limit ({MAX_DEPTH})", style="italic dim"))
            return
        self._node_count += 1
        if isinstance(data, dict):
            label = self._make_label(key, f"{{}} {len(data)} keys")
            branch = node.add(label)
            for k, v in data.items():
                self._build_tree(branch, v, key=k, depth=depth + 1)
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
            text.append(key, style="bold white")
            text.append(": ", style="dim")
        text.append(type_info, style="dim italic")
        return text

    def _format_value(self, key: str | None, value) -> Text:
        text = Text()
        if key is not None:
            text.append(key, style="bold white")
            text.append(": ", style="dim")
        if isinstance(value, str):
            text.append(f'"{value}"', style="green")
        elif isinstance(value, bool):
            text.append(str(value).lower(), style="yellow")
        elif isinstance(value, (int, float)):
            text.append(str(value), style="cyan")
        elif value is None:
            text.append("null", style="dim italic")
        else:
            text.append(repr(value), style="white")
        return text
