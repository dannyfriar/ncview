"""Load and save pinned directories."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict

from ncview.utils.config import config_dir

PINS_FILE = config_dir() / "pins.json"


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


def add_pin(path: str, name: str = "") -> bool:
    """Add or overwrite a pin. Returns True if an existing pin was overwritten."""
    resolved = str(Path(path).resolve())
    pins = load_pins()
    for i, p in enumerate(pins):
        if p["path"] == resolved:
            pins[i] = Pin(path=resolved, name=name)
            _save_pins(pins)
            return True
    pins.append(Pin(path=resolved, name=name))
    _save_pins(pins)
    return False


def remove_pin(path: str) -> None:
    """Remove a path from the pinned list and save."""
    resolved = str(Path(path).resolve())
    pins = load_pins()
    pins = [p for p in pins if p["path"] != resolved]
    _save_pins(pins)
