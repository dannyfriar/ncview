"""Directory history tracking."""

from __future__ import annotations

import json
from pathlib import Path

HISTORY_FILE = Path.home() / ".config" / "ncview" / "history.json"
MAX_HISTORY = 25


def load_history() -> list[str]:
    """Load recent directory paths, most recent first."""
    if not HISTORY_FILE.exists():
        return []
    try:
        data = json.loads(HISTORY_FILE.read_text())
        if isinstance(data, list):
            return [str(p) for p in data][:MAX_HISTORY]
    except (json.JSONDecodeError, OSError):
        pass
    return []


def add_to_history(path: str) -> None:
    """Add a directory path to the top of history, deduplicating."""
    resolved = str(Path(path).resolve())
    history = load_history()
    history = [p for p in history if p != resolved]
    history.insert(0, resolved)
    history = history[:MAX_HISTORY]
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(history, indent=2) + "\n")
