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
from textual.widgets import DataTable, Static, TabbedContent, TabPane

from ncview.utils.file_info import human_size
from ncview.viewers.base import BaseViewer

DATA_PREVIEW_ROWS = 1_000
STATS_ROWS = 10_000


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
    ParquetViewer #schema-content {
        height: 1fr;
    }
    ParquetViewer #stats-content {
        height: 1fr;
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

    def compose(self):
        yield Static(id="pq-info")
        with TabbedContent("Data", "Schema", "Stats", initial="data-tab"):
            with TabPane("Data", id="data-tab"):
                yield DataTable(id="data-table", cursor_type="row")
            with TabPane("Schema", id="schema-tab"):
                yield Static(id="schema-content", markup=False)
            with TabPane("Stats", id="stats-tab"):
                yield Static("Switch to this tab to compute statistics...", id="stats-content", markup=False)

    async def load_content(self) -> None:
        self._load_metadata()
        self._load_data()

    @on(TabbedContent.TabActivated)
    def _on_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        if event.pane.id == "stats-tab" and not self._stats_loaded:
            self._stats_loaded = True
            self._load_stats()

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
            table = RichTable(title="Parquet Schema", expand=True)
            table.add_column("#", style="dim", width=4)
            table.add_column("Column", style="bold cyan")
            table.add_column("Type", style="green")

            for i in range(num_cols):
                field = arrow_schema.field(i)
                table.add_row(str(i), field.name, str(field.type))

            table.caption = f"Total rows: {num_rows:,}  |  Row groups: {num_row_groups}  |  File size: {human_size(file_size)}"
            self.app.call_from_thread(schema_widget.update, table)

        except Exception as e:
            self.app.call_from_thread(info_widget.update, Text(f"Error reading metadata: {e}", style="bold red"))

    @work(thread=True)
    def _load_data(self) -> None:
        """Load first N rows via lazy scan with predicate pushdown."""
        import polars as pl

        dt = self.query_one("#data-table", DataTable)
        try:
            df = pl.scan_parquet(self.path).head(DATA_PREVIEW_ROWS).collect()

            def _add_columns():
                dt.add_column("#", key="__row__")
                for col_name in df.columns:
                    dt.add_column(col_name, key=col_name)

            self.app.call_from_thread(_add_columns)

            str_df = df.cast({col: pl.Utf8 for col in df.columns}).fill_null("null")
            raw_rows = str_df.rows()
            rows = [tuple([str(i)] + list(r)) for i, r in enumerate(raw_rows)]

            def _add_rows():
                dt.add_rows(rows)

            self.app.call_from_thread(_add_rows)
        except Exception as e:
            self.app.call_from_thread(
                dt.add_column, f"Error: {e}", key="error"
            )

    @work(thread=True)
    def _load_stats(self) -> None:
        """Compute .describe() on first N rows. Only called when stats tab is activated."""
        import polars as pl

        widget = self.query_one("#stats-content", Static)
        try:
            self.app.call_from_thread(widget.update, Text("Computing statistics...", style="italic dim"))

            df = pl.scan_parquet(self.path).head(STATS_ROWS).collect()
            desc = df.describe()

            table = RichTable(title=f"Statistics (first {STATS_ROWS:,} rows)", expand=True)
            for col_name in desc.columns:
                style = "bold cyan" if col_name == "statistic" else "white"
                table.add_column(col_name, style=style)

            for i in range(len(desc)):
                row = [str(desc[col][i]) if desc[col][i] is not None else "" for col in desc.columns]
                table.add_row(*row)

            self.app.call_from_thread(widget.update, table)
        except Exception as e:
            self.app.call_from_thread(widget.update, Text(f"Error computing stats: {e}", style="bold red"))
