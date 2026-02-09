"""File metadata extraction and size formatting."""

from __future__ import annotations

import os
import stat
from datetime import datetime, timezone
from pathlib import Path


def human_size(size: int | float) -> str:
    """Convert bytes to human-readable string."""
    for unit in ("B", "K", "M", "G", "T"):
        if abs(size) < 1024:
            if unit == "B":
                return f"{int(size)}{unit}"
            return f"{size:.1f}{unit}"
        size = size / 1024
    return f"{size:.1f}P"


def file_icon(path: Path) -> str:
    """Return a simple icon character for a path."""
    if path.is_dir():
        return "\U0001f4c1"  # folder
    ext = path.suffix.lower()
    if ext == ".py":
        return "\U0001f40d"  # snake (Python)
    if ext == ".rs":
        return "\u2699\ufe0f"  # gear (Rust)
    if ext in {".js", ".ts", ".go", ".c", ".cpp", ".java"}:
        return "\U0001f4c4"  # code
    if ext in {".parquet", ".csv", ".tsv", ".xlsx"}:
        return "\U0001f4ca"  # data
    if ext in {".json", ".yaml", ".yml", ".toml", ".xml"}:
        return "\u2699"  # config
    if ext in {".md", ".txt", ".rst", ".log"}:
        return "\U0001f4dd"  # text
    if ext in {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}:
        return "\U0001f5bc"  # image
    return "\U0001f4c3"  # generic file


def file_metadata(path: Path) -> dict[str, str]:
    """Extract metadata dict for display in fallback viewer."""
    info: dict[str, str] = {
        "Name": path.name,
        "Path": str(path.resolve()) if not path.is_symlink() else str(path),
    }

    # Check for broken symlinks first (lstat doesn't follow the link)
    if path.is_symlink():
        try:
            target = os.readlink(path)
            info["Link target"] = target
            if not path.exists():
                info["Link status"] = "broken"
                return info
        except OSError:
            info["Link target"] = "(unreadable)"
            return info

    try:
        st = path.stat()
    except OSError:
        info["error"] = "Cannot read file metadata"
        return info

    info.update({
        "Size": human_size(st.st_size),
        "Size (bytes)": f"{st.st_size:,}",
        "Modified": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
            .astimezone().strftime("%Y-%m-%d %H:%M:%S"),
        "Created": datetime.fromtimestamp(st.st_ctime, tz=timezone.utc)
            .astimezone().strftime("%Y-%m-%d %H:%M:%S"),
        "Permissions": stat.filemode(st.st_mode),
    })

    try:
        import pwd
        info["Owner"] = pwd.getpwuid(st.st_uid).pw_name
    except (ImportError, KeyError, AttributeError):
        info["Owner"] = str(st.st_uid)

    try:
        import grp
        info["Group"] = grp.getgrgid(st.st_gid).gr_name
    except (ImportError, KeyError, AttributeError):
        info["Group"] = str(st.st_gid)

    return info
