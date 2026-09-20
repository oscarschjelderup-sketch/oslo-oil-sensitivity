"""Betas, event study, scenarios, regimes and PCA on synthetic data with known answers."""
import numpy as np
import pandas as pd
import pytest

from oilbeta import MARKET, OIL, betas, events, pca, regimes, scenarios


@pytest.fixture
def world(rng):
    """Market with oil beta 0.3; stock A loads on oil directly (0.5), stock B only via the market."""
    T = 3000
    idx = pd.bdate_range("2010-01-01", periods=T)
    o = rng.normal(scale=0.02, size=T)
    m = 0.3 * o + rng.normal(scale=0.01, size=T)
    a = 1.0 * m + 0.5 * o + rng.normal(scale=0.01, size=T)
    b = 1.2 * m + rng.normal(scale=0.01, size=T)
    return pd.DataFrame({MARKET: m, OIL: o, "A": a, "B": b}, index=idx)


def test_partial_and_total_beta_recover_the_truth(world):
    est_a = betas.oil_betas(world["A"].to_numpy(), world[MARKET].to_numpy(), world[OIL].to_numpy())
    est_b = betas.oil_betas(world["B"].to_numpy(), world[MARKET].to_numpy(), world[OIL].to_numpy())
    assert est_a["beta_oil_partial"] == pytest.approx(0.5, abs=0.04)
    assert est_a["beta_oil_total"] == pytest.approx(0.5 + 1.0 * 0.3, abs=0.04)
    assert est_b["beta_oil_partial"] == pytest.approx(0.0, abs=0.04)      # no direct oil exposure...
    assert est_b["beta_oil_total"] == pytest.approx(1.2 * 0.3, abs=0.04)   # ...but plenty through the index
    assert est_a["total_lo"] < 0.8 < est_a["total_hi"]


def test_total_beta_identity_and_univariate_equivalence(world):
    r, m, o = (world[c].to_numpy() for c in ("A", MARKET, OIL))
    est = betas.oil_betas(r, m, o)
    assert est["beta_oil_total"] == pytest.approx(est["beta_oil_partial"] + est["beta_mkt"] * est["market_oil_beta"])
    assert est["beta_oil_total"] == pytest.approx(np.cov(r, o)[0, 1] / o.var(ddof=1))
    one_factor = betas.market_oil_beta(r, o)      # same point estimate, wider interval
    assert one_factor["total_se"] > est["total_se"]


def test_rolling_betas_respect_min_obs(world):
    frame = world[["A"]].iloc[:400].copy()
    frame.iloc[:150] = np.nan
    roll = betas.rolling_betas(frame, world[[MARKET, OIL]].iloc[:400], window=200, min_obs=150)
    assert roll["date"].min() == frame.index[299]          # first window with 150 valid rows
    assert (roll["nobs"] >= 150).all()


def test_event_rule_has_no_look_ahead_and_enforces_the_gap():
    idx = pd.bdate_range("2015-01-01", periods=600)
    oil = pd.Series(np.tile([0.01, -0.01], 300), index=idx)
    oil.iloc[[400, 403, 450]] = [0.10, -0.10, 0.10]
    ev = events.find_events(oil, z_threshold=2.5, vol_window=250, min_gap=11, lead=270, lag=10)
    assert list(ev["pos"]) == [400, 450]                   # 403 sits inside the gap
    assert ev.loc[0, "z"] == pytest.approx(0.10 / oil.iloc[150:400].std())   # vol ends the day before


def test_event_study_recovers_the_shock_beta(world, rng):
    frame = world[[MARKET, "A", "B"]]
    ev = events.find_events(world[OIL], 2.0, 250, 11, lead=270, lag=10)
    windows = {"pre": [-5, -1], "impact": [0, 1], "drift": [2, 10]}
    cars = events.abnormal_returns(frame, world[[MARKET, OIL]], ev, (-270, -21), windows)
    sb = events.shock_betas(cars)
    assert sb.loc["A", "shock_beta"] == pytest.approx(0.8, abs=0.08)
    assert sb.loc["B", "shock_beta"] == pytest.approx(0.36, abs=0.08)
    assert sb.loc[MARKET, "shock_beta"] == pytest.approx(0.3, abs=0.08)
    summary = events.summarise(cars).set_index(["unit", "direction", "window"])
    assert summary.loc[("A", "up", "impact"), "mean_car"] > 0 > summary.loc[("A", "down", "impact"), "mean_car"]
    assert abs(summary.loc[("A", "up", "drift"), "t"]) < 3          # nothing happens after the shock
    rel = events.summarise(cars, "car_relative").set_index(["unit", "direction", "window"])
    assert abs(rel.loc[("B", "up", "impact"), "t"]) < 3             # B only moves with the index


def test_past_betas_ignore_the_future(world):
    weekly = world.resample("W-FRI").sum()
    cut = weekly.index[300]
    before = scenarios._past_betas(weekly[["A", "B"]], weekly[OIL], cut, window=260, min_history=104)
    tampered = weekly.copy()
    tampered.loc[tampered.index >= cut, "A"] = 99.0
    after = scenarios._past_betas(tampered[["A", "B"]], tampered[OIL], cut, window=260, min_history=104)
    pd.testing.assert_series_equal(before, after)


