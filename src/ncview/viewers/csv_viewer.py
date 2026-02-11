"""CSV/TSV viewer — Schema + scrollable DataTable + Stats via Polars.

Uses Polars for fast reading and analysis. Handles large files by
only loading the first N rows for the data preview and stats.
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
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB


class CsvViewer(BaseViewer):
    """Displays CSV/TSV files with Schema, Data, and Stats tabs."""

    DEFAULT_CSS = """
    CsvViewer {
        height: 1fr;
    }
    CsvViewer > #csv-info {
        height: auto;
        padding: 0 1;
        background: $primary-background;
        color: $text;
    }
    CsvViewer TabbedContent {
        height: 1fr;
    }
    CsvViewer TabPane {
        height: 1fr;
        padding: 0;
    }
    CsvViewer DataTable {
        height: 1fr;
    }
    CsvViewer #csv-schema-content {
        height: 1fr;
    }
    CsvViewer #csv-stats-content {
        height: 1fr;
    }
    """

    def __init__(self, path: Path, **kwargs) -> None:
        super().__init__(path, **kwargs)
        self._stats_loaded = False
        self._separator = "\t" if path.suffix.lower() in (".tsv", ".tab") else ","

    @staticmethod
    def supported_extensions() -> set[str]:
        return {".csv", ".tsv", ".tab"}

    @staticmethod
    def priority() -> int:
        return 10  # Higher than TextViewer (-1)

    def compose(self):
        yield Static(id="csv-info")
        with TabbedContent("Data", "Schema", "Stats", initial="csv-data-tab"):
            with TabPane("Data", id="csv-data-tab"):
                yield DataTable(id="csv-data-table", cursor_type="row")
            with TabPane("Schema", id="csv-schema-tab"):
                yield Static(id="csv-schema-content", markup=False)
            with TabPane("Stats", id="csv-stats-tab"):
                yield Static(
                    "Switch to this tab to compute statistics...",
                    id="csv-stats-content",
                    markup=False,
                )

    async def load_content(self) -> None:
        self._load_data()

    @on(TabbedContent.TabActivated)
    def _on_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        if event.pane.id == "csv-stats-tab" and not self._stats_loaded:
            self._stats_loaded = True
            self._load_stats()

    @work(thread=True)
    def _load_data(self) -> None:
        """Read CSV and populate info bar, schema, and data table."""
        import polars as pl

        info_widget = self.query_one("#csv-info", Static)
        schema_widget = self.query_one("#csv-schema-content", Static)
        dt = self.query_one("#csv-data-table", DataTable)

        try:
            file_size = self.path.stat().st_size
            if file_size > MAX_FILE_SIZE:
                self.app.call_from_thread(
                    info_widget.update,
                    Text(
                        f"File too large ({file_size / 1024 / 1024:.1f} MB > {MAX_FILE_SIZE // 1024 // 1024} MB limit)",
                        style="bold red",
                    ),
                )
                return

            # Read full file to get row count, but only keep preview rows for display
            lf = pl.scan_csv(
                self.path,
                separator=self._separator,
                infer_schema_length=10_000,
                ignore_errors=True,
            )
            # Get schema from lazy frame (no data read)
            schema = lf.collect_schema()
            col_names = schema.names()
            col_types = [str(schema[name]) for name in col_names]

            # Count total rows (requires a scan)
            num_rows = lf.select(pl.len()).collect().item()
            num_cols = len(col_names)

            # --- Info bar ---
            sep_label = "TSV" if self._separator == "\t" else "CSV"
            info = Text()
            info.append(f"{num_rows:,} rows", style="bold cyan")
            info.append(f"  {num_cols} cols", style="dim")
            info.append(f"  {human_size(file_size)}", style="dim")
            info.append(f"  {sep_label}", style="dim")
            self.app.call_from_thread(info_widget.update, info)

            # --- Schema tab ---
            table = RichTable(title=f"{sep_label} Schema", expand=True)
            table.add_column("#", style="dim", width=4)
            table.add_column("Column", style="bold cyan")
            table.add_column("Type", style="green")

            for i, (name, dtype) in enumerate(zip(col_names, col_types)):
                table.add_row(str(i), name, dtype)

            table.caption = f"Total rows: {num_rows:,}  |  File size: {human_size(file_size)}"
            self.app.call_from_thread(schema_widget.update, table)

            # --- Data tab ---
            df = lf.head(DATA_PREVIEW_ROWS).collect()

            def _add_columns():
                dt.add_column("#", key="__row__")
                for col_name in col_names:
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
                info_widget.update,
                Text(f"Error reading file: {e}", style="bold red"),
            )

    @work(thread=True)
    def _load_stats(self) -> None:
        """Compute .describe() on first N rows."""
        import polars as pl

        widget = self.query_one("#csv-stats-content", Static)
        try:
            self.app.call_from_thread(
                widget.update, Text("Computing statistics...", style="italic dim")
            )

            df = pl.scan_csv(
                self.path,
                separator=self._separator,
                infer_schema_length=10_000,
                ignore_errors=True,
            ).head(STATS_ROWS).collect()

            desc = df.describe()

            table = RichTable(
                title=f"Statistics (first {min(STATS_ROWS, len(df)):,} rows)",
                expand=True,
            )
            for col_name in desc.columns:
                style = "bold cyan" if col_name == "statistic" else "white"
                table.add_column(col_name, style=style)

            for i in range(len(desc)):
                row = [
                    str(desc[col][i]) if desc[col][i] is not None else ""
                    for col in desc.columns
                ]
                table.add_row(*row)

            self.app.call_from_thread(widget.update, table)
        except Exception as e:
            self.app.call_from_thread(
                widget.update,
                Text(f"Error computing stats: {e}", style="bold red"),
            )
