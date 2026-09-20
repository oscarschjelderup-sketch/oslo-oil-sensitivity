"""From raw prices to returns that can be compared.

* Align first, then compute returns. Brent trades on days Oslo is closed (and vice versa).
  Returns are taken on the common calendar, so a return always covers the same span of time
  for the stock, the index and oil.
* No double counting. Sector series are equal-weighted portfolios of their members; no ETF or
  index is ever averaged together with its own constituents.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import MARKET, OIL
from ..config import Config


def splice_market(prices: pd.DataFrame, cfg: Config) -> pd.Series:
    """Chain OSEFX returns (before the splice date) into OSEBX returns (after)."""
    m = cfg.market
    splice = pd.Timestamp(m.splice_date)
    early = np.log(prices[m.early_ticker].dropna()).diff()
    late = np.log(prices[m.late_ticker].dropna()).diff()
    ret = pd.concat([early[early.index <= splice], late[late.index > splice]]).dropna().sort_index()
    level = 100.0 * np.exp(ret.cumsum())
    level.name = MARKET
    return level


def splice_diagnostics(prices: pd.DataFrame, cfg: Config) -> dict:
    m = cfg.market
    both = prices[[m.early_ticker, m.late_ticker]].dropna()
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
    for ticker, rule in cfg.exceptions.history_start.items():
        panel.loc[panel.index < pd.Timestamp(rule.date), ticker] = np.nan
    common = panel[MARKET].notna() & panel[OIL].notna()
    return panel.loc[common]


def daily_returns(panel: pd.DataFrame, cfg: Config | None = None) -> pd.DataFrame:
    """Log returns on the common calendar (computed after alignment, never before)."""
    ret = np.log(panel).diff().iloc[1:]
    for ex in (cfg.exceptions.drop_returns if cfg else []):
        ret.loc[ret.index == pd.Timestamp(ex.date), ex.ticker] = np.nan
    return ret


def weekly_returns(panel: pd.DataFrame, cfg: Config | None = None) -> pd.DataFrame:
    """Friday-to-Friday log returns. A week with no price gives NaN rather than a stale fill."""
    weekly = panel.resample("W-FRI").last()
    if cfg is not None and len(weekly) and weekly.index[-1] > pd.Timestamp(cfg.end):
        weekly = weekly.iloc[:-1]           # the current week is not over yet (live mode)
    ret = np.log(weekly).diff().iloc[1:]
    for ex in (cfg.exceptions.drop_returns if cfg else []):
        week = ret.index[ret.index >= pd.Timestamp(ex.date)]
        if len(week):
            ret.loc[week[0], ex.ticker] = np.nan
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
