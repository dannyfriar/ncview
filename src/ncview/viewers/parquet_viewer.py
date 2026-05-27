"""Parquet viewer — Schema + scrollable DataTable + Stats via Polars.

Designed to handle very large files (50GB+):
- Schema and row count read from parquet footer metadata via pyarrow (O(1))
- Data preview uses Polars lazy scan with .head() pushdown (reads minimal row groups)
- Stats computed lazily on first tab visit, also with .head() pushdown
- All I/O runs in thread workers to keep the UI responsive
"""

from __future__ import annotations

from pathlib import Path

from rich.table import Table as RichTable
from rich.text import Text
from textual import on, work
from textual.containers import VerticalScroll
from textual.events import Key
from textual.widgets import DataTable, Input, Static, TabbedContent, TabPane

from ncview.utils.file_info import human_size
from ncview.viewers.base import BaseViewer

DATA_PREVIEW_ROWS = 1_000
STATS_ROWS = 10_000
MAX_DISPLAY_COLS = 50


class _PqScroll(VerticalScroll):
    """VerticalScroll with vim-style j/k scrolling for parquet schema/stats."""

    BINDINGS = [
        ("j", "scroll_down", "Down"),
        ("k", "scroll_up", "Up"),
        ("g", "scroll_home", "Top"),
        ("G", "scroll_end", "Bottom"),  # noqa: E741
        ("ctrl+d", "page_down", "Page down"),
        ("ctrl+u", "page_up", "Page up"),
    ]


class _PqDataTable(DataTable):
    """DataTable with vim-style j/k/h/l + arrow keys for navigation and scroll."""

    BINDINGS = [
        ("j", "cursor_down", "Down"),
        ("k", "cursor_up", "Up"),
        ("h", "scroll_left", "Scroll left"),
        ("l", "scroll_right", "Scroll right"),
        ("left", "scroll_left", "Scroll left"),
        ("right", "scroll_right", "Scroll right"),
        ("g", "scroll_top", "Top"),
        ("G", "scroll_bottom", "Bottom"),  # noqa: E741
        ("ctrl+d", "page_down", "Page down"),
        ("ctrl+u", "page_up", "Page up"),
    ]

    def action_scroll_top(self) -> None:
        self.move_cursor(row=0)

    def action_scroll_bottom(self) -> None:
        if self.row_count > 0:
            self.move_cursor(row=self.row_count - 1)


