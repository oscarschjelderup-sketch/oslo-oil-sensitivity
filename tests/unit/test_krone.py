"""The krone channel: an exact three-way split of the total oil beta, checked against planted answers."""
import numpy as np
import pandas as pd
import pytest

from oilbeta import MARKET, OIL
from oilbeta.analysis import betas, krone

N = 600
PLANTED = {                      # (direct oil beta, market beta, krone beta)
    "USD.OL": (0.50, 1.00, 0.60),      # a dollar earner: gains when the krone weakens
    "NOK.OL": (0.00, 0.80, -0.40),     # loses when the krone weakens
    "FLAT.OL": (0.00, 0.90, 0.00),
}
G_NOK, G_MKT_DIRECT, MKT_KRONE = -0.20, 0.30, 0.10      # krone on oil; index on oil and on the krone


@pytest.fixture
def market(rng):
    oil = rng.standard_t(df=5, size=N) * 0.04
    fx = G_NOK * oil + rng.normal(scale=0.02, size=N)                    # oil up -> krone stronger -> USD/NOK down
    index = G_MKT_DIRECT * oil + MKT_KRONE * fx + rng.normal(scale=0.015, size=N)
    idx = pd.bdate_range("2010-01-08", periods=N, freq="W-FRI")
    factors = pd.DataFrame({MARKET: index, OIL: oil, krone.KRONE: fx}, index=idx)
    stocks = {t: d * oil + bm * index + bk * fx + rng.normal(scale=0.02, size=N) for t, (d, bm, bk) in PLANTED.items()}
    frame = pd.concat([factors[[MARKET]], pd.DataFrame(stocks, index=idx)], axis=1)
    meta = pd.DataFrame([{"unit": MARKET, "name": "Index", "kind": "market", "sector": ""},
                         *[{"unit": t, "name": t, "kind": "stock", "sector": "S"} for t in stocks]]).set_index("unit")
    return frame, meta, factors


def test_the_split_is_exact_and_the_total_is_the_one_factor_beta(market):
    frame, meta, factors = market
    t = krone.krone_table(frame, meta, factors, min_obs=50)
    assert list(t.index) == [MARKET, *PLANTED]
    assert (t["identity_gap"].abs() < 1e-12).all()
    for unit in t.index:
        one_factor = np.polyfit(factors[OIL], frame[unit], 1)[0]
        assert t.loc[unit, "beta_oil_total"] == pytest.approx(one_factor, abs=1e-12)
    assert np.isnan(t.loc[MARKET, "via_market"]) and np.isnan(t.loc[MARKET, "partial_two_factor"])
    assert (t["nobs"] == N).all()


def test_planted_channels_come_back(market):
    frame, meta, factors = market
    t = krone.krone_table(frame, meta, factors, min_obs=50)
    g_mkt = G_MKT_DIRECT + MKT_KRONE * G_NOK                       # the index's own (one-factor) oil beta
    assert t.loc[MARKET, "krone_oil_beta"] == pytest.approx(G_NOK, abs=0.05)
    assert t.loc[MARKET, "direct"] == pytest.approx(G_MKT_DIRECT, abs=0.05)
    assert t.loc[MARKET, "beta_krone"] == pytest.approx(MKT_KRONE, abs=0.1)
    for unit, (d, bm, bk) in PLANTED.items():
        row = t.loc[unit]
        assert row["direct"] == pytest.approx(d, abs=0.06), unit
        assert row["beta_krone"] == pytest.approx(bk, abs=0.12), unit
        assert row["via_market"] == pytest.approx(bm * g_mkt, abs=0.06), unit
        assert row["via_krone"] == pytest.approx(bk * G_NOK, abs=0.04), unit
    assert t.loc["USD.OL", "krone_q"] < 0.05 and t.loc["NOK.OL", "krone_q"] < 0.05
    assert t.loc["FLAT.OL", "krone_q"] > 0.05
    assert t.loc["USD.OL", "via_krone"] < 0 < t.loc["USD.OL", "direct"]     # the krone works against the oil beta


