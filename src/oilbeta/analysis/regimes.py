"""Step 5 - does the oil beta depend on the regime?

Two splits, both defined without look-ahead:

* direction  - oil up-weeks versus down-weeks (is the downside beta larger?)
* volatility - weeks where trailing oil volatility (known at the start of the week) is
               above versus below its own expanding median.

Each is one regression with the oil return split in two, and a t-test that the two
betas are equal (Newey-West covariance). The market factor is stripped of the *same*
split oil terms, so the betas keep the "total" interpretation of step 2.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import MARKET, OIL
from ..stats import ols


def high_vol_flag(oil: pd.Series, vol_window: int, burn_in: int = 52) -> pd.Series:
    """True when trailing oil vol, known before the week starts, is above its expanding median."""
    vol = oil.rolling(vol_window).std().shift(1)
    median = vol.expanding(min_periods=burn_in).median().shift(1)
    flag = (vol > median).astype(float)
    flag[vol.isna() | median.isna()] = np.nan
    return flag


def split_beta(r: np.ndarray, m: np.ndarray | None, o_a: np.ndarray, o_b: np.ndarray,
               labels: tuple[str, str], hac_lags="auto") -> dict:
    """Two oil betas in one regression. Pass m=None for the market's own beta (no market control)."""
    ok = np.isfinite(r) & np.isfinite(o_a) & np.isfinite(o_b)
    if m is not None:
        ok &= np.isfinite(m)
    r, oil_terms = r[ok], np.column_stack([o_a[ok], o_b[ok]])
    if m is None:
        res = ols(r, oil_terms, list(labels), hac_lags)
    else:
        m_perp = ols(m[ok], oil_terms, list(labels), hac_lags=0).resid
        res = ols(r, np.column_stack([m_perp, oil_terms]), ["market_perp", *labels], hac_lags)
    diff, t, p = res.test_equal(labels[1], labels[0])
    a, b = labels
    return {"nobs": res.nobs, f"n_{a}": int((oil_terms[:, 0] != 0).sum()), f"n_{b}": int((oil_terms[:, 1] != 0).sum()),
            f"beta_{a}": res.coef(a), f"se_{a}": res.stderr(a),
            f"beta_{b}": res.coef(b), f"se_{b}": res.stderr(b),
            "difference": diff, "t_diff": t, "p_diff": p}


def regime_tables(frame: pd.DataFrame, meta: pd.DataFrame, factors: pd.DataFrame,
                  vol_window: int, min_obs: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    m, o = factors[MARKET].to_numpy(), factors[OIL].to_numpy()
    high = high_vol_flag(factors[OIL], vol_window).to_numpy()
    o_up, o_down = np.where(o > 0, o, 0.0), np.where(o < 0, o, 0.0)
    o_up[~np.isfinite(o)] = o_down[~np.isfinite(o)] = np.nan
    o_calm, o_turb = o * (1 - high), o * high
    direction, volatility = [], []
    for unit in frame.columns:
        r = frame[unit].to_numpy()
        if np.isfinite(r).sum() < min_obs:
            continue
        control = None if unit == MARKET else m
        info = meta.loc[unit].to_dict()
        direction.append({"unit": unit, **info, **split_beta(r, control, o_down, o_up, ("down", "up"))})
        volatility.append({"unit": unit, **info, **split_beta(r, control, o_calm, o_turb, ("calm", "turbulent"))})
    return pd.DataFrame(direction).set_index("unit"), pd.DataFrame(volatility).set_index("unit")
