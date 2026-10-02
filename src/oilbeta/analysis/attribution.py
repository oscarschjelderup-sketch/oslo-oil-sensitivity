"""What moved a stock on a given day: oil, the rest of the market, or its own news.

The oil betas answer "what does oil do to this stock?". They were never a forecast of the stock's
day: for the typical stock oil explains about one percent of weekly variance, the index's non-oil
moves another fourteen, and the rest is the company's own news. This module supplies what a reader
needs to see that for themselves.

* `unit_inputs`     per unit, over the scenario window: the two-factor betas, and how wide the
                    unit's own-news distribution is over one trading day (quantiles of the daily
                    residual, computed with those weekly betas).
* `signal_by_size`  how well *past* oil betas rank stocks on a day, by the size of the Brent move.
                    The ranking is close to useless on a quiet oil day and strong on a shock day.

With x the Brent move and m the index move (log returns), a day splits exactly:

    r  =  beta_total * x  +  beta_mkt * (m - gamma * x)  +  own
          oil                the market beyond oil          own news

gamma is the index's own oil beta, so the first term is everything oil did (through the index too)
and the second is what the rest of the market did. Nothing here forecasts: x and m are the moves
that happened. The split says how much of a move each one accounts for.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import MARKET, OIL
from .betas import beta_table

EDGES = (0.5, 1.0, 1.5, 2.5)          # |Brent move| in trailing standard deviations; the last is the shock rule


def unit_inputs(frame_w: pd.DataFrame, frame_d: pd.DataFrame, meta: pd.DataFrame, factors_w: pd.DataFrame,
                factors_d: pd.DataFrame, window: int, min_obs: int, coverage: float = 0.80) -> pd.DataFrame:
    """Betas for the attribution and the one-day range of each unit's own news, over the last `window` weeks."""
    recent_w = frame_w.iloc[-window:]
    recent = beta_table(recent_w, meta, factors_w.iloc[-window:], min_obs)
    first_day = recent_w.index[0] - pd.Timedelta(days=7)                # the first week's days come after this
    days = (frame_d.index > first_day) & (frame_d.index <= recent_w.index[-1])
    m, o = factors_d.loc[days, MARKET].to_numpy(), factors_d.loc[days, OIL].to_numpy()
    tail = (1 - coverage) / 2
    rows = []
    for unit, b in recent.iterrows():
        r = frame_d.loc[days, unit].to_numpy()
        own = r - b["beta_oil_total"] * o if unit == MARKET else r - b["beta_mkt"] * m - b["beta_oil_partial"] * o
        own = own[np.isfinite(own)]
        lo, hi = (np.quantile(own, [tail, 1 - tail]) if len(own) else (np.nan, np.nan))
        rows.append({"unit": unit, "name": b["name"], "kind": b["kind"], "sector": b["sector"],
                     "beta_oil_total": b["beta_oil_total"], "beta_mkt": b["beta_mkt"],
                     "beta_oil_partial": b["beta_oil_partial"], "market_oil_beta": b["market_oil_beta"],
                     "r2_oil": b["r2_oil_only"], "r2_two": b["r2"],
                     "own_lo": float(lo), "own_hi": float(hi), "own_sd": float(own.std(ddof=1)) if len(own) > 1 else np.nan,
                     "nobs_days": int(len(own)), "coverage": coverage})
    return pd.DataFrame(rows).set_index("unit")


def past_betas(stocks_w: pd.DataFrame, oil_w: pd.Series, window: int, min_history: int) -> pd.DataFrame:
    """One-factor (total) oil betas over the trailing `window` weeks, re-labelled to the week they can be used in:
    the row for a Friday holds betas estimated on weeks that ended before that week began."""
    o = pd.concat({c: oil_w.where(stocks_w[c].notna()) for c in stocks_w.columns}, axis=1)
    r = stocks_w.where(oil_w.notna(), axis=0)
    roll = {"window": window, "min_periods": min_history}
    mean_o, mean_r = o.rolling(**roll).mean(), r.rolling(**roll).mean()
    cov = (o * r).rolling(**roll).mean() - mean_o * mean_r
    var = (o * o).rolling(**roll).mean() - mean_o ** 2
    beta = cov / var
    beta.index = beta.index + pd.Timedelta(weeks=1)
    return beta