def test_partial_two_factor_matches_the_headline_estimator(market):
    frame, meta, factors = market
    t = krone.krone_table(frame, meta, factors, min_obs=50)
    for unit in PLANTED:
        est = betas.oil_betas(frame[unit].to_numpy(), factors[MARKET].to_numpy(), factors[OIL].to_numpy())
        assert t.loc[unit, "partial_two_factor"] == pytest.approx(est["beta_oil_partial"], abs=1e-10)
        assert t.loc[unit, "beta_oil_total"] == pytest.approx(est["beta_oil_total"], abs=1e-10)


def test_missing_krone_weeks_are_dropped_not_filled(market):
    frame, meta, factors = market
    factors = factors.copy()
    factors.iloc[100:110, factors.columns.get_loc(krone.KRONE)] = np.nan
    t = krone.krone_table(frame, meta, factors, min_obs=50)
    assert (t["nobs"] == N - 10).all()
    assert (t["identity_gap"].abs() < 1e-12).all()
    s = krone.summary(t, factors, recent_weeks=260)
    assert s["weeks"] == N - 10 and s["weeks_without_krone"] == 10


def test_short_histories_are_left_out(market):
    frame, meta, factors = market
    frame = frame.copy()
    frame["NEW.OL"] = np.nan
    frame.iloc[-30:, frame.columns.get_loc("NEW.OL")] = 0.01
    meta = pd.concat([meta, pd.DataFrame([{"unit": "NEW.OL", "name": "New", "kind": "stock", "sector": "S"}]).set_index("unit")])
    t = krone.krone_table(frame, meta, factors, min_obs=50)
    assert "NEW.OL" not in t.index


def test_summary_reports_the_extremes_and_the_recent_window(market):
    frame, meta, factors = market
    t = krone.krone_table(frame, meta, factors, min_obs=50)
    s = krone.summary(t, factors, recent_weeks=260)
    assert s["weeks"] == N and s["weeks_without_krone"] == 0 and s["recent_weeks"] == 260
    assert s["krone_oil_beta"] == pytest.approx(G_NOK, abs=0.05) and s["krone_oil_corr"] < 0
    assert s["index_total"] == pytest.approx(t.loc[MARKET, "beta_oil_total"])
    assert s["index_via_krone"] == pytest.approx(MKT_KRONE * G_NOK, abs=0.03)
    assert s["recent_krone_oil_beta"] == pytest.approx(G_NOK, abs=0.08)
    assert s["max_stock"]["unit"] == "USD.OL" and s["max_sector"] is None       # no sectors in this fixture
    assert {x["unit"] for x in s["krone_significant"]} == {"USD.OL", "NOK.OL"} and s["n_krone_significant"] == 2
    assert [x["unit"] for x in s["krone_significant"]] == ["NOK.OL", "USD.OL"]  # sorted by krone beta
    assert s["n_direct_positive"] == 1                                            # only the dollar earner has direct oil risk
    assert np.isnan(s["max_sector_partial_shift"]) and s["max_identity_gap"] < 1e-12


def test_rolling_krone_oil_beta_tracks_the_planted_slope(market):
    _, _, factors = market
    roll = krone.rolling_krone_oil_beta(factors, window=104, min_obs=78)
    assert len(roll) == N - 104 + 1 and roll["date"].iloc[-1] == factors.index[-1]
    assert (roll["nobs"] == 104).all()
    assert roll["krone_oil_beta"].mean() == pytest.approx(G_NOK, abs=0.05)
    assert ((roll["lo"] < roll["krone_oil_beta"]) & (roll["krone_oil_beta"] < roll["hi"])).all()
    assert ((roll["lo"] < G_NOK) & (G_NOK < roll["hi"])).mean() > 0.85          # the band covers the truth most of the time
