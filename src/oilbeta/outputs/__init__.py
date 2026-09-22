"""Everything that turns results into files: tables, figures, the report, the live monitor."""
from __future__ import annotations

from pathlib import Path

from ..pipeline import Results
from . import candles, dashboard, factsheet, figures, quotes, report, tables

__all__ = ["candles", "dashboard", "factsheet", "figures", "quotes", "report", "tables", "write_all", "write_live"]


def write_all(res: Results) -> dict[str, Path]:
    """The full set for the pinned paper: tables, workbook, figures, report and a monitor of the same snapshot."""
    out = res.cfg.results_dir
    tables.write_tables(res, out)
    figure_paths = figures.save_all(res, out / "figures")
    report.write_html(res, figure_paths, out / "report.html")
    dashboard.write(res, out)
    return {"report": out / "report.html", "dashboard": out / "dashboard.html", "workbook": out / "oil_sensitivity.xlsx",
            "tables": out / "tables", "figures": out / "figures"}


def write_live(res: Results) -> dict[str, Path]:
    """The live set: tables, workbook and the monitor. No narrative report: its claims belong to the pinned snapshot."""
    out = res.cfg.results_dir
    tables.write_tables(res, out)
    return dashboard.write(res, out)
