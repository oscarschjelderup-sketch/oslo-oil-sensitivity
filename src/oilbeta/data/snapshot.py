"""Download and cache the price snapshot, and describe it in a manifest.

The sample end date is pinned in the config and the snapshot is fingerprinted (SHA-256) in
data/manifest.json, so a set of results can always be traced to the exact prices behind it.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta

import pandas as pd

from ..config import Config


def fetch_prices(cfg: Config, refresh: bool = False) -> pd.DataFrame:
    """Daily adjusted closes for every ticker in the config (cached on disk)."""
    path = cfg.prices_path
    if path.exists() and not refresh:
        return pd.read_csv(path, index_col=0, parse_dates=True)

    import yfinance as yf

    end_exclusive = (pd.Timestamp(cfg.end) + timedelta(days=1)).strftime("%Y-%m-%d")
    raw = yf.download(cfg.download_list, start=cfg.start, end=end_exclusive,
                      auto_adjust=True, progress=False, threads=True)
    prices = raw["Close"].sort_index()
    prices.index = pd.to_datetime(prices.index).tz_localize(None)
    prices.index.name = "Date"
    prices = prices[cfg.download_list].dropna(how="all")

    missing = [t for t in cfg.download_list if prices[t].notna().sum() == 0]
    if missing:
        raise RuntimeError(f"No data returned for: {missing}")
    for factor in (cfg.oil_ticker, cfg.market.late_ticker):     # a half-empty download must not pass as fresh
        last = prices[factor].last_valid_index()
        if last < pd.Timestamp(cfg.end) - timedelta(days=10):
            raise RuntimeError(f"{factor} only reaches {last.date()}, expected data up to {cfg.end}")

    cfg.raw_dir.mkdir(parents=True, exist_ok=True)
    prices.to_csv(path, float_format="%.6f")
    _write_manifest(cfg, prices, path)
    return pd.read_csv(path, index_col=0, parse_dates=True)


def _write_manifest(cfg: Config, prices: pd.DataFrame, path) -> None:
    manifest = {
        "created_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": "Yahoo Finance via yfinance (auto-adjusted closes)",
        "sample": {"start": cfg.start, "end": cfg.end},
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "series": {
            t: {"first": str(prices[t].first_valid_index().date()),
                "last": str(prices[t].last_valid_index().date()),
                "rows": int(prices[t].notna().sum())}
            for t in prices.columns
        },
    }
    cfg.manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
