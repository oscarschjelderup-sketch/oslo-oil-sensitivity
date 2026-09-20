"""Step 4 - from betas to a scenario table, and an honest out-of-sample check.

The scenario table answers "if Brent moves X%, what is the expected move in each stock and
sector?" using total oil betas from the most recent `window` weeks. Two kinds of uncertainty
are shown and must not be confused:

* the confidence interval on the *expected* move (we do not know beta exactly), and
* `p_same_sign`: how often the stock would actually move in the predicted direction in a
  week with that oil move, given everything else that drives it. For most non-energy
  stocks this is barely above a coin flip, which is the point.

The out-of-sample test asks whether betas estimated only on past data rank stocks correctly
in the *next* oil shock (impact window), and whether the same ranking predicts the drift
afterwards. The first is a test of stable sensitivity; the second of genuine predictability.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from . import OIL
from .betas import beta_table


def scenario_table(frame: pd.DataFrame, meta: pd.DataFrame, factors: pd.DataFrame,
                   window: int, shocks: list[float], min_obs: int, sign_shock: float = 0.10) -> pd.DataFrame:
    recent = beta_table(frame.iloc[-window:], meta, factors.iloc[-window:], min_obs)
    out = recent[["name", "kind", "sector", "nobs", "beta_oil_total", "total_lo", "total_hi",
                  "r2_oil_only", "non_oil_vol"]].copy()
    for s in shocks:
        x = np.log1p(s)
        tag = f"{s:+.0%}"
        out[f"exp_{tag}"] = np.expm1(out["beta_oil_total"] * x)
        bounds = np.expm1(np.column_stack([out["total_lo"] * x, out["total_hi"] * x]))
        out[f"lo_{tag}"], out[f"hi_{tag}"] = bounds.min(axis=1), bounds.max(axis=1)
    ref = np.log1p(sign_shock)
    out["p_same_sign"] = stats.norm.cdf((out["beta_oil_total"] * ref).abs() / out["non_oil_vol"])
    out["p_same_sign_shock"] = sign_shock
    out["rank"] = out.groupby("kind")["beta_oil_total"].rank(ascending=False).astype(int)
    return out.sort_values(["kind", "rank"])


def _past_betas(frame: pd.DataFrame, oil: pd.Series, before: pd.Timestamp,
                window: int, min_history: int) -> pd.Series:
    """One-factor (= total) oil betas using only weeks that ended before `before`."""
    past = frame.loc[frame.index < before].iloc[-window:]
    o = oil.loc[past.index]
    betas = {}
    for unit in past.columns:
        r = past[unit]
        ok = r.notna() & o.notna()
        if ok.sum() >= min_history:
            betas[unit] = np.cov(r[ok], o[ok])[0, 1] / o[ok].var()
    return pd.Series(betas, dtype=float)


def out_of_sample(frame_weekly: pd.DataFrame, factors_weekly: pd.DataFrame, cars: pd.DataFrame,
                  events: pd.DataFrame, stocks: list[str], window: int, min_history: int,
                  min_stocks: int = 15) -> pd.DataFrame:
    """Per event: does the past-beta ranking match the realised cross-section of CARs?"""
    impact = cars[cars["window"] == "impact"].pivot(index="event_id", columns="unit", values="car_total")
    drift = cars[cars["window"] == "drift"].pivot(index="event_id", columns="unit", values="car_total")
    oil_move = cars[cars["window"] == "impact"].groupby("event_id")["oil_move"].first()
    rows = []
    for event_id, ev in events.iterrows():
        betas = _past_betas(frame_weekly[stocks], factors_weekly[OIL], ev["date"], window, min_history)
        if len(betas) < min_stocks:
            continue
        predicted = betas * oil_move.loc[event_id]
        row = {"event_id": event_id, "date": ev["date"], "direction": ev["direction"],
               "oil_move": oil_move.loc[event_id], "n_stocks": 0}
        for label, realised in (("impact", impact), ("drift", drift)):
            both = pd.concat([predicted, realised.loc[event_id]], axis=1, keys=["pred", "real"]).dropna()
            if len(both) < min_stocks:
                continue
            row["n_stocks"] = len(both)
            row[f"spearman_{label}"] = stats.spearmanr(both["pred"], both["real"])[0]
            ranked = both.sort_values("pred")
            k = len(ranked) // 3
            row[f"spread_{label}"] = ranked["real"].iloc[-k:].mean() - ranked["real"].iloc[:k].mean()
        rows.append(row)
    return pd.DataFrame(rows).set_index("event_id")


def summarise_oos(oos: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for col in ["spearman_impact", "spread_impact", "spearman_drift", "spread_drift"]:
        x = oos[col].dropna()
        t, p = stats.ttest_1samp(x, 0.0)
        rows.append({"measure": col, "n_events": len(x), "mean": x.mean(), "median": x.median(),
                     "t": float(t), "p": float(p), "share_positive": float((x > 0).mean())})
    return pd.DataFrame(rows).set_index("measure")
