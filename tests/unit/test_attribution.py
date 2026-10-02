"""The split of a day's move, the range of a unit's own news, and when the oil beta's ranking carries information."""
import numpy as np
import pandas as pd
import pytest

from oilbeta import MARKET, OIL
from oilbeta.analysis import attribution

N_STOCKS, GAMMA, MKT_BETA, OWN_SD = 20, 0.25, 1.0, 0.015
OIL_BETAS = np.linspace(-0.3, 0.6, N_STOCKS)                 # direct oil betas, spread so the stocks can be ranked
TICKERS = [f"S{i:02d}.OL" for i in range(N_STOCKS)]
WINDOW, MIN_HISTORY, VOL_WINDOW = 260, 104, 250


@pytest.fixture
def market(rng):
    days = pd.bdate_range("2012-01-02", "2024-12-27", name="Date")
    n = len(days)
    oil = rng.standard_t(df=4, size=n) * 0.017               # fat tails: quiet days and shock days both occur
    index = GAMMA * oil + rng.normal(scale=0.008, size=n)
    cols = {MARKET: index, OIL: oil}
    for ticker, b in zip(TICKERS, OIL_BETAS):
        cols[ticker] = MKT_BETA * index + b * oil + rng.normal(scale=OWN_SD, size=n)
    daily = pd.DataFrame(cols, index=days)
    weekly = daily.resample("W-FRI").sum()                   # log returns add up within the week
    meta = pd.DataFrame([{"unit": MARKET, "name": "Index", "kind": "market", "sector": ""},
                         *[{"unit": t, "name": t, "kind": "stock", "sector": "S"} for t in TICKERS]]).set_index("unit")
    return daily, weekly, meta


def inputs(market):
    daily, weekly, meta = market
    units = [MARKET, *TICKERS]
    return attribution.unit_inputs(weekly[units], daily[units], meta, weekly[[MARKET, OIL]], daily[[MARKET, OIL]],
                                   WINDOW, min_obs=156)


def rank_days(daily, weekly, **kw):
    return attribution.daily_rank_correlation(weekly[TICKERS], daily[TICKERS], weekly[OIL], daily[OIL],
                                              WINDOW, MIN_HISTORY, VOL_WINDOW, **kw)


def test_unit_inputs_recover_the_planted_betas(market):
    t = inputs(market)
    assert list(t.index) == [MARKET, *TICKERS]
    # 260 weeks of fat-tailed oil: standard errors are about 0.02 (index), 0.04 (oil beta) and 0.12 (market beta)
    assert t.loc[MARKET, "beta_oil_total"] == pytest.approx(GAMMA, abs=0.08) and np.isnan(t.loc[MARKET, "beta_oil_partial"])
    stocks = t.loc[TICKERS]
    assert stocks["beta_oil_partial"].to_numpy() == pytest.approx(OIL_BETAS, abs=0.15)
    assert stocks["beta_mkt"].median() == pytest.approx(MKT_BETA, abs=0.10) and (stocks["beta_mkt"] - MKT_BETA).abs().max() < 0.5
    assert np.corrcoef(stocks["beta_oil_partial"], OIL_BETAS)[0, 1] > 0.97     # and the ranking comes back
    assert (stocks["r2_two"] > stocks["r2_oil"]).all()                      # the index always adds explanation
    # the two ways of writing the split agree: total * x + b_mkt * (m - gamma * x) == partial * x + b_mkt * m
    gap = stocks["beta_oil_total"] - stocks["beta_mkt"] * stocks["market_oil_beta"] - stocks["beta_oil_partial"]
    assert gap.abs().max() < 1e-12
    assert stocks["market_oil_beta"].to_numpy() == pytest.approx(t.loc[MARKET, "beta_oil_total"], abs=1e-12)


def test_the_range_covers_the_stated_share_of_days(market):
    daily, weekly, _ = market
    t = inputs(market)
    first_day = weekly.index[-WINDOW] - pd.Timedelta(days=7)
    d = daily.loc[daily.index > first_day]
    assert (t["nobs_days"] == len(d)).all() and len(d) == pytest.approx(WINDOW * 5, abs=10)
    for unit in (MARKET, TICKERS[0], TICKERS[-1]):
        r = t.loc[unit]
        own = d[unit] - r["beta_oil_total"] * d[OIL] if unit == MARKET else d[unit] - r["beta_mkt"] * d[MARKET] - r["beta_oil_partial"] * d[OIL]
        assert ((own >= r["own_lo"]) & (own <= r["own_hi"])).mean() == pytest.approx(0.80, abs=0.005), unit
        assert r["own_lo"] < 0 < r["own_hi"] and r["coverage"] == 0.80
    # 80% of a normal distribution lies within 1.28 standard deviations
    assert t.loc[TICKERS, "own_hi"].median() == pytest.approx(1.2816 * OWN_SD, rel=0.10)
    assert t.loc[MARKET, "own_hi"] < t.loc[TICKERS, "own_hi"].min()         # the index has the least news of its own


