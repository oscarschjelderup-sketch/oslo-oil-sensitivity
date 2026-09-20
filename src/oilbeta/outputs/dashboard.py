"""The live monitor: one interactive, self-contained HTML page rebuilt on every run.

The page never makes a claim the numbers could outgrow: every sentence in it is assembled
from the payload built here. Two files are written:

* dashboard.html  - complete document, opens from disk
* dashboard.page.html - the same page without the document wrapper (for hosts that add their own)
"""
from __future__ import annotations

import json
import math
import os
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path

import numpy as np
import pandas as pd

from .. import MARKET, OIL
from ..analysis import regimes, scenarios
from ..pipeline import Results

INDEX_NAME = "Oslo Børs index"
ROLLING_STEP = 4          # weeks between plotted points; the latest point is always kept
RECENT_SHOCKS = 8


def _clean(x):
    """JSON-safe number: NaN/inf -> None, floats rounded."""
    if x is None:
        return None
    if isinstance(x, (np.floating, float)):
        return None if not math.isfinite(x) else round(float(x), 4)
    if isinstance(x, (np.integer,)):
        return int(x)
    return x


def _pct_change(series: pd.Series, days: int) -> float | None:
    s = series.dropna()
    return None if len(s) <= days else float(s.iloc[-1] / s.iloc[-1 - days] - 1)


def _units(res: Results) -> list[dict]:
    sc, full, roll = res.tables["scenarios"], res.tables["betas_full"], res.tables["betas_rolling"]
    out = []
    for unit, row in sc.iterrows():
        r = roll.loc[roll["unit"] == unit, "beta_oil_total"]
        out.append({
            "id": unit, "name": INDEX_NAME if unit == MARKET else row["name"], "kind": row["kind"],
            "sector": row["sector"] if row["kind"] == "stock" else "",
            "beta": _clean(row["beta_oil_total"]), "lo": _clean(row["total_lo"]), "hi": _clean(row["total_hi"]),
            "beta_full": _clean(full.loc[unit, "beta_oil_total"]) if unit in full.index else None,
            "beta_mkt": _clean(full.loc[unit, "beta_mkt"]) if unit in full.index else None,
            "roll_now": _clean(r.iloc[-1]) if len(r) else None,
            "roll_13w": _clean(r.iloc[-14]) if len(r) > 13 else None,
            "r2_oil": _clean(row["r2_oil_only"]), "non_oil_vol": _clean(row["non_oil_vol"]),
        })
    return out


def _rolling(res: Results, unit_ids: list[str]) -> dict:
    roll = res.tables["betas_rolling"]
    dates = roll.loc[roll["unit"] == MARKET, "date"].reset_index(drop=True)
    keep = sorted(range(len(dates) - 1, -1, -ROLLING_STEP))
    grid = dates.iloc[keep]
    series = {}
    for unit in unit_ids:
        g = roll[roll["unit"] == unit].set_index("date").reindex(grid)
        series[unit] = {"b": [_clean(v) for v in g["beta_oil_total"].round(3)],
                        "lo": [_clean(v) for v in g["total_lo"].round(3)],
                        "hi": [_clean(v) for v in g["total_hi"].round(3)]}
    return {"dates": [d.strftime("%Y-%m-%d") for d in grid], "series": series}


def _shocks(res: Results) -> dict:
    ev, cars, oos = res.tables["events"], res.tables["event_cars"], res.tables["oos_events"]
    s = res.cfg.scenarios
    aggregates = list(res.meta.index[res.meta["kind"] != "stock"])
    impact = cars[cars["window"] == "impact"].pivot(index="event_id", columns="unit", values="car_total")
    drift = cars[cars["window"] == "drift"].pivot(index="event_id", columns="unit", values="car_total")
    oil_move = cars[cars["window"] == "impact"].groupby("event_id")["oil_move"].first()

    def predicted(event_id) -> pd.Series:
        past = scenarios._past_betas(res.weekly[aggregates], res.weekly[OIL], ev.loc[event_id, "date"],
                                     s.window, s.oos_min_history)
        return np.expm1(past * oil_move.loc[event_id])

    recent = []
    for event_id in list(ev.index[-RECENT_SHOCKS:])[::-1]:
        pred = predicted(event_id)
        recent.append({
            "date": ev.loc[event_id, "date"].strftime("%Y-%m-%d"), "z": _clean(ev.loc[event_id, "z"]),
            "oil_move": _clean(np.expm1(oil_move.loc[event_id])),
            "idx_pred": _clean(pred.get(MARKET)), "idx_real": _clean(np.expm1(impact.loc[event_id, MARKET])),
            "spearman": _clean(oos["spearman_impact"].get(event_id)) if "spearman_impact" in oos else None,
            "complete": bool(np.isfinite(drift.loc[event_id, MARKET])) if event_id in drift.index else False,
        })
    latest = None
    if len(ev):
        event_id = ev.index[-1]
        pred = predicted(event_id)
        rows = [{"name": INDEX_NAME if u == MARKET else u, "kind": res.meta.loc[u, "kind"],
                 "pred": _clean(pred[u]), "real": _clean(np.expm1(impact.loc[event_id, u]))}
                for u in aggregates if u in pred.index and np.isfinite(impact.loc[event_id, u])]
        rows.sort(key=lambda r: -r["pred"])
        latest = {"date": recent[0]["date"], "oil_move": recent[0]["oil_move"], "spearman": recent[0]["spearman"],
                  "n_stocks": _clean(oos["n_stocks"].get(event_id)) if len(oos) else None, "rows": rows}
    return {"recent": recent, "latest": latest}


