# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Terminal file browser with vim keybindings, built with Textual. Monokai color scheme. Rich file previews for parquet, CSV, JSON, YAML, TOML, markdown, and syntax-highlighted text.

## Build and run

```bash
uv venv --python 3.12
uv pip install -e .        # editable install for development
ncview                     # launch in current directory
ncview /some/path          # launch in specific directory
```

Version is in `pyproject.toml` and the README PyPI badge — always bump both together. Clean `dist/` after building (old wheels accumulate). No test suite — manual testing in terminal using `test_data/` samples.

## Architecture

The app is a Textual TUI with three layers: **widgets** (UI components), **viewers** (file-type-specific previews), and **utils** (shared logic).

### Widget communication
`FileBrowser` posts messages (`FileSelected`, `FileHighlighted`, `DirectoryChanged`) that `app.py` handles. Never call app methods directly from the browser. `app.py` coordinates all widget interactions — opening/closing preview, split pane management, pins/history modals.

### Viewer registry
Viewers register in `app.py` via `registry.register(ViewerClass)`. Each viewer declares `supported_extensions()` and `priority()`. The registry picks the highest-priority match. Unknown files get a binary heuristic (peek 512 bytes for null bytes) — text falls to TextViewer, binary to FallbackViewer. To add a new viewer: subclass `BaseViewer`, implement `supported_extensions()` and `load_content()`, register it in `app.py`.

### Background I/O
All file reads and directory scans use `@work(thread=True, exclusive=True)` workers. Results pass back via `app.call_from_thread()`. A generation counter (`_load_gen`) prevents stale results from overwriting newer loads. Never access UI widgets from `_load_directory()` — all UI updates happen in `_populate_list()` which runs on the main thread.

### DataTable file listing
The file browser uses `DataTable(cursor_type="row", show_header=False)` for virtual scrolling (handles 10k+ files). Row keys map to a `_path_map: dict[str, Path]` for path lookups. Columns are dynamic — permissions column appears only when toggled.

### InputMode enum
Input states (search, editor path, touch, rename, mkdir, shell command) are tracked with `InputMode`. A single `_finish_input()` handles cleanup for all modes. Each mode has a hidden `Input` widget toggled visible. When adding a new input mode: add to the enum, add to `_INPUT_IDS`, add the Input widget in `compose()`, add the action and `@on(Input.Submitted)` handler.

### Split preview
`Horizontal` container wraps FileBrowser + PreviewPanel. `P` toggles split (45%/55% widths). Full-screen preview hides the browser. Split preview updates use `@work(exclusive=True, group="split-preview")` with 100ms debounce.

### Git status indicators
`_get_git_status()` runs `git rev-parse --show-prefix` to get the repo-relative prefix, then `git status --porcelain -unormal .`. Paths are stripped of the prefix to match direct children. Runs in the background thread alongside directory scanning.

### Config directory
All config resolves through `config_dir()` in `utils/config.py`:
1. `$NCVIEW_CONFIG_DIR` (explicit override)
2. `$XDG_CONFIG_HOME/ncview` (XDG standard)
3. `~/.config/ncview` (default)

Files: `pins.json`, `history.json`, `lastdir` (quit-and-cd).

### Clipboard
`copy_to_clipboard()` tries native tools when not in SSH (pbcopy, wl-copy, xclip, xsel, clip.exe), falls back to OSC 52 over SSH. OSC 52 requires terminal opt-in (e.g. iTerm2 "Applications in terminal may access clipboard").

### Symlinks and paths
Navigation paths use `.absolute()` not `.resolve()` so symlinked paths display as navigated. Storage paths (pins, history) use `.resolve()` for deduplication. Symlink targets show inline as `→ target`.

## CLI routing

Subcommands are routed via `sys.argv[1]` checks before argparse to avoid conflicts between subparsers and the positional browse path. When adding subcommands, add to the `if` chain in `main()` before the argparse fallback.

## Key gotchas

- Status bar hints are split across `_BROWSER_LINE1_BASE`, `_BROWSER_LINE1_SEARCH`, `_BROWSER_LINE2`, `_PREVIEW_LINE1`, `_PREVIEW_LINE2` — update the right set when adding keybindings
- `on_key()` in FileBrowser intercepts backspace/left/right before DataTable consumes them
- `PreviewPanel.show_file()` is async — removes old viewer, creates new, mounts it
- Permissions and symlink data come from the same `stat_cache` / `os.scandir()` — no extra I/O
- The `%` shell command uses `app.suspend()` to drop back to the raw terminal, then reloads the directory on return