def test_a_wider_coverage_gives_a_wider_range(market):
    daily, weekly, meta = market
    units = [MARKET, *TICKERS[:3]]
    args = (weekly[units], daily[units], meta, weekly[[MARKET, OIL]], daily[[MARKET, OIL]], WINDOW, 156)
    narrow, wide = attribution.unit_inputs(*args, coverage=0.50), attribution.unit_inputs(*args, coverage=0.95)
    assert (wide["own_hi"] > narrow["own_hi"]).all() and (wide["own_lo"] < narrow["own_lo"]).all()


def test_the_ranking_works_better_the_further_oil_moves(market):
    daily, weekly, _ = market
    days = rank_days(daily, weekly)
    sig = attribution.signal_by_size(days)
    assert list(sig.index) == ["under 0.5", "0.5 to 1", "1 to 1.5", "1.5 to 2.5", "2.5 or more"]
    assert sig["n_days"].sum() == len(days) and (sig["n_days"] > 20).all()
    corr = sig["mean_rank_corr"].to_numpy()
    assert (np.diff(corr) > 0).all()                                        # monotone in the size of the move
    assert corr[0] < 0.15 and corr[-1] > 0.6
    assert sig["share_positive"].iloc[-1] > 0.95 > sig["share_positive"].iloc[0]
    assert (np.diff(sig["mean_abs_oil"].to_numpy()) > 0).all()
    # the first scored day is the Monday after the first MIN_HISTORY weeks have ended, not a day earlier
    assert weekly.index[MIN_HISTORY - 1] < days.index.min() <= weekly.index[MIN_HISTORY]


def test_betas_and_volatility_use_only_the_past(market):
    daily, weekly, _ = market
    cut = pd.Timestamp("2020-06-05")                                        # a Friday
    before = rank_days(daily, weekly)
    tampered_d, tampered_w = daily.copy(), weekly.copy()
    tampered_d.loc[tampered_d.index > cut] *= -7.0                          # rewrite the future
    tampered_w.loc[tampered_w.index > cut] *= -7.0
    after = rank_days(tampered_d, tampered_w)
    pd.testing.assert_frame_equal(before.loc[:cut], after.loc[:cut])
    assert not before.loc[cut + pd.Timedelta(days=30):].equals(after.loc[cut + pd.Timedelta(days=30):])

    # the row labelled with a Friday holds betas from weeks that ended before that week began
    betas = attribution.past_betas(weekly[TICKERS], weekly[OIL], WINDOW, MIN_HISTORY)
    changed = weekly.copy()
    changed.loc[cut, TICKERS] += 0.5                                        # change that week's own returns
    betas_changed = attribution.past_betas(changed[TICKERS], changed[OIL], WINDOW, MIN_HISTORY)
    pd.testing.assert_series_equal(betas.loc[cut], betas_changed.loc[cut])
    assert not betas.loc[cut + pd.Timedelta(weeks=1)].equals(betas_changed.loc[cut + pd.Timedelta(weeks=1)])


def test_too_few_stocks_or_no_history_scores_nothing(market):
    daily, weekly, _ = market
    assert rank_days(daily, weekly, min_stocks=N_STOCKS + 1).empty
    empty = attribution.signal_by_size(rank_days(daily, weekly, min_stocks=N_STOCKS + 1))
    assert (empty["n_days"] == 0).all() and empty["mean_rank_corr"].isna().all()


def test_summary_has_what_the_page_and_the_report_quote(market):
    daily, weekly, _ = market
    t, days = inputs(market), rank_days(daily, weekly)
    sig = attribution.signal_by_size(days)
    s = attribution.summary(t, sig, days, daily[OIL], VOL_WINDOW)
    assert s["coverage"] == 0.80 and s["gamma"] == pytest.approx(t.loc[MARKET, "beta_oil_total"])
    assert s["oil_daily_vol"] == pytest.approx(daily[OIL].iloc[-VOL_WINDOW:].std(), rel=1e-9)
    assert 0 < s["median_r2_oil"] < s["median_r2_two"] < 1
    assert s["signal_days"] == len(days) and s["signal_since"] == str(days.index.min().date())
    assert [row["label"] for row in s["signal"]] == list(sig.index) and s["signal"][-1]["hi"] is None
    assert all(ord(ch) < 128 for row in s["signal"] for ch in row["label"])   # labels survive any console or CSV reader
