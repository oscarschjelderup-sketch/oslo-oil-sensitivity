"""One stock's oil sensitivity as a small, versioned JSON document.

This is the contract another tool reads — the equity-research-engine puts it in the risk section
of a case. The two projects stay independent: what crosses between them is this file, not a Python
import, so either can be rewritten as long as the schema holds.

Two rules the format enforces:

* every estimate carries its interval and the number of weeks behind it, so a reader can see how
  much is known, not only what was estimated;
* `caveats` travels with the numbers. A deck that prints the beta also prints what it does not mean.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from .. import MARKET, OIL, __version__
from ..analysis import betas
from ..config import Config

SCHEMA = "oilbeta.stock/1"
REPO = "https://github.com/oscarschjelderup-sketch/oslo-oil-sensitivity"

CAVEATS = [
    "An oil beta is co-movement with a sign, not causation: Brent moves for demand as well as supply reasons.",
    "Outside energy most of the oil beta is a demand-shock beta — it reflects the news that moved oil, not the oil price.",
    "The interval covers uncertainty about the expected move only. P(same sign) is how often the move actually goes that way.",
    "Estimated on a universe of today's listings, so delisted companies are missing (survivorship).",
]


def _window(r: np.ndarray, m: np.ndarray, o: np.ndarray, hac_lags, shocks: list[float]) -> dict:
    est = betas.oil_betas(r, m, o, hac_lags)
    out = {
        "weeks": est["nobs"],
        "beta_market": round(est["beta_mkt"], 4),
        "beta_oil_partial": round(est["beta_oil_partial"], 4),
        "partial_lo": round(est["partial_lo"], 4), "partial_hi": round(est["partial_hi"], 4),
        "partial_p": round(est["partial_p"], 4),
        "beta_oil_total": round(est["beta_oil_total"], 4),
        "total_lo": round(est["total_lo"], 4), "total_hi": round(est["total_hi"], 4),
        "total_p": round(est["total_p"], 4),
        "variance_explained_by_oil": round(est["r2_oil_only"], 4),
        "scenarios": [],
    }
    for shock in sorted(shocks):
        x = np.log1p(shock)
        bounds = sorted(float(np.expm1(b * x)) for b in (est["total_lo"], est["total_hi"]))
        out["scenarios"].append({
            "brent": shock,
            "expected": round(float(np.expm1(est["beta_oil_total"] * x)), 4),
            "lo": round(bounds[0], 4), "hi": round(bounds[1], 4),
            "p_same_sign": round(float(stats.norm.cdf(abs(est["beta_oil_total"] * x) / est["non_oil_vol"])), 4),
        })
    return out


def build(cfg: Config, weekly: pd.DataFrame, ticker: str, sector_betas: pd.DataFrame | None = None) -> dict:
    """The factsheet for one ticker. `weekly` must hold MARKET, OIL and the ticker."""
    m, o = weekly[MARKET].to_numpy(), weekly[OIL].to_numpy()
    r = weekly[ticker].to_numpy()
    recent = cfg.scenarios.window
    years = recent // 52
    doc = {
        "schema": SCHEMA,
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": {"study": "oslo-oil-sensitivity", "version": __version__, "url": REPO,
                   "method": "r = a + b_mkt*index + b_oil*Brent on Friday-to-Friday log returns, Newey-West standard errors; "
                             "the total beta orthogonalises the index against oil first, so it is the effect through every channel"},
        "ticker": ticker,
        "name": cfg.names.get(ticker, ticker),
        "sector": cfg.sector_of.get(ticker),
        "market_index": cfg.market.name,
        "oil_series": cfg.study.factors.oil.name,
        "sample": {"start": str(weekly.index.min().date()), "end": str(weekly.index.max().date()), "frequency": "weekly"},
        "windows": {
            "full_history": _window(r, m, o, cfg.betas.hac_lags, cfg.scenarios.shocks),
            f"last_{years}_years": _window(r[-recent:], m[-recent:], o[-recent:], cfg.betas.hac_lags, cfg.scenarios.shocks),
        },
        "caveats": CAVEATS,
    }
    doc["headline_window"] = f"last_{years}_years"
    if sector_betas is not None and doc["sector"] in sector_betas.index:
        ranked = sector_betas.sort_values("beta_oil_total", ascending=False)
        doc["sector_context"] = {
            "name": doc["sector"],
            "beta_oil_total": round(float(ranked.loc[doc["sector"], "beta_oil_total"]), 4),
            "rank": int(ranked.index.get_loc(doc["sector"])) + 1,
            "of": int(len(ranked)),
        }
    return doc


def write(doc: dict, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
