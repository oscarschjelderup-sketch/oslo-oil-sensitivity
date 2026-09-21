"""Step 3b - what kind of oil shock was it?

Brent moves for two very different reasons. A *supply* shock (an outage, an OPEC decision, a
blockade) moves oil against the rest of the economy: oil up is bad news for most companies.
A *demand* shock (a growth scare, a pandemic, a boom) moves oil together with everything
else. An "oil beta" measured across both mixes the effect of oil with the effect of the news
that moved oil.

The split used here is the simplest one that does not need a structural model: over the same
[0,+1] window as the oil move, did global equities (S&P 500) move *with* oil or *against* it?

    same direction      -> demand-type shock
    opposite direction  -> supply-type shock

It is an ex-post label for an event study, not a forecast: the label uses the same two days as
the reaction it helps to explain. Because a sign is a blunt instrument when the equity move is
tiny, the module also reports a threshold-free version: the shock beta from a regression that
holds the global equity move fixed (`net_of_world`).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..stats import benjamini_hochberg, ols

WORLD, VIX = "WORLD", "VIX"


def classify_events(events: pd.DataFrame, panel: pd.DataFrame, oil_move: pd.Series,
                    window: tuple[int, int]) -> pd.DataFrame:
    """Add world_move, vix_change and shock_type to the events table.

    `panel` holds price levels on the common calendar; `oil_move` is the cumulative Brent log
    return over `window`, indexed by event_id. Prices are forward-filled first, so a US holiday
    inside the window counts as "no move that day" rather than as missing.
    """
    out = events.copy()
    if WORLD not in panel or out.empty:
        return out.assign(world_move=np.nan, vix_change=np.nan, shock_type=pd.Series(dtype=object))
    world = np.log(panel[WORLD].ffill()).to_numpy()
    vix = panel[VIX].ffill().to_numpy() if VIX in panel else None
    a, b = window
    moves, vix_changes = [], []
    for pos in out["pos"].astype(int):
        first, last = pos + a - 1, pos + b
        inside = first >= 0 and last < len(world)
        moves.append(world[last] - world[first] if inside else np.nan)
        vix_changes.append(vix[last] - vix[first] if inside and vix is not None else np.nan)
    out["world_move"], out["vix_change"] = moves, vix_changes
    out["oil_move"] = oil_move.reindex(out.index)
    same = np.sign(out["world_move"]) == np.sign(out["oil_move"])
    out["shock_type"] = np.where(out["world_move"].isna() | out["oil_move"].isna(), None,
                                 np.where(same, "demand", "supply"))
    return out


def type_counts(events: pd.DataFrame) -> pd.DataFrame:
    """How many shocks of each type, split by the direction of the oil move."""
    table = pd.crosstab(events["direction"], events["shock_type"]).reindex(
        index=["up", "down"], columns=["demand", "supply"], fill_value=0)
    table["share_demand"] = table["demand"] / table[["demand", "supply"]].sum(axis=1)
    return table


def betas_by_type(cars: pd.DataFrame, events: pd.DataFrame, meta: pd.DataFrame,
                  window: str = "impact", min_events: int = 8) -> pd.DataFrame:
    """Shock beta within demand-type and within supply-type shocks, and a test that they differ.

    One regression per unit across events (White standard errors, one event = one observation):
        CAR = a + a_s*S + b_demand*(oil*D) + b_supply*(oil*S)
    """
    labelled = cars[cars["window"] == window].join(events["shock_type"], on="event_id").dropna(
        subset=["shock_type", "car_total", "oil_move"])
    rows = []
    for unit, g in labelled.groupby("unit", sort=False):
        supply = (g["shock_type"] == "supply").to_numpy(dtype=float)
        n_supply, n_demand = int(supply.sum()), int(len(g) - supply.sum())
        if min(n_supply, n_demand) < min_events:
            continue
        oil = g["oil_move"].to_numpy()
        X = np.column_stack([supply, oil * (1 - supply), oil * supply])
        res = ols(g["car_total"].to_numpy(), X, ["supply_shift", "demand", "supply"], hac_lags=0)
        diff, t, p = res.test_equal("supply", "demand")
        rows.append({"unit": unit, "n_demand": n_demand, "n_supply": n_supply,
                     "beta_demand": res.coef("demand"), "se_demand": res.stderr("demand"),
                     "beta_supply": res.coef("supply"), "se_supply": res.stderr("supply"),
                     "difference": diff, "t_diff": t, "p_diff": p})
    table = pd.DataFrame(rows).set_index("unit")
    table = meta[["name", "kind", "sector"]].join(table, how="inner")
    table["q_diff"] = table.groupby("kind")["p_diff"].transform(lambda p: benjamini_hochberg(p.to_numpy()))
    return table


def betas_net_of_world(cars: pd.DataFrame, events: pd.DataFrame, meta: pd.DataFrame,
                       window: str = "impact", min_events: int = 15) -> pd.DataFrame:
    """Threshold-free version: CAR = a + b_oil*oil + b_world*world. b_oil is the reaction to oil
    with the global equity move held fixed; compare it with the plain shock beta."""
    labelled = cars[cars["window"] == window].join(events["world_move"], on="event_id").dropna(
        subset=["world_move", "car_total", "oil_move"])
    rows = []
    for unit, g in labelled.groupby("unit", sort=False):
        if len(g) < min_events:
            continue
        plain = ols(g["car_total"].to_numpy(), g[["oil_move"]].to_numpy(), ["oil"], hac_lags=0)
        res = ols(g["car_total"].to_numpy(), g[["oil_move", "world_move"]].to_numpy(), ["oil", "world"], hac_lags=0)
        lo, hi = res.ci("oil")
        rows.append({"unit": unit, "n_events": res.nobs, "shock_beta": plain.coef("oil"),
                     "beta_oil_net": res.coef("oil"), "net_lo": lo, "net_hi": hi, "net_p": res.pvalue("oil"),
                     "beta_world": res.coef("world"), "world_p": res.pvalue("world"), "r2": res.r2})
    table = pd.DataFrame(rows).set_index("unit")
    return meta[["name", "kind", "sector"]].join(table, how="inner")
