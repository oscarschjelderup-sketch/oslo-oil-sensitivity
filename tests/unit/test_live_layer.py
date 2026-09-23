"""The 15-minute quotes document and the daily candles: built from synthetic bars, no network."""
import json
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from conftest import study_dict
from oilbeta.config import Config
from oilbeta.outputs import candles, quotes

OSLO = ZoneInfo("Europe/Oslo")


@pytest.fixture
def cfg(tmp_path):
    study = study_dict()
    universe = {"Energy": {"AAA.OL": "Alpha", "BBB.OL": "Beta"}, "Fish": {"CCC.OL": "Gamma"}}
    return Config.from_dicts(study, universe, None, tmp_path).as_live(today=datetime(2026, 9, 23).date())


def session_bars(day: str, closes: list[float], tz=OSLO) -> pd.DataFrame:
    """15-minute bars for one Oslo session, 09:00 onwards, indexed in UTC."""
    start = pd.Timestamp(f"{day} 09:00", tz=tz)
    idx = pd.date_range(start, periods=len(closes), freq="15min").tz_convert("UTC")
    c = np.asarray(closes, dtype=float)
    return pd.DataFrame({"Open": c * 0.999, "High": c * 1.002, "Low": c * 0.998, "Close": c, "Volume": 1000}, index=idx)


def oil_bars(closes_by_hour: dict[str, float]) -> pd.DataFrame:
    idx = pd.DatetimeIndex([pd.Timestamp(t, tz="UTC") for t in closes_by_hour])
    c = np.array(list(closes_by_hour.values()), dtype=float)
    return pd.DataFrame({"Open": c, "High": c * 1.001, "Low": c * 0.999, "Close": c, "Volume": 10}, index=idx)


@pytest.fixture
def market(cfg):
    """Monday 21 Sep: full session closing at 100. Tuesday 22 Sep: open, last bar 11:45, index at 102."""
    index = pd.concat([session_bars("2026-09-21", [99, 99.5, 100.0] + [100.0] * 26),      # 09:00 .. 15:30 -> 16:15 with 29 bars
                       session_bars("2026-09-22", [101, 101.5, 102.0] + [102.0] * 9)])     # 09:00 .. 11:45
    aaa = pd.concat([session_bars("2026-09-21", [50] * 29), session_bars("2026-09-22", [51] * 12)])
    bbb = pd.concat([session_bars("2026-09-21", [20] * 29), session_bars("2026-09-22", [19] * 12)])
    ccc = session_bars("2026-09-21", [5] * 29)                                            # no trade yet today
    # Brent: 90 at Oslo's Monday close (14:15 UTC), drifts to 95 overnight, 99 by Tuesday noon
    brent = oil_bars({"2026-09-21 10:00": 88, "2026-09-21 14:00": 90, "2026-09-21 14:15": 90, "2026-09-21 20:00": 95,
                      "2026-09-22 06:00": 97, "2026-09-22 09:45": 99})
    fx = oil_bars({"2026-09-21 14:00": 10.5, "2026-09-22 09:45": 10.6})
    return {cfg.market.late_ticker: index, "AAA.OL": aaa, "BBB.OL": bbb, "CCC.OL": ccc, cfg.oil_ticker: brent, "NOK=X": fx}


def test_every_move_is_measured_from_oslos_previous_close(cfg, market):
    now = datetime(2026, 9, 22, 10, 5, tzinfo=UTC)                     # 12:05 Oslo, market open
    doc = quotes.build(cfg, market, now=now)
    s = doc["session"]
    assert s["date"] == "2026-09-22" and s["previous_date"] == "2026-09-21"
    assert s["previous_close_at"] == "2026-09-21T14:00+00:00"          # 16:00 Oslo bar, the last one before Tuesday
    assert s["market_open"] and s["trading_day"] and not s["stale"]
    assert doc["index"]["prev_close"] == 100.0 and doc["index"]["last"] == 102.0
    assert doc["index"]["change"] == pytest.approx(0.02)
    assert doc["stocks"]["AAA.OL"]["change"] == pytest.approx(0.02)
    assert doc["stocks"]["BBB.OL"]["change"] == pytest.approx(-0.05)
    # Brent's move over the SAME window: from its price at Oslo's close (90) to now (99)
    assert doc["brent"]["prev_close"] == 90.0 and doc["brent"]["change"] == pytest.approx(0.1)
    assert doc["brent"]["prev_close_at"] == "2026-09-21T14:00+00:00"
    assert doc["usdnok"]["change"] == pytest.approx(10.6 / 10.5 - 1, abs=1e-5)   # rounded to five decimals


