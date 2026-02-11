"""Clipboard support via OSC 52 escape sequence."""

from __future__ import annotations

import base64
import sys


def osc52_copy(text: str) -> None:
    """Copy text to clipboard via OSC 52 — works over SSH."""
    encoded = base64.b64encode(text.encode()).decode()
    sys.stdout.write(f"\033]52;c;{encoded}\a")
    sys.stdout.flush()
