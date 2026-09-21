"""The factsheet is a contract with another tool, so its shape is part of the tested surface."""
import json

import numpy as np
import pandas as pd
import pytest

from conftest import study_dict
from oilbeta import MARKET, OIL
from oilbeta.config import Config
from oilbeta.outputs import factsheet


@pytest.fixture
def weekly(rng):
    """208 weeks in which the stock's true total oil beta is 0.5 and its market beta 1.0."""
    idx = pd.date_range("2022-09-16", periods=208, freq="W-FRI")
    oil = rng.normal(scale=0.04, size=len(idx))
    market = 0.3 * oil + rng.normal(scale=0.02, size=len(idx))
    stock = 1.0 * market + 0.2 * oil + rng.normal(scale=0.02, size=len(idx))
    index_tracker = 1.0 * market + rng.normal(scale=0.01, size=len(idx))     # moves with the index, no oil of its own
    return pd.DataFrame({MARKET: market, OIL: oil, "AAA.OL": stock, "BBB.OL": index_tracker}, index=idx)


@pytest.fixture
def cfg(tmp_path):
    study = study_dict()
    study["sample"] = {"start": "2022-09-16", "end": "2026-09-11"}
    study["scenarios"]["window"] = 104
    return Config.from_dicts(study, {"Energy": {"AAA.OL": "Alpha", "BBB.OL": "Beta"}}, None, tmp_path)


def test_the_document_carries_what_a_reader_needs_to_judge_it(cfg, weekly):
    doc = factsheet.build(cfg, weekly, "AAA.OL")
    assert doc["schema"] == "oilbeta.stock/1"
    assert doc["ticker"] == "AAA.OL" and doc["name"] == "Alpha" and doc["sector"] == "Energy"
    assert doc["sample"] == {"start": str(weekly.index.min().date()), "end": str(weekly.index.max().date()),
                             "frequency": "weekly"}        # the data's own span, not the config's end date
    assert doc["source"]["url"].startswith("https://") and "Newey-West" in doc["source"]["method"]
    assert doc["caveats"] and any("causation" in c for c in doc["caveats"])

    assert doc["headline_window"] == "last_2_years" and set(doc["windows"]) == {"full_history", "last_2_years"}
    full = doc["windows"]["full_history"]
    assert full["weeks"] == len(weekly)
    # The planted truth: 0.2 direct oil exposure, plus 1.0 x 0.3 through the index = 0.5 total. These
    # assert the reported 95% intervals cover it, which is the property that matters to a reader. The
    # draw is seeded, so this is deterministic - on another seed a 95% interval would miss 5% of the time.
    assert full["total_lo"] <= 0.5 <= full["total_hi"]
    assert full["partial_lo"] <= 0.2 <= full["partial_hi"]
    assert full["total_lo"] < full["beta_oil_total"] < full["total_hi"]
    assert full["partial_p"] < 0.05 and full["variance_explained_by_oil"] > 0.2
    assert doc["windows"]["last_2_years"]["weeks"] == 104


def test_every_scenario_is_signed_bounded_and_ordered(cfg, weekly):
    full = factsheet.build(cfg, weekly, "AAA.OL")["windows"]["full_history"]
    shocks = [s["brent"] for s in full["scenarios"]]
    assert shocks == sorted(shocks) == sorted(cfg.scenarios.shocks)
    for s in full["scenarios"]:
        assert s["lo"] <= s["expected"] <= s["hi"]
        assert np.sign(s["expected"]) == np.sign(s["brent"])           # a positive beta moves with oil
        assert 0.5 <= s["p_same_sign"] <= 1.0
        assert abs(s["expected"]) < abs(s["brent"])                    # a beta below 1 cannot amplify the move


def test_a_stock_that_only_moves_with_the_index_reports_no_direct_exposure(cfg, weekly):
    """BBB.OL is the index: its total beta is the index's own, and its partial beta is zero."""
    full = factsheet.build(cfg, weekly, "BBB.OL")["windows"]["full_history"]
    assert full["partial_lo"] <= 0.0 <= full["partial_hi"]     # the interval covers "no direct exposure"
    assert full["partial_p"] > 0.05                            # and there is no evidence against it
    assert full["beta_oil_total"] == pytest.approx(0.3, abs=0.06)   # what it has is the index's own oil beta


def test_sector_context_is_added_only_when_it_is_known(cfg, weekly, tmp_path):
    sectors = pd.DataFrame({"beta_oil_total": [0.64, 0.11]}, index=["Energy", "Seafood"])
    doc = factsheet.build(cfg, weekly, "AAA.OL", sector_betas=sectors)
    assert doc["sector_context"] == {"name": "Energy", "beta_oil_total": 0.64, "rank": 1, "of": 2}
    assert "sector_context" not in factsheet.build(cfg, weekly, "AAA.OL")

    path = factsheet.write(doc, tmp_path / "out" / "AAA.OL.json")
    assert json.loads(path.read_text(encoding="utf-8")) == doc        # round-trips, and creates its folder
