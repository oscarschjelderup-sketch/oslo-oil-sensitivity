"""Step 3 - event study around oil shocks.

* Events are picked by a rule, not by hand: a day where |Brent return| exceeds
  `z_threshold` trailing standard deviations (volatility measured up to the day before,
  so there is no look-ahead). Shocks closer than `min_gap` trading days to an accepted
  event are skipped, which keeps the [0,+10] windows from overlapping.
* Abnormal returns come from a market model fitted on days [-270,-21] before each event:
    - total:    r - (alpha + beta * MARKET_perp), MARKET_perp = market stripped of its oil
                component -> keeps everything oil did to the stock, removes other market noise.
    - relative: r - (alpha + beta * MARKET) -> classic market model, "winner or loser versus
                the index during the shock".
* Oslo closes about six hours before Brent settles, so part of a day-0 oil move only
  reaches Oslo prices on day +1. The impact window is therefore [0,+1].
* Inference is across events for one unit at a time (non-overlapping windows), never
  across stocks on the same day, which would ignore cross-sectional correlation.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from .. import MARKET, OIL
from ..stats import ols


def find_events(oil: pd.Series, z_threshold: float, vol_window: int, min_gap: int,
                lead: int, lag: int) -> pd.DataFrame:
    """Rule-based oil shocks. `lead`/`lag` = trading days needed before/after an event."""
    sigma = oil.rolling(vol_window).std().shift(1)
    z = oil / sigma
    rows, last_pos = [], -10**9
    for pos in np.flatnonzero((z.abs() >= z_threshold).to_numpy()):
        if pos - last_pos < min_gap or pos < lead or pos + lag >= len(oil):
            continue
        rows.append({"date": oil.index[pos], "pos": int(pos), "z": float(z.iloc[pos]),
                     "oil_day0": float(oil.iloc[pos]),
                     "direction": "up" if oil.iloc[pos] > 0 else "down"})
        last_pos = pos
    events = pd.DataFrame(rows)
    events.index.name = "event_id"
    return events


def _fit_line(y: np.ndarray, x: np.ndarray) -> tuple[float, float]:
    ok = np.isfinite(y) & np.isfinite(x)
    slope, intercept = np.polyfit(x[ok], y[ok], 1)
    return float(intercept), float(slope)


def _window(x: np.ndarray, start: int, stop: int) -> np.ndarray:
    """x[start:stop], padded with NaN where the data has not happened yet (recent events)."""
    out = np.full(stop - start, np.nan)
    seg = x[start:min(stop, len(x))]
    out[:len(seg)] = seg
    return out


def _event_ars(frame: pd.DataFrame, factors: pd.DataFrame, events: pd.DataFrame,
               estimation: tuple[int, int], lo: int, hi: int, min_est_obs: int):
    """Yield (event_id, event, unit, ar_total, ar_relative) with ARs for relative days lo..hi."""
    m_all, o_all = factors[MARKET].to_numpy(), factors[OIL].to_numpy()
    columns = {unit: frame[unit].to_numpy() for unit in frame.columns}
    for event_id, ev in events.iterrows():
        pos = int(ev["pos"])
        est = slice(pos + estimation[0], pos + estimation[1] + 1)
        m_evw, o_evw = _window(m_all, pos + lo, pos + hi + 1), _window(o_all, pos + lo, pos + hi + 1)
        a, gamma = _fit_line(m_all[est], o_all[est])
        m_perp_est = m_all[est] - (a + gamma * o_all[est])
        m_perp_evw = m_evw - (a + gamma * o_evw)
        for unit, r in columns.items():
            r_est, r_evw = r[est], _window(r, pos + lo, pos + hi + 1)
            if np.isfinite(r_est).sum() < min_est_obs:
                continue
            if unit == MARKET:                      # constant-mean model; "relative" is undefined
                ar_total = r_evw - np.nanmean(r_est)
                ar_rel = np.full_like(ar_total, np.nan)
            else:
                alpha, beta = _fit_line(r_est, m_perp_est)
                ar_total = r_evw - (alpha + beta * m_perp_evw)
                alpha_r, beta_r = _fit_line(r_est, m_all[est])
                ar_rel = r_evw - (alpha_r + beta_r * m_evw)
            yield event_id, ev, unit, ar_total, ar_rel


def abnormal_returns(frame: pd.DataFrame, factors: pd.DataFrame, events: pd.DataFrame,
                     estimation: tuple[int, int], windows: dict[str, list[int]],
                     min_est_obs: int = 120) -> pd.DataFrame:
    """CARs per event, unit and window. Long format."""
    o_all = factors[OIL].to_numpy()
    lo = min(w[0] for w in windows.values())
    hi = max(w[1] for w in windows.values())
    rows = []
    for event_id, ev, unit, ar_total, ar_rel in _event_ars(frame, factors, events, estimation, lo, hi, min_est_obs):
        pos = int(ev["pos"])
        for name, w in windows.items():
            sl = slice(w[0] - lo, w[1] - lo + 1)
            rows.append({"event_id": event_id, "date": ev["date"], "direction": ev["direction"],
                         "unit": unit, "window": name,
                         "oil_move": float(_window(o_all, pos + w[0], pos + w[1] + 1).sum()),
                         "car_total": float(ar_total[sl].sum()) if np.isfinite(ar_total[sl]).all() else np.nan,
                         "car_relative": float(ar_rel[sl].sum()) if np.isfinite(ar_rel[sl]).all() else np.nan})
    return pd.DataFrame(rows)


def car_paths(frame: pd.DataFrame, factors: pd.DataFrame, events: pd.DataFrame,
              estimation: tuple[int, int], span: tuple[int, int] = (-5, 10),
              min_est_obs: int = 120) -> pd.DataFrame:
    """Average cumulative abnormal return (total) by relative day, for up- and down-shocks.

    The path is cumulated from the first day of `span` and re-based to zero at day -1, so
    the value at day k >= 0 is the CAR over [0, k]. Oil's own path is included as unit OIL.
    """
    lo, hi = span
    days = np.arange(lo, hi + 1)
    o_all = factors[OIL].to_numpy()
    rows = []
    for event_id, ev, unit, ar_total, _ in _event_ars(frame, factors, events, estimation, lo, hi, min_est_obs):
        if np.isfinite(ar_total).all():
            cum = np.cumsum(ar_total)
            rows.append(pd.DataFrame({"event_id": event_id, "direction": ev["direction"], "unit": unit,
                                      "day": days, "car": cum - cum[-lo - 1]}))
    for event_id, ev in events.iterrows():
        cum = np.cumsum(_window(o_all, int(ev["pos"]) + lo, int(ev["pos"]) + hi + 1))
        if not np.isfinite(cum).all():          # window not complete yet
            continue
        rows.append(pd.DataFrame({"event_id": event_id, "direction": ev["direction"], "unit": OIL,
                                  "day": days, "car": cum - cum[-lo - 1]}))
    if not rows:                                # every event is still waiting for its full window
        return pd.DataFrame(columns=["unit", "direction", "day", "mean_car", "se", "n_events"])
    long = pd.concat(rows, ignore_index=True)
    out = long.groupby(["unit", "direction", "day"], sort=False)["car"].agg(["mean", "sem", "count"]).reset_index()
    return out.rename(columns={"mean": "mean_car", "sem": "se", "count": "n_events"})


def summarise(cars: pd.DataFrame, measure: str = "car_total") -> pd.DataFrame:
    """Mean CAR across events with a cross-event t-test, by unit, direction and window."""
    rows = []
    for (unit, direction, window), g in cars.groupby(["unit", "direction", "window"], sort=False):
        x = g[measure].dropna()
        if len(x) < 5:
            continue
        t, p = stats.ttest_1samp(x, 0.0)
        rows.append({"unit": unit, "direction": direction, "window": window, "n_events": len(x),
                     "mean_oil_move": g.loc[x.index, "oil_move"].mean(), "mean_car": x.mean(),
                     "t": float(t), "p": float(p), "share_positive": float((x > 0).mean())})
    return pd.DataFrame(rows)


def shock_betas(cars: pd.DataFrame, window: str = "impact", min_events: int = 10) -> pd.DataFrame:
    """Slope of CAR_total on the oil move across events: the oil beta measured *in shocks*.

    Comparable to the weekly total beta from step 2. White standard errors (each event is
    one independent observation).
    """
    rows = []
    sub = cars[cars["window"] == window]
    for unit, g in sub.groupby("unit", sort=False):
        g = g.dropna(subset=["car_total"])
        if len(g) < min_events:
            continue
        res = ols(g["car_total"].to_numpy(), g[["oil_move"]].to_numpy(), ["oil"], hac_lags=0)
        lo, hi = res.ci("oil")
        rows.append({"unit": unit, "n_events": res.nobs, "shock_beta": res.coef("oil"),
                     "shock_lo": lo, "shock_hi": hi, "shock_p": res.pvalue("oil"), "shock_r2": res.r2})
    return pd.DataFrame(rows).set_index("unit")
