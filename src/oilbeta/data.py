"""Step 1 - the data foundation.

Three rules, each fixing a specific way oil-vs-equity studies go wrong:

1. *Align first, then compute returns.* Brent trades on days Oslo is closed (and vice
   versa). Returns are taken on the common calendar, so a return always covers the same
   span of time for the stock, the index and oil.
2. *No double counting.* Sector series are equal-weighted portfolios of their members.
   No ETF or index is ever averaged together with its own constituents.
3. *Fixed snapshot.* The sample end date is pinned in the config and the downloaded
   snapshot is described in data/manifest.json, so results can be reproduced and audited.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd

from . import MARKET, OIL
from .config import Config


# --------------------------------------------------------------------------
# Download / cache
# --------------------------------------------------------------------------
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
    for factor in (cfg.oil_ticker, cfg.market["late_ticker"]):     # a half-empty download must not pass as fresh
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


# --------------------------------------------------------------------------
# Market index splice
# --------------------------------------------------------------------------
def splice_market(prices: pd.DataFrame, cfg: Config) -> pd.Series:
    """Chain OSEFX returns (before the splice date) into OSEBX returns (after)."""
    m = cfg.market
    splice = pd.Timestamp(m["splice_date"])
    early = np.log(prices[m["early_ticker"]].dropna()).diff()
    late = np.log(prices[m["late_ticker"]].dropna()).diff()
    ret = pd.concat([early[early.index <= splice], late[late.index > splice]]).dropna().sort_index()
    level = 100.0 * np.exp(ret.cumsum())
    level.name = MARKET
    return level


def splice_diagnostics(prices: pd.DataFrame, cfg: Config) -> dict:
    m = cfg.market
    both = prices[[m["early_ticker"], m["late_ticker"]]].dropna()
    r = np.log(both).diff().dropna()
    diff = r.iloc[:, 0] - r.iloc[:, 1]
    return {
        "overlap_start": str(both.index.min().date()),
        "overlap_end": str(both.index.max().date()),
        "overlap_days": int(len(r)),
        "return_correlation": round(float(r.corr().iloc[0, 1]), 4),
        "tracking_error_annualised": round(float(diff.std() * np.sqrt(252)), 4),
    }


# --------------------------------------------------------------------------
# Aligned panels and returns
# --------------------------------------------------------------------------
def build_panel(prices: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Price panel on the common Oslo/Brent calendar: MARKET, OIL, context series, stocks."""
    market = splice_market(prices, cfg)
    panel = pd.concat(
        [market, prices[cfg.oil_ticker].rename(OIL),
         prices[list(cfg.context.values())].rename(columns={v: k.upper() for k, v in cfg.context.items()}),
         prices[cfg.tickers]],
        axis=1, sort=True,
    )
    for ticker, rule in _exceptions(cfg).get("history_start", {}).items():
        panel.loc[panel.index < pd.Timestamp(rule["date"]), ticker] = np.nan
    common = panel[MARKET].notna() & panel[OIL].notna()
    return panel.loc[common]


def _exceptions(cfg: Config) -> dict:
    return cfg.raw.get("data_exceptions") or {}


def daily_returns(panel: pd.DataFrame, cfg: Config | None = None) -> pd.DataFrame:
    """Log returns on the common calendar (computed after alignment, never before)."""
    ret = np.log(panel).diff().iloc[1:]
    for ex in (_exceptions(cfg).get("drop_returns", []) if cfg else []):
        ret.loc[ret.index == pd.Timestamp(ex["date"]), ex["ticker"]] = np.nan
    return ret


def weekly_returns(panel: pd.DataFrame, cfg: Config | None = None) -> pd.DataFrame:
    """Friday-to-Friday log returns. A week with no price gives NaN rather than a stale fill."""
    weekly = panel.resample("W-FRI").last()
    if cfg is not None and len(weekly) and weekly.index[-1] > pd.Timestamp(cfg.end):
        weekly = weekly.iloc[:-1]           # the current week is not over yet (live mode)
    ret = np.log(weekly).diff().iloc[1:]
    for ex in (_exceptions(cfg).get("drop_returns", []) if cfg else []):
        week = ret.index[ret.index >= pd.Timestamp(ex["date"])]
        if len(week):
            ret.loc[week[0], ex["ticker"]] = np.nan
    return ret


def sector_returns(returns: pd.DataFrame, cfg: Config, min_members: int = 2) -> pd.DataFrame:
    """Equal-weighted sector portfolios built from constituents only.

    Averaging is done in simple-return space (a portfolio return is the mean of simple
    returns, not of log returns) and converted back to logs.
    """
    out = {}
    for sector, members in cfg.universe.items():
        simple = np.expm1(returns[list(members)])
        port = simple.mean(axis=1, skipna=True)
        port[simple.notna().sum(axis=1) < min(min_members, len(members))] = np.nan
        out[sector] = np.log1p(port)
    return pd.DataFrame(out)


# --------------------------------------------------------------------------
# Validation report
# --------------------------------------------------------------------------
def validate(panel: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """One row per series: coverage, staleness and suspicious prints. Flags, never silent fixes."""
    v = cfg.section("validation")
    daily = daily_returns(panel, cfg)      # after the documented exceptions, so a flag
    weekly = weekly_returns(panel, cfg)    # here means "still in the sample"
    ex = _exceptions(cfg)
    n_dropped = pd.Series([e["ticker"] for e in ex.get("drop_returns", [])]).value_counts()
    min_weeks = cfg.section("betas")["min_history"]
    rows = []
    for col in panel.columns:
        p, r = panel[col].dropna(), daily[col].dropna()
        live = daily[col].loc[p.index.min():p.index.max()]
        zero_share = float((r == 0).mean()) if len(r) else np.nan
        flags = []
        if weekly[col].notna().sum() < min_weeks:
            flags.append("short history")
        if zero_share > v["max_zero_return_share"]:
            flags.append("stale prices")
        if (r.abs() > v["max_abs_daily_return"]).any():
            flags.append("extreme print")
        rows.append({
            "series": col,
            "name": cfg.names.get(col, col),
            "sector": cfg.sector_of.get(col, "factor"),
            "first": p.index.min().date(),
            "last": p.index.max().date(),
            "daily_obs": len(r),
            "weekly_obs": int(weekly[col].notna().sum()),
            "missing_days_while_listed": int(live.isna().sum()),
            "zero_return_share": round(zero_share, 4),
            "max_abs_daily_return": round(float(r.abs().max()), 4),
            "extreme_days": int((r.abs() > v["max_abs_daily_return"]).sum()),
            "returns_dropped": int(n_dropped.get(col, 0)),
            "history_trimmed": col in ex.get("history_start", {}),
            "flags": "; ".join(flags) or "ok",
        })
    return pd.DataFrame(rows)
