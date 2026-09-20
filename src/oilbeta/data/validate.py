"""Data-quality report. Flags, never silent fixes: removals live in the config with a reason."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import Config
from .align import daily_returns, weekly_returns


def validate(panel: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """One row per series: coverage, staleness and suspicious prints. Flags, never silent fixes."""
    v = cfg.validation
    daily = daily_returns(panel, cfg)      # after the documented exceptions, so a flag
    weekly = weekly_returns(panel, cfg)    # here means "still in the sample"
    n_dropped = pd.Series([e.ticker for e in cfg.exceptions.drop_returns], dtype=object).value_counts()
    min_weeks = cfg.betas.min_history
    rows = []
    for col in panel.columns:
        p, r = panel[col].dropna(), daily[col].dropna()
        live = daily[col].loc[p.index.min():p.index.max()]
        zero_share = float((r == 0).mean()) if len(r) else np.nan
        flags = []
        if weekly[col].notna().sum() < min_weeks:
            flags.append("short history")
        if zero_share > v.max_zero_return_share:
            flags.append("stale prices")
        if (r.abs() > v.max_abs_daily_return).any():
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
            "extreme_days": int((r.abs() > v.max_abs_daily_return).sum()),
            "returns_dropped": int(n_dropped.get(col, 0)),
            "history_trimmed": col in cfg.exceptions.history_start,
            "flags": "; ".join(flags) or "ok",
        })
    return pd.DataFrame(rows)
