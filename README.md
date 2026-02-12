# ncview

Terminal file browser with vim keybindings, inspired by [ncdu](https://dev.yorhel.nl/ncdu). Built with [Textual](https://textual.textualize.io/), [Polars](https://pola.rs/), and [PyArrow](https://arrow.apache.org/docs/python/).

[![PyPI](https://img.shields.io/badge/pypi-v0.3.8-blue)](https://pypi.org/project/ncview/)
![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)

## Features

- **Vim-style navigation** — `j`/`k`/`h`/`l`, arrow keys, and more
- **Parquet viewer** — schema, scrollable data table (first 1K rows), and statistics via Polars. Handles 50GB+ files efficiently using PyArrow metadata reads (O(1), no full scan)
- **CSV/TSV viewer** — schema, scrollable data table, and statistics via Polars. Tab-separated files auto-detected
- **JSON viewer** — collapsible/expandable tree with color-coded values
- **Text viewer** — syntax highlighting for 50+ languages via Rich
- **Fallback viewer** — file metadata for unknown/binary types

## Install

```bash
# Clone and install
git clone git@github.com:dannyfriar/ncview.git
cd ncview
uv venv --python 3.12
uv pip install -e .
```

## Usage

```bash
ncview              # browse current directory
ncview /some/path   # browse a specific directory
ncview --help       # show usage
```

## Keybindings

### File browser

| Key | Action |
|-----|--------|
| `j` / `k` / `↑` / `↓` | Move cursor up/down |
| `l` / `Enter` / `→` | Enter directory or open file preview |
| `h` / `Backspace` / `←` | Go to parent directory |
| `g` / `G` | Jump to top/bottom |
| `.` | Toggle hidden files |
| `s` | Cycle sort (name → size → modified) |
| `/` | Search in current directory |
| `n` / `N` | Jump to next/previous search match |
| `P` | Toggle split preview pane |
| `e` | Open file in `$EDITOR` (default: `vim`) |
| `q` / `Ctrl+C` | Quit |

### Preview (all file types)

| Key | Action |
|-----|--------|
| `h` / `Backspace` / `←` / `Escape` | Close preview, return to browser |
| `j` / `k` | Scroll up/down |
| `Ctrl+D` / `Ctrl+U` | Page down/up |
| `q` / `Ctrl+C` | Quit |

### Parquet viewer

| Key | Action |
|-----|--------|
| `1` | Data tab (default) |
| `2` | Schema tab |
| `3` | Stats tab (computed on first visit) |
| `↑` / `↓` | Scroll through rows in data table |

### JSON viewer

| Key | Action |
|-----|--------|
| `j` / `k` | Move cursor through visible nodes |
| `l` | Expand node (or move to first child if already expanded) |
| `h` | Collapse node (or move to parent if leaf/already collapsed) |
| `Space` / `Enter` | Toggle expand/collapse |
| `g` / `G` | Jump to top/bottom |

## Test data

The `test_data/` directory contains sample files for testing:

- `users.parquet` — 500 rows, 7 columns
- `sales.parquet` — 2,000 rows, 7 columns (with nulls)
- `numeric_series.parquet` — 5,000 rows, 6 columns
- `sample.json` — nested JSON with arrays and objects
