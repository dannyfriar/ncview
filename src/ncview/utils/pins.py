"""Load and save pinned directories from ~/.config/ncview/pins.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict

PINS_FILE = Path.home() / ".config" / "ncview" / "pins.json"


class Pin(TypedDict):
    path: str
    name: str


def load_pins() -> list[Pin]:
    """Read the pinned directories list. Returns empty list if file is missing."""
    if not PINS_FILE.exists():
        return []
    try:
        data = json.loads(PINS_FILE.read_text())
        if isinstance(data, list):
            pins: list[Pin] = []
            for entry in data:
                if isinstance(entry, dict) and "path" in entry:
                    pins.append(Pin(path=entry["path"], name=entry.get("name", "")))
                elif isinstance(entry, str):
                    # Backwards compat: bare string -> unnamed pin
                    pins.append(Pin(path=entry, name=""))
            return pins
    except (json.JSONDecodeError, OSError):
        pass
    return []


def _save_pins(pins: list[Pin]) -> None:
    """Write the pinned directories list to disk."""
    PINS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PINS_FILE.write_text(json.dumps(pins, indent=2) + "\n")


def add_pin(path: str, name: str = "") -> None:
    """Append a resolved absolute path, deduplicate, and save."""
    resolved = str(Path(path).resolve())
    pins = load_pins()
    if any(p["path"] == resolved for p in pins):
        return
    pins.append(Pin(path=resolved, name=name))
    _save_pins(pins)


def remove_pin(path: str) -> None:
    """Remove a path from the pinned list and save."""
    resolved = str(Path(path).resolve())
    pins = load_pins()
    pins = [p for p in pins if p["path"] != resolved]
    _save_pins(pins)