def build_payload(res: Results) -> dict:
    cfg, T = res.cfg, res.tables
    roll = T["betas_rolling"]
    mroll = roll[roll["unit"] == MARKET]
    now = mroll.iloc[-1]
    oil_weekly = res.weekly[OIL]
    vol_window = cfg.regimes.vol_window
    vol = oil_weekly.rolling(vol_window).std() * math.sqrt(52)
    high = regimes.high_vol_flag(oil_weekly, vol_window)
    ev, oos = T["events"], T["oos_summary"]
    units = _units(res)
    last_shock = None if ev.empty else {"date": ev["date"].iloc[-1].strftime("%Y-%m-%d"), "z": _clean(ev["z"].iloc[-1]),
                                        "oil_day0": _clean(np.expm1(ev["oil_day0"].iloc[-1]))}
    return {
        "meta": {
            "generated": datetime.now(UTC).isoformat(timespec="seconds"),
            "data_through": res.panel.index.max().strftime("%Y-%m-%d"), "sample_start": res.info["sample"]["start"],
            "live": cfg.is_live, "stale": bool(res.info.get("stale", False)),
            "n_stocks": len(cfg.tickers), "n_events": int(len(ev)),
            "roll_window": cfg.betas.rolling_window, "scen_window": cfg.scenarios.window,
            "z_threshold": cfg.events.z_threshold,
            # optional footer links, set by the deploy workflow (relative or absolute URLs)
            "links": {k: v for k, v in {"Research report": os.environ.get("OILBETA_REPORT_URL"),
                                        "Workbook (xlsx)": os.environ.get("OILBETA_WORKBOOK_URL"),
                                        "Code and method": os.environ.get("OILBETA_REPO_URL")}.items() if v},
        },
        "brent": {"last": _clean(res.panel[OIL].iloc[-1]), "chg_1w": _clean(_pct_change(res.panel[OIL], 5)),
                  "chg_1m": _clean(_pct_change(res.panel[OIL], 21))},
        "market": {"beta_now": _clean(now["beta_oil_total"]), "lo": _clean(now["total_lo"]), "hi": _clean(now["total_hi"]),
                   "beta_52w": _clean(mroll["beta_oil_total"].iloc[-53]) if len(mroll) > 52 else None,
                   "beta_full": _clean(T["betas_full"].loc[MARKET, "beta_oil_total"])},
        "regime": {"state": "turbulent" if high.iloc[-1] == 1 else "calm", "vol_now": _clean(vol.iloc[-1]),
                   "vol_median": _clean(vol.expanding(min_periods=52).median().iloc[-1]), "last_shock": last_shock},
        "units": units,
        "rolling": _rolling(res, [u["id"] for u in units]),
        "shocks": _shocks(res),
        "oos": {"n": int(oos.loc["spearman_impact", "n_events"]), "mean": _clean(oos.loc["spearman_impact", "mean"]),
                "t": _clean(oos.loc["spearman_impact", "t"]), "share_pos": _clean(oos.loc["spearman_impact", "share_positive"]),
                "drift_mean": _clean(oos.loc["spearman_drift", "mean"]), "drift_t": _clean(oos.loc["spearman_drift", "t"])},
    }


DATA_FILE = "dashboard-data.js"
MARKER = "<!--__DATA_SCRIPT__-->"


def render(payload: dict) -> dict[str, str]:
    """Three files from one template.

    * ``data_js``  - the payload as ``window.OIL_DATA = {...};``
    * ``page``     - the page with a ``<script src>`` for that file (small; for hosts that
                     take a page plus supporting files)
    * ``document`` - a complete stand-alone document with the payload inlined (opens from disk)
    """
    template = resources.files("oilbeta.outputs").joinpath("templates/dashboard.html").read_text(encoding="utf-8")
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    data_js = "window.OIL_DATA = " + data + ";\n"
    page = template.replace(MARKER, f'<script src="{DATA_FILE}"></script>')
    inline = template.replace(MARKER, "<script>" + data_js + "</script>")
    document = ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width, initial-scale=1">\n</head><body>\n'
                + inline + "\n</body></html>\n")
    return {"data_js": data_js, "page": page, "document": document}


def write(res: Results, out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = build_payload(res)
    parts = render(payload)
    paths = {"dashboard": out_dir / "dashboard.html", "page": out_dir / "dashboard.page.html",
             "data": out_dir / DATA_FILE, "payload": out_dir / "dashboard.json"}
    paths["dashboard"].write_text(parts["document"], encoding="utf-8")
    paths["page"].write_text(parts["page"], encoding="utf-8")
    paths["data"].write_text(parts["data_js"], encoding="utf-8")
    paths["payload"].write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return paths
