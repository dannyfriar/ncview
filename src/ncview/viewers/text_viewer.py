"""Text viewer — syntax-highlighted scrollable text."""

from __future__ import annotations

from pathlib import Path

from rich.syntax import Syntax
from rich.text import Text
from textual import work
from textual.widgets import Static

from ncview.viewers.base import BaseViewer

MAX_LINES = 10_000
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

# Map file extensions to Rich lexer names
_EXT_TO_LEXER: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "jsx",
    ".tsx": "tsx",
    ".rs": "rust",
    ".go": "go",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".java": "java",
    ".rb": "ruby",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "zsh",
    ".fish": "fish",
    ".sql": "sql",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",
    ".less": "less",
    ".xml": "xml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".ini": "ini",
    ".cfg": "ini",
    ".conf": "ini",
    ".md": "markdown",
    ".rst": "rst",
    ".r": "r",
    ".R": "r",
    ".lua": "lua",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
    ".pl": "perl",
    ".php": "php",
    ".ex": "elixir",
    ".exs": "elixir",
    ".erl": "erlang",
    ".hs": "haskell",
    ".ml": "ocaml",
    ".clj": "clojure",
    ".vim": "vim",
    ".dockerfile": "dockerfile",
    ".tf": "terraform",
    ".proto": "protobuf",
    ".graphql": "graphql",
    ".gql": "graphql",
}

# All extensions this viewer handles
_ALL_EXTENSIONS = {
    ".txt", ".log", ".env", ".gitignore", ".dockerignore",
    ".editorconfig", ".properties", ".lock",
} | set(_EXT_TO_LEXER.keys())


class TextViewer(BaseViewer):
    """Displays text files with syntax highlighting."""

    DEFAULT_CSS = """
    TextViewer {
        height: auto;
    }
    TextViewer > Static {
        width: 1fr;
    }
    """

    @staticmethod
    def supported_extensions() -> set[str]:
        return _ALL_EXTENSIONS

    @staticmethod
    def priority() -> int:
        return -1  # Low priority — catch-all for text

    def compose(self):
        yield Static(id="text-content")

    async def load_content(self) -> None:
        self._load_text()

    @work(thread=True, exclusive=True)
    def _load_text(self) -> None:
        """Read and highlight text in a background thread."""
        try:
            file_size = self.path.stat().st_size
            if file_size > MAX_FILE_SIZE:
                self.app.call_from_thread(
                    self._show_content,
                    Text(
                        f"File too large ({file_size / 1024 / 1024:.1f} MB > {MAX_FILE_SIZE // 1024 // 1024} MB limit)",
                        style="bold red",
                    ),
                )
                return
            raw = self.path.read_text(errors="replace")
            lines = raw.split("\n", MAX_LINES + 1)
            if len(lines) > MAX_LINES:
                raw = "\n".join(lines[:MAX_LINES])
                raw += f"\n\n... truncated at {MAX_LINES:,} lines ..."

            lexer = _EXT_TO_LEXER.get(self.path.suffix.lower())
            if lexer:
                content = Syntax(
                    raw,
                    lexer,
                    theme="monokai",
                    line_numbers=True,
                    word_wrap=False,
                )
            else:
                content = Text(raw)

            self.app.call_from_thread(self._show_content, content)
        except Exception as e:
            self.app.call_from_thread(
                self._show_content,
                Text(f"Error reading file: {e}", style="bold red"),
            )

    def _show_content(self, content) -> None:
        self.query_one("#text-content", Static).update(content)
