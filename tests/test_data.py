import numpy as np
import pandas as pd

from oilbeta import MARKET, OIL, data


def test_oil_return_spans_the_oslo_holiday(mini_cfg, mini_prices):
    """Returns are computed after alignment: the day Oslo is closed is folded into the next return."""
    panel = data.build_panel(mini_prices, mini_cfg)
    assert pd.Timestamp("2020-01-07") not in panel.index
    ret = data.daily_returns(panel)
    got = ret.loc["2020-01-08", OIL]
    assert np.isclose(got, np.log(55 / 53))            # two oil days in one return
    assert np.isclose(ret.loc["2020-01-08", "AAA.OL"], np.log(15 / 13))


def test_market_splice_chains_returns_not_levels(mini_cfg, mini_prices):
    level = data.splice_market(mini_prices, mini_cfg)
    ret = np.log(level).diff().dropna()
    assert np.isclose(ret.loc["2020-01-06"], np.log(103 / 102))   # early index up to the splice date
    assert np.isclose(ret.loc["2020-01-09"], np.log(220 / 210))   # late index afterwards
    assert level.name == MARKET and (level > 0).all()


def test_sector_portfolio_is_equal_weighted_in_simple_returns(mini_cfg):
    idx = pd.date_range("2020-01-03", periods=2, freq="W-FRI")
    ret = pd.DataFrame({"AAA.OL": np.log([1.10, 1.00]), "BBB.OL": np.log([0.90, np.nan]),
                        "CCC.OL": np.log([1.05, 1.02])}, index=idx)
    sectors = data.sector_returns(ret, mini_cfg)
    assert np.isclose(sectors.loc[idx[0], "Energy"], np.log(1.0))   # (+10% and -10%) / 2 = 0%
    assert np.isnan(sectors.loc[idx[1], "Energy"])                  # fewer than two members that week
    assert np.isclose(sectors.loc[idx[0], "Fish"], np.log(1.05))    # single-member sector still reported


def test_documented_exceptions_are_removed_from_daily_and_weekly(mini_cfg, mini_prices):
    mini_cfg.raw["data_exceptions"] = {"drop_returns": [{"ticker": "AAA.OL", "date": "2020-01-03", "reason": "test"}]}
    panel = data.build_panel(mini_prices, mini_cfg)
    daily, weekly = data.daily_returns(panel, mini_cfg), data.weekly_returns(panel, mini_cfg)
    assert np.isnan(daily.loc["2020-01-03", "AAA.OL"])
    assert np.isfinite(daily.loc["2020-01-03", "BBB.OL"])
    assert np.isfinite(data.daily_returns(panel).loc["2020-01-03", "AAA.OL"])   # untouched without cfg
    assert weekly["AAA.OL"].isna().sum() == data.weekly_returns(panel)["AAA.OL"].isna().sum() + 1


def test_history_start_trims_a_ticker(mini_cfg, mini_prices):
    mini_cfg.raw["data_exceptions"] = {"history_start": {"CCC.OL": {"date": "2020-01-06", "reason": "test"}}}
    panel = data.build_panel(mini_prices, mini_cfg)
    assert panel["CCC.OL"].first_valid_index() == pd.Timestamp("2020-01-06")
    assert panel["AAA.OL"].first_valid_index() < pd.Timestamp("2020-01-06")


def test_validation_flags_stale_series(mini_cfg, mini_prices):
    report = data.validate(data.build_panel(mini_prices, mini_cfg), mini_cfg).set_index("series")
    assert "stale prices" in report.loc["BBB.OL", "flags"]
    assert report.loc["AAA.OL", "flags"] == "ok"
