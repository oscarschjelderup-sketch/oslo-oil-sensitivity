"""Step 2 - two-factor oil betas with confidence intervals.

    r_i = a + b_mkt * MARKET + b_oil * OIL + e

Two oil betas are reported because they answer different questions:

* partial - MARKET enters as is. "Does this stock carry oil exposure beyond what the
  Oslo index already has?" Oslo Børs is itself oil-heavy, so part of every stock's oil
  exposure hides inside b_mkt and the partial beta understates the full effect.
* total   - MARKET is first stripped of its own oil component (the residual of MARKET on
  OIL). "If Brent moves 10%, what happens to this stock, through every channel?"
  Because that residual is orthogonal to OIL in-sample, the point estimate equals the
  one-factor oil beta; keeping the market residual in the regression only soaks up
  noise and tightens the interval.  Identity:  total = partial + b_mkt * gamma,
  where gamma is the market's own oil beta.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import MARKET, OIL
from ..config import Config
from ..stats import benjamini_hochberg, ols, orthogonalise


def oil_betas(r: np.ndarray, m: np.ndarray, o: np.ndarray, hac_lags="auto") -> dict:
    """Partial and total oil beta of one return series. Inputs are aligned arrays (NaNs allowed)."""
    ok = np.isfinite(r) & np.isfinite(m) & np.isfinite(o)
    r, m, o = r[ok], m[ok], o[ok]
    partial = ols(r, np.column_stack([m, o]), ["market", "oil"], hac_lags)
    m_perp, _, gamma = orthogonalise(m, o)
    total = ols(r, np.column_stack([m_perp, o]), ["market_perp", "oil"], hac_lags)
    oil_only = ols(r, o[:, None], ["oil"], hac_lags)
    p_lo, p_hi = partial.ci("oil")
    t_lo, t_hi = total.ci("oil")
    return {
        "nobs": total.nobs,
        "beta_mkt": partial.coef("market"),
        "beta_oil_partial": partial.coef("oil"),
        "partial_se": partial.stderr("oil"),
        "partial_lo": p_lo, "partial_hi": p_hi,
        "partial_p": partial.pvalue("oil"),
        "beta_oil_total": total.coef("oil"),
        "total_se": total.stderr("oil"),
        "total_lo": t_lo, "total_hi": t_hi,
        "total_p": total.pvalue("oil"),
        "market_oil_beta": gamma,
        "r2": total.r2,
        "r2_oil_only": oil_only.r2,
        "resid_vol": float(total.resid.std(ddof=3)),
        "non_oil_vol": float(oil_only.resid.std(ddof=2)),   # everything oil does not explain
    }


def market_oil_beta(m: np.ndarray, o: np.ndarray, hac_lags="auto") -> dict:
    """The index's own oil beta (one factor). Partial beta is undefined for the market itself."""
    res = ols(m, o[:, None], ["oil"], hac_lags)
    lo, hi = res.ci("oil")
    nan = float("nan")
    return {
        "nobs": res.nobs, "beta_mkt": 1.0,
        "beta_oil_partial": nan, "partial_se": nan, "partial_lo": nan, "partial_hi": nan, "partial_p": nan,
        "beta_oil_total": res.coef("oil"), "total_se": res.stderr("oil"),
        "total_lo": lo, "total_hi": hi, "total_p": res.pvalue("oil"),
        "market_oil_beta": res.coef("oil"), "r2": res.r2, "r2_oil_only": res.r2,
        "resid_vol": float(res.resid.std(ddof=2)),
        "non_oil_vol": float(res.resid.std(ddof=2)),
    }


def units_frame(returns: pd.DataFrame, sectors: pd.DataFrame, cfg: Config) -> tuple[pd.DataFrame, pd.DataFrame]:
    """All series we estimate betas for (market, sector portfolios, stocks) + a lookup table."""
    frame = pd.concat([returns[[MARKET]], sectors, returns[cfg.tickers]], axis=1)
    meta = pd.DataFrame(
        [{"unit": MARKET, "name": cfg.market.name, "kind": "market", "sector": ""}]
        + [{"unit": s, "name": s, "kind": "sector", "sector": s} for s in sectors.columns]
        + [{"unit": t, "name": cfg.names[t], "kind": "stock", "sector": cfg.sector_of[t]} for t in cfg.tickers]
    ).set_index("unit")
    return frame, meta


def beta_table(frame: pd.DataFrame, meta: pd.DataFrame, factors: pd.DataFrame,
               min_obs: int, hac_lags="auto") -> pd.DataFrame:
    """Full-sample (or any slice you pass in) oil betas for every unit."""
    m, o = factors[MARKET].to_numpy(), factors[OIL].to_numpy()
    rows = []
    for unit in frame.columns:
        r = frame[unit].to_numpy()
        if np.isfinite(r).sum() < min_obs:
            continue
        est = market_oil_beta(m, o, hac_lags) if unit == MARKET else oil_betas(r, m, o, hac_lags)
        first = frame[unit].first_valid_index()
        rows.append({"unit": unit, **meta.loc[unit].to_dict(), "from": first.date(), **est})
    return add_q_values(pd.DataFrame(rows).set_index("unit"), {"partial_p": "partial_q", "total_p": "total_q"})


def add_q_values(table: pd.DataFrame, columns: dict[str, str]) -> pd.DataFrame:
    """Benjamini-Hochberg q-values next to each p-value. The family of tests is the `kind`:
    the 63 stocks are corrected together, the 10 sectors together."""
    for p_col, q_col in columns.items():
        table[q_col] = table.groupby("kind")[p_col].transform(lambda p: benjamini_hochberg(p.to_numpy()))
    return table


def rolling_betas(frame: pd.DataFrame, factors: pd.DataFrame, window: int, min_obs: int,
                  hac_lags="auto") -> pd.DataFrame:
    """Rolling-window oil betas. Long format: one row per (unit, window end date)."""
    m_all, o_all = factors[MARKET].to_numpy(), factors[OIL].to_numpy()
    keep = ["beta_mkt", "beta_oil_partial", "partial_lo", "partial_hi",
            "beta_oil_total", "total_lo", "total_hi", "nobs"]
    rows = []
    for unit in frame.columns:
        r_all = frame[unit].to_numpy()
        for end in range(window, len(frame) + 1):
            sl = slice(end - window, end)
            r, m, o = r_all[sl], m_all[sl], o_all[sl]
            if (np.isfinite(r) & np.isfinite(m) & np.isfinite(o)).sum() < min_obs:
                continue
            est = market_oil_beta(m, o, hac_lags) if unit == MARKET else oil_betas(r, m, o, hac_lags)
            rows.append({"unit": unit, "date": frame.index[end - 1], **{k: est[k] for k in keep}})
    return pd.DataFrame(rows)