def test_scenario_table_maps_beta_to_expected_move(world):
    weekly = world.resample("W-FRI").sum()
    frame = weekly[[MARKET, "A", "B"]]
    meta = pd.DataFrame({"name": ["Index", "A", "B"], "kind": ["market", "stock", "stock"],
                         "sector": ["", "x", "x"]}, index=[MARKET, "A", "B"])
    table = scenarios.scenario_table(frame, meta, weekly[[MARKET, OIL]], window=260, shocks=[-0.1, 0.1], min_obs=100)
    row = table.loc["A"]
    assert row["exp_+10%"] == pytest.approx(np.expm1(row["beta_oil_total"] * np.log(1.1)))
    assert row["lo_+10%"] < row["exp_+10%"] < row["hi_+10%"]
    assert row["lo_-10%"] < row["exp_-10%"] < row["hi_-10%"] < 0
    assert 0.5 <= table["p_same_sign"].min() and table["p_same_sign"].max() <= 1
    assert table.loc["A", "rank"] == 1 and table.loc["B", "rank"] == 2


def test_out_of_sample_ranking_works_on_impact_but_not_on_drift(rng):
    T, n = 2600, 30
    idx = pd.bdate_range("2008-01-01", periods=T)
    o = pd.Series(rng.standard_t(df=3, size=T) * 0.015, index=idx)
    true_beta = np.linspace(-0.2, 1.0, n)
    stocks = pd.DataFrame(np.outer(o, true_beta) + rng.normal(scale=0.015, size=(T, n)),
                          index=idx, columns=[f"S{i}" for i in range(n)])
    daily = pd.concat([pd.Series(rng.normal(scale=0.01, size=T), index=idx, name=MARKET), o.rename(OIL), stocks], axis=1)
    ev = events.find_events(daily[OIL], 2.5, 250, 11, lead=270, lag=10)
    cars = events.abnormal_returns(daily[stocks.columns], daily[[MARKET, OIL]], ev, (-270, -21),
                                   {"impact": [0, 1], "drift": [2, 10]})
    weekly = daily.resample("W-FRI").sum()
    oos = scenarios.out_of_sample(weekly[stocks.columns], weekly[[MARKET, OIL]], cars, ev,
                                  list(stocks.columns), window=260, min_history=104)
    summary = scenarios.summarise_oos(oos)
    assert summary.loc["spearman_impact", "mean"] > 0.4 and summary.loc["spearman_impact", "p"] < 0.001
    assert abs(summary.loc["spearman_drift", "mean"]) < 0.15


def test_regime_split_recovers_asymmetric_betas(rng):
    T = 4000
    o = rng.normal(scale=0.03, size=T)
    m = rng.normal(scale=0.02, size=T)
    r = 0.8 * m + np.where(o < 0, 0.9, 0.3) * o + rng.normal(scale=0.01, size=T)
    out = regimes.split_beta(r, m, np.where(o < 0, o, 0.0), np.where(o > 0, o, 0.0), ("down", "up"))
    assert out["beta_down"] == pytest.approx(0.9, abs=0.05)
    assert out["beta_up"] == pytest.approx(0.3, abs=0.05)
    assert out["difference"] < 0 and out["p_diff"] < 0.001


def test_volatility_flag_has_no_look_ahead(rng):
    oil = pd.Series(rng.normal(scale=0.03, size=400), index=pd.date_range("2010-01-01", periods=400, freq="W-FRI"))
    base = regimes.high_vol_flag(oil, vol_window=26)
    shocked = oil.copy()
    shocked.iloc[300:] *= 10
    pd.testing.assert_series_equal(base.iloc[:301], regimes.high_vol_flag(shocked, 26).iloc[:301])
    assert base.iloc[:78].isna().all() and base.iloc[100:].notna().all()


def test_pca_finds_the_market_first_and_orients_components(rng):
    T, n = 600, 12
    idx = pd.date_range("2012-01-06", periods=T, freq="W-FRI")
    m, o = rng.normal(scale=0.02, size=T), rng.normal(scale=0.04, size=T)
    oil_loading = np.r_[np.full(6, 0.5), np.full(6, -0.1)]
    stocks = pd.DataFrame(np.outer(m, np.ones(n)) + np.outer(o, oil_loading) + rng.normal(scale=0.01, size=(T, n)),
                          index=idx, columns=[f"S{i}" for i in range(n)])
    out = pca.return_pca(stocks, pd.DataFrame({MARKET: m, OIL: o}, index=idx), n_components=3)
    s = out["summary"]
    assert s.loc["PC1", MARKET] > 0.6 and s.loc["PC2", OIL] > 0.5
    assert s["variance_share"].is_monotonic_decreasing
    assert out["loadings"]["PC2"].iloc[:6].mean() > out["loadings"]["PC2"].iloc[6:].mean()
