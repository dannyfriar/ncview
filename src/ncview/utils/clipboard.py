"""Clipboard support via OSC 52 escape sequence."""

from __future__ import annotations

import base64
import sys


def osc52_copy(text: str) -> None:
    """Copy text to clipboard via OSC 52 — works over SSH.

    Writes directly to /dev/tty to bypass Textual's stdout capture.
    """
    encoded = base64.b64encode(text.encode()).decode()
    payload = f"\033]52;c;{encoded}\a"
    try:
        with open("/dev/tty", "w") as tty:
            tty.write(payload)
            tty.flush()
    except OSError:
        sys.stdout.write(payload)
        sys.stdout.flush()
