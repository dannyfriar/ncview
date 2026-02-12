"""Clipboard support — native tools locally, OSC 52 over SSH."""

from __future__ import annotations

import base64
import os
import shutil
import subprocess
import sys


def copy_to_clipboard(text: str) -> None:
    """Copy text to system clipboard.

    Uses native clipboard tools (pbcopy/xclip/xsel) when running locally.
    Falls back to OSC 52 escape sequence over SSH sessions.
    """
    if not _is_ssh() and _try_native(text):
        return
    _osc52(text)


def _is_ssh() -> bool:
    return bool(os.environ.get("SSH_TTY") or os.environ.get("SSH_CLIENT"))


def _try_native(text: str) -> bool:
    """Try native clipboard commands. Returns True on success."""
    for cmd in (
        ["pbcopy"],                              # macOS
        ["wl-copy"],                             # Wayland
        ["xclip", "-selection", "clipboard"],     # X11
        ["xsel", "--clipboard", "--input"],       # X11 alt
        ["clip.exe"],                            # WSL
    ):
        if shutil.which(cmd[0]):
            try:
                subprocess.run(cmd, input=text.encode(), check=True)
                return True
            except (subprocess.SubprocessError, OSError):
                continue
    return False


def _osc52(text: str) -> None:
    """Send OSC 52 escape sequence — works over SSH if terminal supports it."""
    encoded = base64.b64encode(text.encode()).decode()
    payload = f"\033]52;c;{encoded}\a"
    try:
        with open("/dev/tty", "w") as tty:
            tty.write(payload)
            tty.flush()
    except OSError:
        sys.stderr.write(payload)
        sys.stderr.flush()
