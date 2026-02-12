"""Centralized config directory resolution."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def config_dir() -> Path:
    """Return the ncview config directory.

    Resolution order:
        1. $NCVIEW_CONFIG_DIR  (explicit override)
        2. $XDG_CONFIG_HOME/ncview  (XDG standard)
        3. ~/.config/ncview  (default)
    """
    if env := os.environ.get("NCVIEW_CONFIG_DIR"):
        return Path(env)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "ncview"
    return Path.home() / ".config" / "ncview"
