"""Price sources, the supplement mechanism and the oil-series robustness check. No network: fake sources."""
import hashlib
import json

import numpy as np
import pandas as pd
import pytest

from conftest import study_dict
from oilbeta import data
from oilbeta.analysis import robustness
from oilbeta.config import Config
from oilbeta.data.snapshot import _supplement_path


class FakeSource:
    """Returns slices of a prepared frame and records what it was asked for."""

    name = "fake vendor"

    def __init__(self, frame: pd.DataFrame):
        self.frame, self.calls = frame, []

    def fetch(self, tickers, start, end):
        self.calls.append((list(tickers), start, end))
        return self.frame.loc[start:end].reindex(columns=list(tickers))


@pytest.fixture
def market(rng):
    idx = pd.bdate_range("2004-12-01", "2012-12-31", name="Date")
    n = len(idx)
    oil = rng.standard_t(df=4, size=n) * 0.015
    m = 0.3 * oil + rng.normal(scale=0.009, size=n)
    level = lambda r: 100 * np.exp(np.cumsum(r))                     # noqa: E731
    frame = pd.DataFrame({"BZ=F": level(oil), "OSEFX.OL": level(m), "OSEBX.OL": level(m) * 7, "NOK=X": level(rng.normal(scale=0.006, size=n)),
                          "^VIX": level(rng.normal(scale=0.03, size=n)), "^GSPC": level(rng.normal(scale=0.01, size=n))}, index=idx)
    for i, b in enumerate([0.6, 0.5, 0.0, -0.1]):
        frame[f"S{i}.OL"] = level(m + b * oil + rng.normal(scale=0.012, size=n))
    frame.loc[:"2007-07-29", "BZ=F"] = np.nan                        # the future has no early history, like the real one
    spot = pd.DataFrame({"DCOILBRENTEU": level(oil + rng.normal(scale=0.004, size=n))}, index=idx)
    return frame, spot


@pytest.fixture
def cfg(tmp_path):
    study = study_dict()
    study["sample"] = {"start": "2007-07-30", "end": "2012-12-31"}
    universe = {"Energy": {"S0.OL": "Zero", "S1.OL": "One"}, "Other": {"S2.OL": "Two", "S3.OL": "Three"}}
    return Config.from_dicts(study, universe, None, tmp_path)


def test_a_new_series_is_added_without_touching_the_pinned_snapshot(cfg, market):
    frame, _ = market
    source = FakeSource(frame)
    first = data.fetch_prices(cfg, refresh=True, source=source)
    sha = hashlib.sha256(cfg.prices_path.read_bytes()).hexdigest()
    assert json.loads(cfg.manifest_path.read_text())["sha256"] == sha and "^GSPC" in first

    # pretend the snapshot was pinned before the world index became part of the study
    first.drop(columns="^GSPC").to_csv(cfg.prices_path, float_format="%.6f")
    sha_old = hashlib.sha256(cfg.prices_path.read_bytes()).hexdigest()
    source.calls.clear()
    again = data.fetch_prices(cfg, source=source)

    assert source.calls == [(["^GSPC"], "2007-07-30", "2012-12-31")]              # only the missing series, same dates
    assert hashlib.sha256(cfg.prices_path.read_bytes()).hexdigest() == sha_old   # the pinned file is untouched
    assert again["^GSPC"].notna().sum() > 1000 and list(again.columns[:-1]) == list(first.drop(columns="^GSPC").columns)
    manifest = json.loads(cfg.manifest_path.read_text())
    assert manifest["supplement"]["source"] == "fake vendor" and "^GSPC" in manifest["supplement"]["series"]
    data.fetch_prices(cfg, source=source)
    assert len(source.calls) == 1                                                # the supplement is cached too

    data.fetch_prices(cfg, refresh=True, source=source)                          # a full refresh makes it redundant
    assert not _supplement_path(cfg).exists() and "supplement" not in json.loads(cfg.manifest_path.read_text())


def test_a_download_that_stops_early_is_rejected(cfg, market):
    frame, _ = market
    with pytest.raises(RuntimeError, match="only reaches"):
        data.fetch_prices(cfg, refresh=True, source=FakeSource(frame.loc[:"2012-06-30"]))


def test_robustness_inputs_are_cached_and_described(cfg, market):
    frame, spot = market
    yahoo, fred = FakeSource(frame), FakeSource(spot)
    extra = data.fetch_robustness(cfg, yahoo=yahoo, fred=fred)
    assert extra["long"].index.min() == pd.Timestamp("2005-01-03") and extra["fred"].index.min() < pd.Timestamp("2005-01-03")
    assert fred.calls[0][0] == ["DCOILBRENTEU"] and yahoo.calls[0][1] == "2005-01-03"
    manifest = json.loads(cfg.manifest_path.read_text())["robustness"]
    assert set(manifest) == {"fred_brent", "prices_long"} and len(manifest["fred_brent"]["sha256"]) == 64
    data.fetch_robustness(cfg, yahoo=yahoo, fred=fred)
    assert len(yahoo.calls) == 1 and len(fred.calls) == 1


def test_oil_series_check_compares_three_variants(cfg, market):
    frame, spot = market
    prices = frame.loc["2007-07-30":]
    check = robustness.oil_series_check(cfg, prices, spot, frame)
    s = check["summary"]
    assert list(s.index) == [robustness.BASELINE, robustness.SPOT, robustness.SPOT_LONG]
    assert s.loc[robustness.BASELINE, "rank_corr_with_baseline"] == 1.0 and s.loc[robustness.BASELINE, "max_abs_beta_change"] == 0.0
    assert s.loc[robustness.SPOT_LONG, "weeks"] > s.loc[robustness.SPOT, "weeks"] + 100
    assert s.loc[robustness.SPOT_LONG, "first_week"] < s.loc[robustness.BASELINE, "first_week"]
    # a noisy copy of the same oil series gives nearly the same betas
    assert s["index_beta"].to_numpy() == pytest.approx(0.30, abs=0.06)
    assert check["agreement"]["weekly_return_correlation"] > 0.9
    pre = check["agreement"]["pre_crisis"]
    assert pre["windows"] > 50 and pre["last_end"] < robustness.CRISIS_START and pre["min"] <= pre["mean"] <= pre["max"]
    assert set(check["rolling"]["variant"]) == set(s.index)


def test_window_average_handles_an_empty_range():
    rolling = pd.DataFrame({"variant": ["x"], "date": [pd.Timestamp("2020-01-03")], "beta_oil_total": [0.2]})
    assert robustness.window_average(rolling, "x", None, "2010-01-01")["windows"] == 0
    assert robustness.window_average(rolling, "x", "2019-01-01", None)["mean"] == 0.2
