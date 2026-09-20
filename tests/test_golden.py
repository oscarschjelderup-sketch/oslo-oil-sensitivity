"""Regression ("golden") tests: a refactor must not move the numbers.

Two layers:

* `test_pinned_snapshot_...` re-runs the study on the real pinned snapshot and compares the
  headline numbers quoted in the README. The raw Yahoo prices are not redistributed, so this
  runs wherever data/raw/prices.csv exists and matches the SHA-256 in data/manifest.json
  (your machine), and is skipped elsewhere (CI).
* `test_end_to_end_on_a_synthetic_market` builds a seeded synthetic market, pushes it through
  the *whole* chain (pipeline, tables, workbook, figures, report, dashboard) and pins the
  results. It needs no downloaded data, so it guards every push in CI.
"""
import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from oilbeta import MARKET, pipeline, report
from oilbeta.config import Config, load_config

REPO = Path(__file__).resolve().parents[1]
QUIET = dict(log=lambda *_: None)

# Headline numbers of the pinned snapshot (configs/oslo.yaml, sample end 2026-09-11).
PINNED = {
    "index_beta_full": 0.286587, "index_beta_lo": 0.213891, "index_beta_hi": 0.359284,
    "index_beta_latest_window": 0.130235,
    "eqnr_total": 0.465176, "eqnr_partial": 0.242424, "nas_partial": -0.318514, "dnb_total": 0.284842,
    "shock_beta_ep": 0.550700, "oos_spearman_impact": 0.280400, "oos_t": 10.509944, "oos_spearman_drift": -0.011662,
    "index_beta_down": 0.369631, "index_beta_up": 0.186181, "pc1_share": 0.280381, "scenario_ep_10": 0.052953,
}
PINNED_COUNTS = {"n_events": 69, "n_up": 22, "oos_n": 63, "n_sig_partial": 16, "weeks": 997, "trading_days": 4610}


def headline(res) -> tuple[dict, dict]:
    T = res.tables
    full, roll, ev, oos = T["betas_full"], T["betas_rolling"], T["events"], T["oos_summary"]
    stocks = full[full["kind"] == "stock"]
    numbers = {
        "index_beta_full": full.loc[MARKET, "beta_oil_total"], "index_beta_lo": full.loc[MARKET, "total_lo"],
        "index_beta_hi": full.loc[MARKET, "total_hi"],
        "index_beta_latest_window": roll.loc[roll["unit"] == MARKET, "beta_oil_total"].iloc[-1],
        "shock_beta_ep": T["shock_betas"].loc["Exploration & production", "shock_beta"],
        "oos_spearman_impact": oos.loc["spearman_impact", "mean"], "oos_t": oos.loc["spearman_impact", "t"],
        "oos_spearman_drift": oos.loc["spearman_drift", "mean"],
        "index_beta_down": T["regime_direction"].loc[MARKET, "beta_down"],
        "index_beta_up": T["regime_direction"].loc[MARKET, "beta_up"],
        "pc1_share": T["pca_summary"].loc["PC1", "variance_share"],
        "scenario_ep_10": T["scenarios"].loc["Exploration & production", "exp_+10%"],
    }
    counts = {
        "n_events": len(ev), "n_up": int((ev["direction"] == "up").sum()),
        "oos_n": int(oos.loc["spearman_impact", "n_events"]),
        "n_sig_partial": int(((stocks["partial_p"] < 0.05) & (stocks["beta_oil_partial"] > 0)).sum()),
        "weeks": res.info["sample"]["weeks"], "trading_days": res.info["sample"]["trading_days"],
    }
    return numbers, counts


def test_pinned_snapshot_reproduces_the_published_numbers():
    cfg = load_config(REPO / "configs" / "oslo.yaml")
    if not cfg.prices_path.exists():
        pytest.skip("pinned raw prices are not in this checkout (they are not redistributed)")
    expected_sha = json.loads(cfg.manifest_path.read_text(encoding="utf-8"))["sha256"]
    if hashlib.sha256(cfg.prices_path.read_bytes()).hexdigest() != expected_sha:
        pytest.skip("data/raw/prices.csv is not the snapshot described by data/manifest.json")

    res = pipeline.run(cfg, rolling_stocks=False, **QUIET)
    numbers, counts = headline(res)
    full = res.tables["betas_full"]
    numbers |= {"eqnr_total": full.loc["EQNR.OL", "beta_oil_total"], "eqnr_partial": full.loc["EQNR.OL", "beta_oil_partial"],
                "nas_partial": full.loc["NAS.OL", "beta_oil_partial"], "dnb_total": full.loc["DNB.OL", "beta_oil_total"]}
    assert counts == PINNED_COUNTS
    assert numbers == pytest.approx(PINNED, abs=2e-6)