def test_a_stock_that_has_not_traded_today_keeps_yesterdays_print_and_no_change(cfg, market):
    doc = quotes.build(cfg, market, now=datetime(2026, 9, 22, 10, 5, tzinfo=UTC))
    ccc = doc["stocks"]["CCC.OL"]
    assert ccc["last"] == 5.0 and ccc["last_at"].startswith("2026-09-21")
    assert ccc["change"] == pytest.approx(0.0)                          # its last print IS the previous close
    assert doc["coverage"] == {"stocks_with_quotes": 3, "stocks_in_universe": 3}


def test_bars_are_local_wall_clock_epochs_for_the_chart(cfg, market):
    doc = quotes.build(cfg, market, now=datetime(2026, 9, 22, 10, 5, tzinfo=UTC))
    first = doc["index"]["bars"][0]
    assert datetime.fromtimestamp(first[0], tz=UTC).strftime("%Y-%m-%d %H:%M") == "2026-09-21 09:00"   # Oslo time, as UTC
    assert len(first) == 6 and first[4] == 99.0 and first[5] == 1000
    assert len(doc["index"]["bars"]) == 41 and doc["index"]["session_high"] == pytest.approx(102 * 1.002)
    assert "bars" not in doc["stocks"]["AAA.OL"]                        # stocks carry a quote, not a chart


def test_closed_market_and_stale_data_are_flagged_not_hidden(cfg, market):
    evening = quotes.build(cfg, market, now=datetime(2026, 9, 22, 18, 0, tzinfo=UTC))
    assert not evening["session"]["market_open"] and not evening["session"]["stale"]
    weekend = quotes.build(cfg, market, now=datetime(2026, 9, 26, 10, 0, tzinfo=UTC))
    assert not weekend["session"]["trading_day"] and not weekend["session"]["market_open"]
    late = quotes.build(cfg, market, now=datetime(2026, 9, 22, 12, 0, tzinfo=UTC))    # 14:00 Oslo, last bar 11:45
    assert late["session"]["market_open"] and late["session"]["stale"] and late["session"]["age_minutes"] == pytest.approx(135)


def test_a_failed_refresh_republishes_the_previous_document_as_stale(cfg, market, tmp_path):
    doc = quotes.build(cfg, market, now=datetime(2026, 9, 22, 10, 5, tzinfo=UTC))
    path = quotes.write(doc, tmp_path / "q" / "quotes.json")
    previous = quotes.load(path)
    later = datetime(2026, 9, 22, 11, 0, tzinfo=UTC)
    stale = quotes.mark_stale(previous, now=later, reason="Yahoo throttled")
    assert stale["session"]["stale"] and stale["session"]["stale_reason"] == "Yahoo throttled"
    assert stale["session"]["age_minutes"] == pytest.approx(75) and stale["session"]["market_open"]
    assert stale["brent"] == doc["brent"] and stale["refreshed_utc"].startswith("2026-09-22T11:00")
    assert quotes.load(tmp_path / "missing.json") is None
    (tmp_path / "broken.json").write_text("{", encoding="utf-8")
    assert quotes.load(tmp_path / "broken.json") is None


def test_no_index_bars_is_an_error_not_a_silent_document(cfg, market):
    with pytest.raises(ValueError, match="no intraday bars for the index"):
        quotes.build(cfg, {k: v for k, v in market.items() if k != cfg.market.late_ticker})


def test_next_session_window_skips_the_weekend():
    start, end = quotes.next_session_window(datetime(2026, 9, 25, 16, 0, tzinfo=UTC))   # Friday evening
    assert start.astimezone(OSLO).strftime("%a %H:%M") == "Mon 09:00" and end > start
    start, _ = quotes.next_session_window(datetime(2026, 9, 22, 8, 0, tzinfo=UTC))      # Tuesday morning
    assert start.astimezone(OSLO).strftime("%a %H:%M") == "Tue 09:00"


# --------------------------------------------------------------------------- candles
def test_candles_are_compact_named_and_free_of_gaps(cfg, tmp_path):
    days = pd.bdate_range("2026-03-01", "2026-09-22")
    c = 100 + np.cumsum(np.random.default_rng(1).normal(size=len(days)))
    frame = pd.DataFrame({"Open": c, "High": c + 1, "Low": c - 1, "Close": c, "Volume": 1}, index=days)
    frame.iloc[10, frame.columns.get_loc("Close")] = np.nan                       # a missing day is dropped, not zeroed
    doc = candles.build(cfg, {"AAA.OL": frame, cfg.oil_ticker: frame * 0.9, "ZZZ.OL": frame}, now=datetime(2026, 9, 23, tzinfo=UTC))
    assert doc["schema"] == "oilbeta.candles/1" and doc["through"] == "2026-09-22"
    assert set(doc["series"]) == {"AAA.OL", cfg.oil_ticker}                      # ZZZ.OL is not in the config: left out
    aaa = doc["series"]["AAA.OL"]
    assert aaa["name"] == "Alpha" and aaa["sector"] == "Energy"
    assert len(aaa["bars"]) == len(days) - 1 and all(len(b) == 5 for b in aaa["bars"])
    assert aaa["bars"][0][0] == "2026-03-02" and all(b[2] >= b[3] for b in aaa["bars"])
    assert doc["series"][cfg.oil_ticker]["name"] == cfg.study.factors.oil.name
    path = candles.write(doc, tmp_path / "c" / "candles.json")
    assert json.loads(path.read_text(encoding="utf-8")) == doc
    assert path.stat().st_size < 30_000                                             # two series, six months


