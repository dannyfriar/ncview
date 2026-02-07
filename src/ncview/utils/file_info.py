"""File metadata extraction and size formatting."""

from __future__ import annotations

import grp
import os
import pwd
import stat
from datetime import datetime
from pathlib import Path


def human_size(size: int) -> str:
    """Convert bytes to human-readable string."""
    for unit in ("B", "K", "M", "G", "T"):
        if abs(size) < 1024:
            if unit == "B":
                return f"{size}{unit}"
            return f"{size:.1f}{unit}"
        size /= 1024  # type: ignore[assignment]
    return f"{size:.1f}P"


def file_icon(path: Path) -> str:
    """Return a simple icon character for a path."""
    if path.is_dir():
        return "\U0001f4c1"  # folder
    ext = path.suffix.lower()
    if ext in {".py", ".js", ".ts", ".rs", ".go", ".c", ".cpp", ".java"}:
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
    try:
        st = path.stat()
    except OSError:
        return {"error": "Cannot read file metadata"}

    info: dict[str, str] = {
        "Name": path.name,
        "Path": str(path.resolve()),
        "Size": human_size(st.st_size),
        "Size (bytes)": f"{st.st_size:,}",
        "Modified": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        "Created": datetime.fromtimestamp(st.st_ctime).strftime("%Y-%m-%d %H:%M:%S"),
        "Permissions": stat.filemode(st.st_mode),
    }

    try:
        info["Owner"] = pwd.getpwuid(st.st_uid).pw_name
    except (KeyError, AttributeError):
        info["Owner"] = str(st.st_uid)

    try:
        info["Group"] = grp.getgrgid(st.st_gid).gr_name
    except (KeyError, AttributeError):
        info["Group"] = str(st.st_gid)

    if path.is_symlink():
        try:
            info["Link target"] = str(path.resolve())
        except OSError:
            info["Link target"] = "(broken)"

    return info