# --------------------------------------------------------------------------
SECTORS = {"Exploration & production": (1.0, 0.50), "Oil service & drilling": (1.2, 0.40),
           "Banks & insurance": (0.9, 0.00), "Seafood": (0.7, -0.10)}       # (market beta, direct oil beta)


def synthetic_config(tmp_path: Path) -> Config:
    raw = copy.deepcopy(yaml.safe_load((REPO / "configs" / "oslo.yaml").read_text(encoding="utf-8")))
    raw["sample"] = {"start": "2008-01-01", "end": "2016-12-30"}
    raw["data_exceptions"] = {}
    raw["universe"] = {s: {f"{s[:3].upper()}{i}.OL": f"{s.split()[0]} {i}" for i in range(4)} for s in SECTORS}
    return Config(raw=raw, root=tmp_path)


def synthetic_prices(cfg: Config) -> pd.DataFrame:
    rng = np.random.default_rng(20260911)
    idx = pd.bdate_range(cfg.start, cfg.end, name="Date")
    n = len(idx)
    oil = rng.standard_t(df=4, size=n) * 0.015                      # fat tails -> real oil shocks
    market = 0.3 * oil + rng.normal(scale=0.009, size=n)
    level = lambda r: 100 * np.exp(np.cumsum(r))                     # noqa: E731
    cols = {cfg.oil_ticker: level(oil)}
    index_level = level(market)
    splice = pd.Timestamp(cfg.market["splice_date"])
    cols[cfg.market["early_ticker"]] = np.where(idx <= splice + pd.Timedelta(days=120), index_level, np.nan)
    cols[cfg.market["late_ticker"]] = np.where(idx >= splice, index_level * 7.0, np.nan)
    for ticker in cfg.context.values():
        cols[ticker] = level(rng.normal(scale=0.006, size=n))
    for sector, members in cfg.universe.items():
        b_mkt, b_oil = SECTORS[sector]
        for ticker in members:
            cols[ticker] = level(b_mkt * market + b_oil * oil + rng.normal(scale=0.014, size=n))
    return pd.DataFrame(cols, index=idx)


SYNTHETIC = {
    "index_beta_full": 0.298333, "index_beta_lo": 0.260508, "index_beta_hi": 0.336157,
    "index_beta_latest_window": 0.298561, "shock_beta_ep": 0.747326,
    "oos_spearman_impact": 0.632895, "oos_t": 18.721530, "oos_spearman_drift": -0.029102,
    "index_beta_down": 0.288535, "index_beta_up": 0.310068, "pc1_share": 0.468299, "scenario_ep_10": 0.082027,
}
SYNTHETIC_COUNTS = {"n_events": 41, "n_up": 17, "oos_n": 38, "n_sig_partial": 8, "weeks": 469, "trading_days": 2348}


def test_end_to_end_on_a_synthetic_market(tmp_path):
    cfg = synthetic_config(tmp_path)
    cfg.raw_dir.mkdir(parents=True)
    synthetic_prices(cfg).to_csv(cfg.prices_path, float_format="%.6f")

    res = pipeline.run(cfg, **QUIET)
    paths = report.write_all(res)

    # 1. the planted structure comes back out
    full = res.tables["betas_full"]
    assert full.loc[MARKET, "beta_oil_total"] == pytest.approx(0.30, abs=0.05)
    assert full.loc["Exploration & production", "beta_oil_partial"] == pytest.approx(0.50, abs=0.05)
    assert full.loc["Banks & insurance", "beta_oil_partial"] == pytest.approx(0.00, abs=0.05)
    assert full.loc["Seafood", "beta_oil_total"] == pytest.approx(-0.10 + 0.7 * 0.30, abs=0.05)
    assert res.tables["oos_summary"].loc["spearman_impact", "mean"] > 0.3

    # 2. every deliverable is written and the monitor's payload is valid
    for key in ("report", "dashboard", "workbook"):
        assert paths[key].stat().st_size > 10_000, key
    assert len(list(paths["figures"].glob("*.png"))) == 10
    payload = json.loads((cfg.results_dir / "dashboard.json").read_text(encoding="utf-8"))
    assert payload["meta"]["n_stocks"] == 16 and len(payload["units"]) == 21 and not payload["meta"]["live"]
    assert payload["shocks"]["latest"]["rows"] and payload["rolling"]["dates"][-1] <= cfg.end
    assert pd.ExcelFile(paths["workbook"]).sheet_names[0] == "Betas (full sample)"

    # 3. and the numbers are exactly the ones this code produced when the test was written
    numbers, counts = headline(res)
    assert counts == SYNTHETIC_COUNTS
    assert numbers == pytest.approx(SYNTHETIC, abs=1e-6)
