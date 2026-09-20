"""CSV tables and one Excel workbook: every number in the report, in a form that can be checked."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..pipeline import Results

EXCEL_SHEETS = {
    "betas_full": "Betas (full sample)",
    "scenarios": "Scenarios (recent betas)",
    "shock_betas": "Shock betas",
    "event_summary_total": "Event CARs (total)",
    "event_summary_relative": "Event CARs (vs index)",
    "events": "Oil shocks",
    "oos_summary": "Out-of-sample summary",
    "oos_events": "Out-of-sample by event",
    "regime_direction": "Regime up vs down",
    "regime_volatility": "Regime calm vs turbulent",
    "pca_summary": "PCA summary",
    "pca_loadings": "PCA loadings",
    "validation": "Data validation",
}


def write_tables(res: Results, out_dir: Path) -> None:
    tables = out_dir / "tables"
    tables.mkdir(parents=True, exist_ok=True)
    aggregates = set(res.meta.index[res.meta["kind"] != "stock"])
    for name, df in res.tables.items():
        if name == "event_cars":                       # large intermediate, rebuilt on every run
            continue
        if name == "betas_rolling":                    # stocks' rolling paths stay in memory; keep the repo small
            df = df[df["unit"].isin(aggregates)]
        df.to_csv(tables / f"{name}.csv", float_format="%.5f")
    with pd.ExcelWriter(out_dir / "oil_sensitivity.xlsx", engine="openpyxl") as xl:
        for name, sheet in EXCEL_SHEETS.items():
            df = res.tables[name].copy()
            for col in df.select_dtypes(include=["datetimetz", "datetime"]).columns:
                df[col] = df[col].dt.date
            df.to_excel(xl, sheet_name=sheet[:31])
            ws = xl.sheets[sheet[:31]]
            ws.freeze_panes = "B2"
            for cells in ws.columns:
                width = max(len(str(c.value)) if c.value is not None else 0 for c in cells[:60])
                ws.column_dimensions[cells[0].column_letter].width = min(max(10, width + 2), 44)
