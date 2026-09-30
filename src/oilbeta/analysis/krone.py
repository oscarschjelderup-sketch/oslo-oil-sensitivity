"""Is it the krone? How much of each oil beta runs through USD/NOK.

Brent is priced in dollars and Oslo Børs in kroner, and the krone is itself an oil currency: when
Brent rises the krone tends to strengthen. Part of a stock's reaction to oil could therefore be the
currency rather than the commodity. Adding USD/NOK as a third factor splits the total oil beta
exactly (same weeks, OLS with a constant):

    r = a + d * OIL + b_mkt * MARKET + b_nok * USDNOK + e

    total  =  d  +  b_mkt * g_mkt  +  b_nok * g_nok
              direct   through the index   through the krone

g_mkt and g_nok are the index's and the krone's own oil betas over the same weeks. For the index
itself the middle term does not exist. USD/NOK is quoted in kroner per dollar, so a positive b_nok
means the stock gains when the krone weakens; g_nok is negative because oil rises strengthen it.

The index's own krone channel reaches every stock through its index beta, so "through the krone"
for a stock or sector is the exposure *beyond* what the index already carries - the same convention
as the partial oil beta.

The headline model stays two-factor (docs/decisions/0010): this table measures the currency channel
and how far the partial betas move once it is held fixed. It does not replace them.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import MARKET, OIL
from ..stats import ols
from .betas import add_q_values

KRONE = "USDNOK"          # weekly column name of the configured `usdnok` context series


def _slope(y: np.ndarray, x: np.ndarray) -> float:
    """OLS slope of y on x with a constant: the one-factor beta."""
    xc = x - x.mean()
    return float(xc @ (y - y.mean()) / (xc @ xc))


def decompose(r: np.ndarray, m: np.ndarray, o: np.ndarray, f: np.ndarray, hac_lags="auto",
              is_market: bool = False) -> dict:
    """Split one series' total oil beta into direct, through-the-index and through-the-krone parts.
    Inputs are aligned arrays (NaNs allowed); every term is estimated on the weeks where all four exist."""
    ok = np.isfinite(r) & np.isfinite(m) & np.isfinite(o) & np.isfinite(f)
    r, m, o, f = r[ok], m[ok], o[ok], f[ok]
    g_mkt, g_nok = _slope(m, o), _slope(f, o)
    if is_market:
        three = ols(r, np.column_stack([o, f]), ["oil", "krone"], hac_lags)
        b_mkt, via_market, partial = float("nan"), float("nan"), float("nan")
    else:
        three = ols(r, np.column_stack([o, m, f]), ["oil", "market", "krone"], hac_lags)
        b_mkt = three.coef("market")
        via_market = b_mkt * g_mkt
        partial = ols(r, np.column_stack([m, o]), ["market", "oil"], hac_lags).coef("oil")
    d_lo, d_hi = three.ci("oil")
    k_lo, k_hi = three.ci("krone")
    return {
        "nobs": three.nobs,
        "beta_oil_total": _slope(r, o),
        "direct": three.coef("oil"), "direct_lo": d_lo, "direct_hi": d_hi, "direct_p": three.pvalue("oil"),
        "via_market": via_market,
        "via_krone": three.coef("krone") * g_nok,
        "beta_mkt": b_mkt,
        "beta_krone": three.coef("krone"), "krone_lo": k_lo, "krone_hi": k_hi, "krone_p": three.pvalue("krone"),
        "partial_two_factor": partial,           # the headline partial beta, re-estimated on the same weeks
        "market_oil_beta": g_mkt, "krone_oil_beta": g_nok,
    }


def krone_table(frame: pd.DataFrame, meta: pd.DataFrame, factors: pd.DataFrame, min_obs: int,
                hac_lags="auto") -> pd.DataFrame:
    """The decomposition for every unit with enough history. `factors` holds MARKET, OIL and KRONE."""
    m, o, f = (factors[c].to_numpy() for c in (MARKET, OIL, KRONE))
    rows = []
    for unit in frame.columns:
        r = frame[unit].to_numpy()
        if np.isfinite(r).sum() < min_obs:
            continue
        est = decompose(r, m, o, f, hac_lags, is_market=unit == MARKET)
        rows.append({"unit": unit, **meta.loc[unit].to_dict(), **est})
    table = pd.DataFrame(rows).set_index("unit")
    table["identity_gap"] = table["beta_oil_total"] - table[["direct", "via_market", "via_krone"]].fillna(0.0).sum(axis=1)
    return add_q_values(table, {"direct_p": "direct_q", "krone_p": "krone_q"})


def rolling_krone_oil_beta(factors: pd.DataFrame, window: int, min_obs: int, hac_lags="auto") -> pd.DataFrame:
    """The krone's own oil beta (USD/NOK on Brent) in rolling windows: is the channel opening or closing?"""
    o_all, f_all = factors[OIL].to_numpy(), factors[KRONE].to_numpy()
    rows = []
    for end in range(window, len(factors) + 1):
        sl = slice(end - window, end)
        o, f = o_all[sl], f_all[sl]
        if (np.isfinite(o) & np.isfinite(f)).sum() < min_obs:
            continue
        res = ols(f, o[:, None], ["oil"], hac_lags)
        lo, hi = res.ci("oil")
        rows.append({"date": factors.index[end - 1], "krone_oil_beta": res.coef("oil"), "lo": lo, "hi": hi, "nobs": res.nobs})
    return pd.DataFrame(rows)


