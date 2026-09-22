"""Daily candles for the chart on the page: unadjusted OHLC, the way a trader sees a stock.

Rebuilt by the daily job, so it is at most a day behind; the 15-minute quotes document carries
the current session. Compact on purpose: the page loads this lazily when a chart is opened.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from .. import __version__
from ..config import Config

SCHEMA = "oilbeta.candles/1"


def _rows(frame: pd.DataFrame) -> list[list]:
    rows = []
    for day, (o, h, lo, c) in zip(frame.index, frame[["Open", "High", "Low", "Close"]].itertuples(index=False)):
        if not (np.isfinite(o) and np.isfinite(h) and np.isfinite(lo) and np.isfinite(c)):
            continue
        rows.append([day.strftime("%Y-%m-%d"), round(float(o), 3), round(float(h), 3), round(float(lo), 3), round(float(c), 3)])
    return rows


def build(cfg: Config, daily: dict[str, pd.DataFrame], now: datetime | None = None) -> dict:
    """`daily` is {ticker: OHLC frame indexed by date}. Names come from the config."""
    now = (now or datetime.now(UTC)).astimezone(UTC)
    names = {cfg.oil_ticker: cfg.study.factors.oil.name, cfg.market.late_ticker: cfg.market.name, **cfg.names}
    fx = cfg.context.get("usdnok")
    if fx:
        names[fx] = "USD/NOK"
    series = {}
    through = None
    for ticker, frame in daily.items():
        if ticker not in names or frame is None or frame.empty:
            continue
        rows = _rows(frame)
        if not rows:
            continue
        series[ticker] = {"name": names[ticker], "sector": cfg.sector_of.get(ticker), "bars": rows}
        last = rows[-1][0]
        through = max(through or last, last)
    return {
        "schema": SCHEMA,
        "generated_utc": now.isoformat(timespec="seconds"),
        "source": {"study": "oslo-oil-sensitivity", "version": __version__, "prices": "Yahoo Finance, unadjusted daily OHLC"},
        "through": through,
        "series": series,
    }


def write(doc: dict, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    return path