# --------------------------------------------------------------------------- the refresh loop's tick schedule
def oslo(y, mo, d, h, mi, s=0):
    return datetime(y, mo, d, h, mi, s, tzinfo=OSLO)


@pytest.mark.parametrize("now, expected", [
    (oslo(2026, 9, 22, 7, 30), oslo(2026, 9, 22, 9, 1)),        # before the open: wait for the first tick
    (oslo(2026, 9, 22, 9, 5), oslo(2026, 9, 22, 9, 16)),        # between ticks
    (oslo(2026, 9, 22, 9, 15, 30), oslo(2026, 9, 22, 9, 16)),   # just before one
    (oslo(2026, 9, 22, 9, 16), oslo(2026, 9, 22, 9, 31)),       # exactly on one: it was just done, move on
    (oslo(2026, 9, 22, 16, 40), oslo(2026, 9, 22, 16, 46)),     # the delayed closing-auction bar
])
def test_ticks_fall_one_minute_after_each_quarter_hour(now, expected):
    assert quotes.next_tick(now) == expected


@pytest.mark.parametrize("now", [
    oslo(2026, 9, 22, 16, 46, 1),                                # after the last tick
    oslo(2026, 9, 26, 12, 0),                                    # Saturday
    oslo(2026, 9, 27, 10, 0),                                    # Sunday
])
def test_no_tick_when_the_session_is_over(now):
    assert quotes.next_tick(now) is None


def test_ticks_follow_oslo_wall_clock_across_the_switch_to_winter_time():
    """After 25 Oct 2026 Oslo is UTC+1: 09:16 Oslo is 08:16 UTC, not 07:16."""
    winter = datetime(2026, 11, 3, 8, 5, tzinfo=UTC)             # 09:05 Oslo
    assert quotes.next_tick(winter).astimezone(UTC) == datetime(2026, 11, 3, 8, 16, tzinfo=UTC)
    summer = datetime(2026, 9, 22, 7, 5, tzinfo=UTC)             # 09:05 Oslo
    assert quotes.next_tick(summer).astimezone(UTC) == datetime(2026, 9, 22, 7, 16, tzinfo=UTC)


def doc(session_date, fetched_oslo, **session):
    return {"generated_utc": fetched_oslo.astimezone(UTC).isoformat(), "session": {"date": session_date, **session}}


def test_a_holiday_ends_the_loop_but_a_throttled_or_old_document_does_not():
    now = oslo(2026, 9, 22, 11, 0)
    holiday = doc("2026-09-21", oslo(2026, 9, 22, 10, 46))                 # fetched today, late enough, no bars today
    assert quotes.next_tick(now, holiday) is None
    early = doc("2026-09-21", oslo(2026, 9, 22, 9, 31))                    # fetched before 10:30: too early to tell
    assert quotes.next_tick(now, early) == oslo(2026, 9, 22, 11, 1)
    throttled = doc("2026-09-21", oslo(2026, 9, 22, 10, 46), stale_reason="refresh failed: 429")
    assert quotes.next_tick(now, throttled) == oslo(2026, 9, 22, 11, 1)    # a failed download proves nothing
    todays = doc("2026-09-22", oslo(2026, 9, 22, 10, 46))
    assert quotes.next_tick(now, todays) == oslo(2026, 9, 22, 11, 1)


def test_yesterdays_document_says_nothing_about_today():
    """The regression that was caught by hand: the loop starts mid-session holding yesterday's document."""
    last_night = doc("2026-09-22", oslo(2026, 9, 22, 23, 11))
    assert quotes.next_tick(oslo(2026, 9, 23, 14, 10), last_night) == oslo(2026, 9, 23, 14, 16)
    assert quotes.next_tick(oslo(2026, 9, 23, 14, 10), {"session": {"date": "2026-09-22"}}) == oslo(2026, 9, 23, 14, 16)