def _largest(part: pd.DataFrame) -> dict | None:
    """The unit whose through-the-krone part is largest in absolute value."""
    if part.empty:
        return None
    unit = part["via_krone"].abs().idxmax()
    row = part.loc[unit]
    return {"unit": unit, "name": row["name"], "via_krone": float(row["via_krone"]), "beta_krone": float(row["beta_krone"])}


def summary(table: pd.DataFrame, factors: pd.DataFrame, recent_weeks: int, hac_lags="auto") -> dict:
    """The handful of numbers the report quotes, including the index's split over the recent window."""
    stocks, sectors = table[table["kind"] == "stock"], table[table["kind"] == "sector"]
    ok = factors[[OIL, KRONE]].dropna()
    idx = table.loc[MARKET]
    recent = factors.iloc[-recent_weeks:]
    now = decompose(*(recent[c].to_numpy() for c in (MARKET, MARKET, OIL, KRONE)), hac_lags, is_market=True)
    sig = stocks[stocks["krone_q"] < 0.05].sort_values("beta_krone")
    shift = (sectors["direct"] - sectors["partial_two_factor"]).abs()
    return {
        "weeks": int(len(ok)),
        "weeks_without_krone": int((factors[OIL].notna() & factors[KRONE].isna()).sum()),
        "krone_oil_beta": _slope(ok[KRONE].to_numpy(), ok[OIL].to_numpy()),
        "krone_oil_corr": float(ok[KRONE].corr(ok[OIL])),
        "index_total": float(idx["beta_oil_total"]), "index_direct": float(idx["direct"]),
        "index_via_krone": float(idx["via_krone"]), "index_beta_krone": float(idx["beta_krone"]),
        "index_krone_p": float(idx["krone_p"]),
        "recent_weeks": recent_weeks, "recent_index_total": now["beta_oil_total"],
        "recent_index_via_krone": now["via_krone"], "recent_krone_oil_beta": now["krone_oil_beta"],
        "max_sector": _largest(sectors), "max_stock": _largest(stocks),
        "max_sector_partial_shift": float(shift.max()) if len(shift) else float("nan"),
        "n_direct_positive": int(((stocks["direct_q"] < 0.05) & (stocks["direct"] > 0)).sum()),
        "n_krone_significant": int(len(sig)),
        "krone_significant": [{"unit": u, "name": r["name"], "beta_krone": float(r["beta_krone"]),
                               "via_krone": float(r["via_krone"])} for u, r in sig.iterrows()],
        "max_identity_gap": float(table["identity_gap"].abs().max()),
    }
