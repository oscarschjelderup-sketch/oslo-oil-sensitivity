"""Multiple-testing correction and the demand/supply split of oil shocks."""
import numpy as np
import pandas as pd
import pytest
from scipy import stats

from oilbeta import MARKET, OIL
from oilbeta.analysis import betas, events, shocktype
from oilbeta.stats import benjamini_hochberg


def test_bh_matches_scipy_and_a_hand_example(rng):
    p = rng.uniform(size=200) ** 2
    assert np.allclose(benjamini_hochberg(p), stats.false_discovery_control(p, method="bh"))
    # classic textbook case: m = 5
    q = benjamini_hochberg([0.01, 0.04, 0.03, 0.005, 0.20])
    assert q == pytest.approx([0.025, 0.05, 0.05, 0.025, 0.20])


def test_bh_ignores_missing_tests_and_never_exceeds_one():
    q = benjamini_hochberg([0.9, np.nan, 0.95, 0.001])
    assert np.isnan(q[1]) and q[3] == pytest.approx(0.003)           # three tests, not four
    assert np.nanmax(q) <= 1.0 and np.all(np.diff(np.sort(q[np.isfinite(q)])) >= 0)
    assert np.isnan(benjamini_hochberg([np.nan, np.nan])).all()


def test_fdr_removes_most_false_positives_that_raw_p_values_let_through(rng):
    """200 stocks with NO oil exposure: raw 5% tests flag about ten of them, a 5% FDR almost none."""
    T, n = 600, 200
    o = rng.normal(scale=0.04, size=T)
    m = rng.normal(scale=0.02, size=T)
    idx = pd.date_range("2012-01-06", periods=T, freq="W-FRI")
    frame = pd.DataFrame(np.outer(m, np.ones(n)) + rng.normal(scale=0.03, size=(T, n)), index=idx,
                         columns=[f"S{i}" for i in range(n)])
    meta = pd.DataFrame({"name": frame.columns, "kind": "stock", "sector": "x"}, index=frame.columns)
    table = betas.beta_table(frame, meta, pd.DataFrame({MARKET: m, OIL: o}, index=idx), min_obs=100)
    raw, fdr = int((table["partial_p"] < 0.05).sum()), int((table["partial_q"] < 0.05).sum())
    assert 3 <= raw <= 25 and fdr <= 1
    assert (table["partial_q"] >= table["partial_p"] - 1e-12).all()


@pytest.fixture
def shock_world(rng):
    """Oil shocks of two kinds. Demand-type: world equities move with oil and the stock loads on the
    world. Supply-type: world moves against oil. The stock's true oil beta is 0.2 in both."""
    T = 3200
    idx = pd.bdate_range("2008-01-01", periods=T)
    o = np.clip(rng.normal(scale=0.012, size=T), -0.025, 0.025)
    w = rng.normal(scale=0.004, size=T)
    shock_days = np.arange(300, T - 20, 40)
    kinds = np.where(np.arange(len(shock_days)) % 2 == 0, "demand", "supply")
    for day, kind in zip(shock_days, kinds):
        size = rng.choice([-1, 1]) * rng.uniform(0.06, 0.10)
        o[day] = size
        w[day] = (0.3 if kind == "demand" else -0.3) * size
    m = 0.2 * o + rng.normal(scale=0.006, size=T)
    energy = 0.6 * o + rng.normal(scale=0.006, size=T)                   # pure oil exposure
    cyclical = 0.2 * o + 1.0 * w + rng.normal(scale=0.006, size=T)       # oil + world exposure
    returns = pd.DataFrame({MARKET: m, OIL: o, "ENERGY": energy, "CYCLICAL": cyclical}, index=idx)
    panel = pd.DataFrame({"WORLD": 100 * np.exp(np.cumsum(w)), "VIX": 20 + np.cumsum(rng.normal(size=T)) * 0.1}, index=idx)
    return returns, panel, dict(zip(shock_days, kinds))


def test_shocks_are_labelled_by_the_sign_of_the_world_move(shock_world):
    returns, panel, truth = shock_world
    ev = events.find_events(returns[OIL], 2.5, 250, 11, lead=270, lag=1)
    cars = events.abnormal_returns(returns[[MARKET, "ENERGY", "CYCLICAL"]], returns[[MARKET, OIL]], ev, (-270, -21),
                                   {"impact": [0, 1], "drift": [2, 10]})
    oil_move = cars[cars["window"] == "impact"].groupby("event_id")["oil_move"].first()
    labelled = shocktype.classify_events(ev, panel, oil_move, (0, 1))
    planted = labelled["pos"].map(truth)
    assert len(labelled) >= 40 and planted.notna().all()
    assert (labelled["shock_type"] == planted).mean() > 0.95
    counts = shocktype.type_counts(labelled)
    assert int(counts[["demand", "supply"]].to_numpy().sum()) == len(labelled)
    assert counts["share_demand"].between(0, 1).all()


def test_split_betas_separate_oil_from_the_news_that_moved_oil(shock_world):
    returns, panel, _ = shock_world
    ev = events.find_events(returns[OIL], 2.5, 250, 11, lead=270, lag=1)
    cars = events.abnormal_returns(returns[[MARKET, "ENERGY", "CYCLICAL"]], returns[[MARKET, OIL]], ev, (-270, -21),
                                   {"impact": [0, 1], "drift": [2, 10]})
    oil_move = cars[cars["window"] == "impact"].groupby("event_id")["oil_move"].first()
    ev = shocktype.classify_events(ev, panel, oil_move, (0, 1))
    meta = pd.DataFrame({"name": ["Index", "Energy", "Cyclical"], "kind": ["market", "stock", "stock"],
                         "sector": ["", "e", "c"]}, index=[MARKET, "ENERGY", "CYCLICAL"])
    by_type = shocktype.betas_by_type(cars, ev, meta)
    # energy reacts the same to both kinds; the cyclical stock only looks oil-sensitive in demand-type shocks
    assert by_type.loc["ENERGY", "beta_demand"] == pytest.approx(0.6, abs=0.07)
    assert by_type.loc["ENERGY", "beta_supply"] == pytest.approx(0.6, abs=0.07)
    assert by_type.loc["ENERGY", "p_diff"] > 0.05
    assert by_type.loc["CYCLICAL", "beta_demand"] == pytest.approx(0.2 + 0.3, abs=0.08)
    assert by_type.loc["CYCLICAL", "beta_supply"] == pytest.approx(0.2 - 0.3, abs=0.08)
    assert by_type.loc["CYCLICAL", "q_diff"] < 0.001
    # holding the world move fixed recovers the true oil beta of 0.2
    net = shocktype.betas_net_of_world(cars, ev, meta)
    assert net.loc["CYCLICAL", "beta_oil_net"] == pytest.approx(0.2, abs=0.06)
    assert net.loc["CYCLICAL", "beta_world"] == pytest.approx(1.0, abs=0.2)
    assert net.loc["CYCLICAL", "net_lo"] < 0.2 < net.loc["CYCLICAL", "net_hi"]


def test_no_world_series_means_no_labels_not_a_crash(rng):
    idx = pd.bdate_range("2015-01-01", periods=600)
    oil = pd.Series(np.clip(rng.normal(scale=0.01, size=600), -0.02, 0.02), index=idx)
    oil.iloc[400] = 0.10
    ev = events.find_events(oil, 2.5, 250, 11, lead=270, lag=1)
    out = shocktype.classify_events(ev, pd.DataFrame({"OTHER": 1.0}, index=idx), pd.Series({0: 0.1}), (0, 1))
    assert out["shock_type"].isna().all() and "world_move" in out