class ParquetViewer(BaseViewer):
    """Displays parquet files with Schema, Data, and Stats tabs."""

    DEFAULT_CSS = """
    ParquetViewer {
        height: 1fr;
    }
    ParquetViewer > #pq-info {
        height: auto;
        padding: 0 1;
        background: $primary-background;
        color: $text;
    }
    ParquetViewer > #pq-hint {
        height: 1;
        padding: 0 1;
        color: #75715e;
    }
    ParquetViewer > #pq-search {
        dock: bottom;
        height: 0;
        overflow: hidden;
    }
    ParquetViewer > #pq-search.visible {
        height: auto;
    }
    ParquetViewer TabbedContent {
        height: 1fr;
    }
    ParquetViewer TabPane {
        height: 1fr;
        padding: 0;
    }
    ParquetViewer DataTable {
        height: 1fr;
    }
    ParquetViewer VerticalScroll {
        height: 1fr;
    }
    ParquetViewer VerticalScroll:focus {
        border: none;
    }
    ParquetViewer #schema-content {
        height: auto;
    }
    ParquetViewer #stats-content {
        height: auto;
    }
    """

    @staticmethod
    def supported_extensions() -> set[str]:
        return {".parquet"}

    @staticmethod
    def priority() -> int:
        return 10

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._stats_loaded = False
        self._schema_fields: list[tuple[int, str, str]] = []
        self._search_active = False
        self._search_query = ""
        self._data_filtered = False  # True if data tab is showing a filtered column set

    def compose(self):
        yield Static(id="pq-info")
        hint = Text()
        hint.append("/", style="bold #66d9ef")
        hint.append(" search columns  ", style="#75715e")
        hint.append("j/k", style="bold #66d9ef")
        hint.append(" scroll  ", style="#75715e")
        hint.append("1/2/3", style="bold #66d9ef")
        hint.append(" tabs", style="#75715e")
        yield Static(hint, id="pq-hint")
        with TabbedContent("1 Data", "2 Schema", "3 Stats", initial="data-tab"):
            with TabPane("1 Data", id="data-tab"):
                yield _PqDataTable(id="data-table", cursor_type="row")
            with TabPane("2 Schema", id="schema-tab"):
                with _PqScroll():
                    yield Static(id="schema-content", markup=False)
            with TabPane("3 Stats", id="stats-tab"):
                with _PqScroll():
                    yield Static("Switch to this tab to compute statistics...", id="stats-content", markup=False)
        yield Input(placeholder="Search columns...", id="pq-search")

    async def load_content(self) -> None:
        self._load_metadata()
        self._load_data()

    @on(TabbedContent.TabActivated)
    def _on_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        if event.pane.id == "stats-tab" and not self._stats_loaded:
            self._stats_loaded = True
            self._load_stats()
        # Focus the scroll container so j/k/arrows work
        try:
            scroll = event.pane.query_one(_PqScroll)
            scroll.focus()
        except Exception:
            pass

    def _render_schema(self) -> None:
        """Rebuild the schema RichTable, applying _search_query as a filter."""
        query = self._search_query.lower()
        if query:
            matches = [f for f in self._schema_fields if query in f[1].lower()]
            title = f"Parquet Schema  ({len(matches)} of {len(self._schema_fields)} cols match '/{self._search_query}')"
        else:
            matches = self._schema_fields
            title = "Parquet Schema"
        table = RichTable(title=title, expand=True)
        table.add_column("#", style="dim", width=4)
        table.add_column("Column", style="bold cyan")
        table.add_column("Type", style="green")
        for idx, name, dtype in matches:
            table.add_row(str(idx), name, dtype)
        try:
            self.query_one("#schema-content", Static).update(table)
        except Exception:
            pass

    def on_key(self, event: Key) -> None:
        """Capture `/` on schema or data tab to start column search."""
        if self._search_active:
            event.prevent_default()
            event.stop()
            tc = self.query_one(TabbedContent)
            on_data = tc.active == "data-tab"
            if event.key == "escape":
                self._search_query = ""
                self._end_search()
                self._render_schema()
                # If data was filtered, restore full view
                if on_data and self._data_filtered:
                    self._data_filtered = False
                    self._load_data()
            elif event.key == "enter":
                self._end_search()
                # On data tab, Enter commits the filter and reloads data
                if on_data:
                    self._data_filtered = bool(self._search_query)
                    self._load_data()
            elif event.key == "backspace":
                inp = self.query_one("#pq-search", Input)
                inp.value = inp.value[:-1]
                self._search_query = inp.value
                self._render_schema()
            elif event.character and event.character.isprintable():
                inp = self.query_one("#pq-search", Input)
                inp.value += event.character
                self._search_query = inp.value
                self._render_schema()
            return
        if event.key == "slash":
            tc = self.query_one(TabbedContent)
            if tc.active in ("schema-tab", "data-tab"):
                event.prevent_default()
                event.stop()
                self._start_search()

    def _start_search(self) -> None:
        self._search_active = True
        inp = self.query_one("#pq-search", Input)
        inp.value = self._search_query
        inp.add_class("visible")

    def _end_search(self) -> None:
        self._search_active = False
        self.query_one("#pq-search", Input).remove_class("visible")
        # Refocus the active tab's primary widget
        try:
            tc = self.query_one(TabbedContent)
            if tc.active == "data-tab":
                self.query_one("#data-table", DataTable).focus()
            else:
                self.query_one(f"#{tc.active}", TabPane).query_one(_PqScroll).focus()
        except Exception:
            pass

    @work(thread=True)
    def _load_metadata(self) -> None:
        """Read schema and row count from parquet footer (O(1), no data scan)."""
        import pyarrow.parquet as pq

        info_widget = self.query_one("#pq-info", Static)
        schema_widget = self.query_one("#schema-content", Static)
        try:
            pf = pq.ParquetFile(self.path)
            metadata = pf.metadata
            arrow_schema = pf.schema_arrow

            num_rows = metadata.num_rows
            num_cols = metadata.num_columns
            num_row_groups = metadata.num_row_groups
            file_size = self.path.stat().st_size

            # --- Info bar ---
            info = Text()
            info.append(f"{num_rows:,} rows", style="bold cyan")
            info.append(f"  {num_cols} cols", style="dim")
            info.append(f"  {num_row_groups} row groups", style="dim")
            info.append(f"  {human_size(file_size)}", style="dim")
            self.app.call_from_thread(info_widget.update, info)

            # --- Schema tab ---
            fields = [(i, arrow_schema.field(i).name, str(arrow_schema.field(i).type)) for i in range(num_cols)]
            self._schema_fields = fields
            self.app.call_from_thread(self._render_schema)

        except Exception as e:
            self.app.call_from_thread(info_widget.update, Text(f"Error reading metadata: {e}", style="bold red"))

    @work(thread=True, exclusive=True)
    def _load_data(self) -> None:
        """Load first N rows via lazy scan with predicate pushdown.

        Respects self._search_query when self._data_filtered is True — only
        loads columns whose name contains the query.
        """
        import polars as pl

        dt = self.query_one("#data-table", DataTable)
        try:
            scan = pl.scan_parquet(self.path)
            all_cols = scan.collect_schema().names()
            if self._data_filtered and self._search_query:
                q = self._search_query.lower()
                matching = [c for c in all_cols if q in c.lower()]
            else:
                matching = all_cols
            truncated = len(matching) > MAX_DISPLAY_COLS
            display_cols = matching[:MAX_DISPLAY_COLS]
            df = (
                scan.select(display_cols).head(DATA_PREVIEW_ROWS).collect()
                if display_cols
                else None
            )

            def _add_columns():
                dt.clear(columns=True)
                dt.add_column("#", key="__row__")
                if df is not None:
                    for col_name in df.columns:
                        dt.add_column(col_name, key=col_name)
                if truncated:
                    dt.add_column(f"... +{len(matching) - MAX_DISPLAY_COLS} cols", key="__truncated__")

            self.app.call_from_thread(_add_columns)

            if df is None:
                return
            str_df = df.cast({col: pl.Utf8 for col in df.columns}).fill_null("null")
            raw_rows = str_df.rows()
            suffix = ("",) if truncated else ()
            rows = [tuple([str(i)] + list(r) + list(suffix)) for i, r in enumerate(raw_rows)]

            def _add_rows():
                dt.add_rows(rows)

            self.app.call_from_thread(_add_rows)
        except Exception as e:
            def _show_err():
                dt.clear(columns=True)
                dt.add_column(f"Error: {e}", key="error")
            self.app.call_from_thread(_show_err)

    @work(thread=True)
    def _load_stats(self) -> None:
        """Compute .describe() on first N rows. Only called when stats tab is activated."""
        import polars as pl

        widget = self.query_one("#stats-content", Static)
        try:
            self.app.call_from_thread(widget.update, Text("Computing statistics...", style="italic dim"))

            scan = pl.scan_parquet(self.path)
            all_cols = scan.collect_schema().names()
            display_cols = all_cols[:MAX_DISPLAY_COLS]
            df = scan.select(display_cols).head(STATS_ROWS).collect()
            desc = df.describe()

            stats_title = f"Statistics (first {STATS_ROWS:,} rows"
            if len(all_cols) > MAX_DISPLAY_COLS:
                stats_title += f", first {MAX_DISPLAY_COLS} cols"
            stats_title += ")"
            table = RichTable(title=stats_title, expand=True)
            for col_name in desc.columns:
                style = "bold cyan" if col_name == "statistic" else "white"
                table.add_column(col_name, style=style)

            for i in range(len(desc)):
                row = [str(desc[col][i]) if desc[col][i] is not None else "" for col in desc.columns]
                table.add_row(*row)

            self.app.call_from_thread(widget.update, table)
        except Exception as e:
            self.app.call_from_thread(widget.update, Text(f"Error computing stats: {e}", style="bold red"))
