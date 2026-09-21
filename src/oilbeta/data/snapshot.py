"""Download and cache price snapshots, and describe them in a manifest.

The sample end date is pinned in the config and every file is fingerprinted (SHA-256) in
data/manifest.json, so a set of results can always be traced to the exact prices behind it.

Three kinds of file live in data/raw/:

* prices.csv            the pinned snapshot. Never rewritten unless `--refresh` is asked for.
* prices_supplement.csv series the study needs but the pinned file does not have (a factor added
                        later). Downloaded for the same date range and fingerprinted separately,
                        so extending the study never changes the original snapshot's hash.
* fred_brent.csv, prices_long.csv   inputs of the robustness check (another oil series, a longer sample).
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

from ..config import Config
from .sources import FredSource, PriceSource, YahooSource


def _read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, index_col=0, parse_dates=True)


def _describe(prices: pd.DataFrame, path: Path, source: PriceSource) -> dict:
    return {
        "created_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": source.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "series": {t: {"first": str(prices[t].first_valid_index().date()), "last": str(prices[t].last_valid_index().date()),
                       "rows": int(prices[t].notna().sum())} for t in prices.columns if prices[t].notna().any()},
    }


def _update_manifest(cfg: Config, key: str | None, entry: dict) -> None:
    """key=None replaces the description of the main snapshot; a key adds or replaces one extra file."""
    path = cfg.manifest_path
    manifest = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if key is None:
        manifest = {**entry, "sample": {"start": cfg.start, "end": cfg.end},
                    **{k: v for k, v in manifest.items() if k == "robustness"}}     # a refresh drops the supplement
    elif "/" in key:
        group, name = key.split("/")
        manifest.setdefault(group, {})[name] = entry
    else:
        manifest[key] = entry
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _save(cfg: Config, prices: pd.DataFrame, path: Path, source: PriceSource, key: str | None) -> pd.DataFrame:
    path.parent.mkdir(parents=True, exist_ok=True)
    prices.to_csv(path, float_format="%.6f")
    _update_manifest(cfg, key, _describe(prices, path, source))
    return _read(path)


def fetch_prices(cfg: Config, refresh: bool = False, source: PriceSource | None = None) -> pd.DataFrame:
    """Daily adjusted closes for every ticker in the config (cached on disk)."""
    source = source or YahooSource()
    path = cfg.prices_path
    if path.exists() and not refresh:
        return _with_supplement(cfg, _read(path), source)

    prices = source.fetch(cfg.download_list, cfg.start, cfg.end)
    missing = [t for t in cfg.download_list if prices[t].notna().sum() == 0]
    if missing:
        raise RuntimeError(f"No data returned for: {missing}")
    for factor in (cfg.oil_ticker, cfg.market.late_ticker):     # a half-empty download must not pass as fresh
        last = prices[factor].last_valid_index()
        if last < pd.Timestamp(cfg.end) - timedelta(days=10):
            raise RuntimeError(f"{factor} only reaches {last.date()}, expected data up to {cfg.end}")
    supplement = _supplement_path(cfg)
    if supplement.exists():                 # a full refresh contains everything; an old supplement would shadow it
        supplement.unlink()
    return _save(cfg, prices, path, source, key=None)


def _supplement_path(cfg: Config) -> Path:
    return cfg.prices_path.with_name(cfg.prices_path.stem + "_supplement.csv")


def _with_supplement(cfg: Config, prices: pd.DataFrame, source: PriceSource) -> pd.DataFrame:
    """Add series the config asks for but the cached snapshot lacks, without touching the snapshot."""
    missing = [t for t in cfg.download_list if t not in prices.columns]
    if not missing:
        return prices
    path = _supplement_path(cfg)
    have = _read(path) if path.exists() else pd.DataFrame(index=pd.DatetimeIndex([], name="Date"))
    need = [t for t in missing if t not in have.columns]
    if need:
        new = source.fetch(need, str(prices.index.min().date()), str(prices.index.max().date()))
        empty = [t for t in need if new[t].notna().sum() == 0]
        if empty:
            raise RuntimeError(f"No data returned for: {empty}")
        have = _save(cfg, have.join(new, how="outer") if len(have.columns) else new, path, source, key="supplement")
    return prices.join(have[missing], how="left")


def fetch_robustness(cfg: Config, refresh: bool = False, yahoo: PriceSource | None = None,
                     fred: PriceSource | None = None) -> dict[str, pd.DataFrame]:
    """Inputs of the oil-series robustness check: FRED Brent spot, and Yahoo prices from an earlier start."""
    rb = cfg.study.robustness
    if rb is None:
        raise ValueError("no robustness section in study.yaml")
    yahoo, fred = yahoo or YahooSource(), fred or FredSource()
    fred_path, long_path = cfg.raw_dir / "fred_brent.csv", cfg.raw_dir / "prices_long.csv"
    long_start = rb.long_start.isoformat()
    if refresh or not fred_path.exists():
        spot = fred.fetch([rb.fred_brent], (rb.long_start - timedelta(days=30)).isoformat(), cfg.end)
        _save(cfg, spot, fred_path, fred, key="robustness/fred_brent")
    if refresh or not long_path.exists():
        _save(cfg, yahoo.fetch(cfg.download_list, long_start, cfg.end), long_path, yahoo, key="robustness/prices_long")
    return {"fred": _read(fred_path), "long": _read(long_path)}