def daily_rank_correlation(stocks_w: pd.DataFrame, stocks_d: pd.DataFrame, oil_w: pd.Series, oil_d: pd.Series,
                           window: int, min_history: int, vol_window: int, min_stocks: int = 15) -> pd.DataFrame:
    """One row per trading day: the size of the Brent move in trailing standard deviations (volatility up to the
    day before, as in the event rule) and the rank correlation, across stocks, between betas known before the
    week began and that day's returns. The correlation is signed so that positive means "ranked as oil implied"."""
    week = stocks_d.index.to_period("W-FRI").end_time.normalize()
    beta = past_betas(stocks_w, oil_w, window, min_history).reindex(week)
    beta.index = stocks_d.index
    x, b = stocks_d.where(beta.notna()), beta.where(stocks_d.notna())
    rho = x.rank(axis=1).corrwith(b.rank(axis=1), axis=1)
    z = oil_d / oil_d.rolling(vol_window).std().shift(1)
    out = pd.DataFrame({"z": z.reindex(stocks_d.index), "oil": oil_d.reindex(stocks_d.index),
                        "rank_corr": rho * np.sign(oil_d.reindex(stocks_d.index)), "n_stocks": x.notna().sum(axis=1)})
    return out[(out["n_stocks"] >= min_stocks) & out["z"].notna() & out["rank_corr"].notna() & (out["oil"] != 0)]


def bucket_label(lo: float, hi: float | None) -> str:
    """Plain-ASCII label (the unit, trailing standard deviations, is added where the table is shown)."""
    return f"under {hi:g}" if lo == 0 else f"{lo:g} or more" if hi is None else f"{lo:g} to {hi:g}"


def signal_by_size(days: pd.DataFrame, edges: tuple[float, ...] = EDGES) -> pd.DataFrame:
    """Average the daily rank correlations by the size of the Brent move."""
    bounds = [0.0, *edges, None]
    rows = []
    for lo, hi in zip(bounds[:-1], bounds[1:]):
        size = days["z"].abs()
        g = days[(size >= lo) & (size < hi if hi is not None else True)]
        rows.append({"size_sd": bucket_label(lo, hi), "lo": lo, "hi": hi, "n_days": int(len(g)),
                     "mean_abs_oil": float(np.expm1(g["oil"].abs()).mean()) if len(g) else np.nan,
                     "mean_rank_corr": float(g["rank_corr"].mean()) if len(g) else np.nan,
                     "share_positive": float((g["rank_corr"] > 0).mean()) if len(g) else np.nan})
    return pd.DataFrame(rows).set_index("size_sd")


def summary(inputs: pd.DataFrame, signal: pd.DataFrame, rank_days: pd.DataFrame, oil_d: pd.Series,
            vol_window: int) -> dict:
    """The numbers the page and the report quote."""
    stocks = inputs[inputs["kind"] == "stock"]
    return {
        "coverage": float(inputs["coverage"].iloc[0]),
        "gamma": float(inputs.loc[MARKET, "beta_oil_total"]),
        "oil_daily_vol": float(oil_d.rolling(vol_window).std().iloc[-1]),        # the yardstick for today's move
        "median_r2_oil": float(stocks["r2_oil"].median()),
        "median_r2_two": float(stocks["r2_two"].median()),
        "median_own_lo": float(stocks["own_lo"].median()), "median_own_hi": float(stocks["own_hi"].median()),
        "signal_days": int(len(rank_days)),
        "signal_since": str(rank_days.index.min().date()) if len(rank_days) else None,
        "signal": [{"label": label, "lo": float(r["lo"]), "hi": None if r["hi"] is None or pd.isna(r["hi"]) else float(r["hi"]),
                    "n_days": int(r["n_days"]), "mean_abs_oil": float(r["mean_abs_oil"]),
                    "mean_rank_corr": float(r["mean_rank_corr"]), "share_positive": float(r["share_positive"])}
                   for label, r in signal.iterrows()],
    }
