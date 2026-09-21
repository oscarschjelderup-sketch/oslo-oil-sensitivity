"""Robustness - do the results depend on which oil series is used, or on where the sample starts?

The baseline uses the Brent front-month future from Yahoo, which only starts in July 2007: the
sample opens straight into the financial crisis, when oil and equities fell together. Two
alternatives are run through exactly the same code:

* spot, same sample   Brent spot from FRED (U.S. EIA) instead of the future. A different
                      instrument from an independent vendor; if the betas move, the vendor matters.
* spot, long sample   the same spot series with stock prices from 2005, which adds two and a half
                      pre-crisis years. If the early betas were a crisis artefact, this shows it.

Nothing here feeds back into the headline numbers; it only reports how far they move.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import MARKET, OIL
from ..config import Config
from ..data import align
from . import betas

BASELINE, SPOT, SPOT_LONG = "Brent future (baseline)", "Brent spot, same sample", "Brent spot, from 2005"
CRISIS_START = "2008-09-01"


def _with_oil(prices: pd.DataFrame, oil: pd.Series, cfg: Config) -> pd.DataFrame:
    out = prices.copy()
    out[cfg.oil_ticker] = oil.reindex(out.index)
    return out


def _estimate(prices: pd.DataFrame, cfg: Config) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    panel = align.build_panel(prices, cfg)
    weekly = align.weekly_returns(panel, cfg)
    frame, meta = betas.units_frame(weekly, align.sector_returns(weekly, cfg), cfg)
    factors = weekly[[MARKET, OIL]]
    table = betas.beta_table(frame, meta, factors, cfg.betas.min_history, cfg.betas.hac_lags)
    rolling = betas.rolling_betas(frame[[MARKET]], factors, cfg.betas.rolling_window, cfg.betas.rolling_min_obs,
                                  cfg.betas.hac_lags)
    return table, rolling, weekly


def oil_series_check(cfg: Config, prices: pd.DataFrame, fred: pd.DataFrame, prices_long: pd.DataFrame) -> dict:
    """Run the beta step under the three variants. Returns a summary table, the rolling index betas
    and a small dict describing how closely the two oil series agree."""
    spot = fred.iloc[:, 0].dropna()
    variants = {BASELINE: prices, SPOT: _with_oil(prices, spot, cfg), SPOT_LONG: _with_oil(prices_long, spot, cfg)}
    tables, rolling, weekly = {}, [], {}
    for name, frame in variants.items():
        tables[name], roll, weekly[name] = _estimate(frame, cfg)
        rolling.append(roll.assign(variant=name))

    base_stocks = tables[BASELINE].query("kind == 'stock'")["beta_oil_total"]
    sectors = [u for u in tables[BASELINE].index if tables[BASELINE].loc[u, "kind"] == "sector"]
    rows = []
    for name, t in tables.items():
        stocks = t.query("kind == 'stock'")["beta_oil_total"]
        both = pd.concat([base_stocks, stocks], axis=1, keys=["base", "this"]).dropna()
        w = weekly[name]
        rows.append({
            "variant": name, "first_week": w.index.min().date(), "weeks": int(w[OIL].notna().sum()),
            "index_beta": t.loc[MARKET, "beta_oil_total"], "index_lo": t.loc[MARKET, "total_lo"],
            "index_hi": t.loc[MARKET, "total_hi"],
            **{f"beta: {s}": t.loc[s, "beta_oil_total"] for s in sectors if s in t.index},
            "stocks": len(stocks), "rank_corr_with_baseline": both["base"].corr(both["this"], method="spearman"),
            "max_abs_beta_change": float((both["this"] - both["base"]).abs().max()),
        })

    fut, spt = weekly[BASELINE][OIL], weekly[SPOT][OIL]
    agree = pd.concat([fut, spt], axis=1, keys=["future", "spot"]).dropna()
    agreement = {"weeks": int(len(agree)), "weekly_return_correlation": float(agree["future"].corr(agree["spot"])),
                 "spot_vol_over_future_vol": float(agree["spot"].std() / agree["future"].std())}
    all_rolling = pd.concat(rolling, ignore_index=True)
    # two-year windows that end before Lehman contain no financial crisis; the next block is dominated by it
    agreement["pre_crisis"] = window_average(all_rolling, SPOT_LONG, None, CRISIS_START)
    agreement["crisis_era"] = window_average(all_rolling, SPOT_LONG, "2009-01-01", "2014-01-01")
    return {"summary": pd.DataFrame(rows).set_index("variant"), "rolling": all_rolling, "agreement": agreement}


def window_average(rolling: pd.DataFrame, variant: str, first: str | None, last: str | None) -> dict:
    """Mean rolling index beta over the windows that END between `first` and `last` (either may be None)."""
    r = rolling[rolling["variant"] == variant]
    if first:
        r = r[r["date"] >= pd.Timestamp(first)]
    if last:
        r = r[r["date"] < pd.Timestamp(last)]
    if r.empty:
        return {"windows": 0, "mean": float(np.nan), "min": float(np.nan), "max": float(np.nan)}
    b = r["beta_oil_total"]
    return {"windows": int(len(b)), "mean": float(b.mean()), "min": float(b.min()), "max": float(b.max()),
            "first_end": str(r["date"].iloc[0].date()), "last_end": str(r["date"].iloc[-1].date())}
