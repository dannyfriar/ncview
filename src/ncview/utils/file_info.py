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


def file_icon(path: Path, is_dir: bool | None = None) -> str:
    """Return a Nerd Font icon for a path.

    Pass is_dir=True/False to avoid a stat() syscall.
    """
    if is_dir if is_dir is not None else path.is_dir():
        return "\uf07b"  # nf-fa-folder
    ext = path.suffix.lower()
    icon = _ICON_MAP.get(ext)
    if icon:
        return icon
    if ext in _CODE_EXTS:
        return "\uf121"  # nf-fa-code
    return "\uf016"  # nf-fa-file_o


_ICON_MAP: dict[str, str] = {
    # Languages
    ".py": "\ue73c",  # nf-dev-python
    ".rs": "\ue7a8",  # nf-dev-rust
    ".js": "\ue74e",  # nf-dev-javascript
    ".ts": "\ue628",  # nf-seti-typescript
    ".go": "\ue724",  # nf-seti-go
    ".c": "\ue61e",  # nf-custom-c
    ".cpp": "\ue61d",  # nf-custom-cpp
    ".java": "\ue738",  # nf-dev-java
    ".rb": "\ue739",  # nf-dev-ruby
    ".lua": "\ue620",  # nf-seti-lua
    ".sh": "\uf489",  # nf-oct-terminal
    ".bash": "\uf489",
    ".zsh": "\uf489",
    # Data
    ".json": "\ue60b",  # nf-seti-json
    ".yaml": "\uf481",  # nf-oct-file_yaml
    ".yml": "\uf481",
    ".toml": "\uf013",  # nf-fa-cog
    ".xml": "\uf1c0",  # nf-fa-database
    ".csv": "\uf1c0",
    ".tsv": "\uf1c0",
    ".parquet": "\uf1c0",
    ".xlsx": "\uf1c0",
    # Docs
    ".md": "\ue73e",  # nf-dev-markdown
    ".markdown": "\ue73e",
    ".txt": "\uf0f6",  # nf-fa-file_text_o
    ".rst": "\uf0f6",
    ".log": "\uf0f6",
    # Images
    ".png": "\uf1c5",  # nf-fa-file_image_o
    ".jpg": "\uf1c5",
    ".jpeg": "\uf1c5",
    ".gif": "\uf1c5",
    ".svg": "\uf1c5",
    ".webp": "\uf1c5",
    # Config / infra
    ".env": "\uf023",  # nf-fa-lock
    ".gitignore": "\ue702",  # nf-dev-git
    ".dockerignore": "\ue7b0",  # nf-dev-docker
    "Dockerfile": "\ue7b0",
}

_CODE_EXTS = {".h", ".hpp", ".cs", ".swift", ".kt", ".scala", ".r", ".m", ".pl"}


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
