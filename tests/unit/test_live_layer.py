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


def test_brents_move_for_the_split_stops_where_oslo_stopped(cfg, market):
    during = quotes.build(cfg, market, now=datetime(2026, 9, 22, 10, 5, tzinfo=UTC))
    b = during["brent"]
    assert b["change_oslo"] == b["change"] and b["last_oslo"] == 99.0          # no later Brent bar yet: one and the same
    assert b["last_oslo_at"] == "2026-09-22T09:45+00:00" == during["session"]["latest_bar"]
    assert "change_oslo" not in during["index"] and "change_oslo" not in during["stocks"]["AAA.OL"]

    # the evening after: Oslo's last bar is still 11:45, Brent has fallen back to 93 and USD/NOK has moved on
    late = dict(market)
    late[cfg.oil_ticker] = pd.concat([market[cfg.oil_ticker], oil_bars({"2026-09-22 16:00": 96, "2026-09-22 19:00": 93})])
    late["NOK=X"] = pd.concat([market["NOK=X"], oil_bars({"2026-09-22 19:00": 10.4})])
    evening = quotes.build(cfg, late, now=datetime(2026, 9, 22, 19, 30, tzinfo=UTC))
    b, fx = evening["brent"], evening["usdnok"]
    assert b["last"] == 93.0 and b["change"] == pytest.approx(93 / 90 - 1, abs=1e-5)       # the live move runs on
    assert b["last_oslo"] == 99.0 and b["change_oslo"] == pytest.approx(0.1)               # the stocks saw +10%
    assert b["last_oslo_at"] == "2026-09-22T09:45+00:00"
    assert fx["change"] == pytest.approx(10.4 / 10.5 - 1, abs=1e-5) and fx["change_oslo"] == pytest.approx(10.6 / 10.5 - 1, abs=1e-5)
    assert evening["stocks"]["AAA.OL"]["change"] == during["stocks"]["AAA.OL"]["change"]    # and the stocks did not move


def daily_bars(closes_by_day: dict[str, float]) -> pd.DataFrame:
    """Daily bars as the vendor returns them: one row per session, stamped at UTC midnight."""
    idx = pd.DatetimeIndex([pd.Timestamp(d, tz="UTC") for d in closes_by_day])
    c = np.array(list(closes_by_day.values()), dtype=float)
    return pd.DataFrame({"Open": c, "High": c, "Low": c, "Close": c, "Volume": 5000}, index=idx)


@pytest.fixture
def official(cfg):
    """Official closes: the closing auction moved every price away from the last 15-minute bar."""
    return {cfg.market.late_ticker: daily_bars({"2026-09-21": 100.5, "2026-09-22": 103.0}),
            "AAA.OL": daily_bars({"2026-09-21": 50.5, "2026-09-22": 52.0}),
            "BBB.OL": daily_bars({"2026-09-21": 20.0}),                      # no daily bar for Tuesday
            "CCC.OL": daily_bars({"2026-09-21": 5.1})}


def test_the_reference_is_the_official_close_not_the_last_bar(cfg, market, official):
    doc = quotes.build(cfg, market, now=datetime(2026, 9, 22, 10, 5, tzinfo=UTC), daily=official)   # 12:05 Oslo
    s, c = doc["session"], doc["coverage"]
    assert s["previous_close_basis"] == "official close" and s["last_basis"] == "last 15-minute bar" and not s["session_over"]
    assert doc["index"]["prev_close"] == 100.5 and doc["index"]["prev_close_at"] == "2026-09-21T14:25+00:00"   # 16:25 Oslo
    assert doc["index"]["last"] == 102.0 and doc["index"]["change"] == pytest.approx(102 / 100.5 - 1, abs=1e-5)
    assert doc["stocks"]["AAA.OL"]["change"] == pytest.approx(51 / 50.5 - 1, abs=1e-5)
    assert doc["stocks"]["BBB.OL"]["change"] == pytest.approx(19 / 20 - 1, abs=1e-5)
    # a stock with no print today stands at its official close with no move, not at the gap to its last bar
    ccc = doc["stocks"]["CCC.OL"]
    assert ccc["last"] == 5.1 and ccc["change"] == pytest.approx(0.0) and ccc["last_at"] == "2026-09-21T14:25+00:00"
    assert c["official_previous_close"] == 3 and c["official_last"] == 0 and c["carried_forward"] == []
    assert c["reference_from_published"] == []
    assert {(s["prev_close_basis"], s["last_basis"]) for s in doc["stocks"].values()} == {("official close", "last 15-minute bar")}
    assert "prev_close_basis" not in doc["brent"]                       # Brent has no auction and no basis to state
    # Brent has no auction: still measured from its bar at Oslo's close
    assert doc["brent"]["prev_close"] == 90.0 and doc["brent"]["change"] == pytest.approx(0.1)
    # without daily bars the document falls back to the last bars and says so
    plain = quotes.build(cfg, market, now=datetime(2026, 9, 22, 10, 5, tzinfo=UTC))
    assert plain["session"]["previous_close_basis"] == "last 15-minute bar" and plain["coverage"]["official_previous_close"] == 0
    assert plain["index"]["prev_close"] == 100.0


def test_once_the_session_is_over_the_last_price_is_the_official_close(cfg, market, official):
    before = quotes.build(cfg, market, now=datetime(2026, 9, 22, 14, 30, tzinfo=UTC), daily=official)    # 16:30 Oslo
    assert before["index"]["last"] == 102.0 and before["session"]["last_basis"] == "last 15-minute bar"
    after = quotes.build(cfg, market, now=datetime(2026, 9, 22, 14, 50, tzinfo=UTC), daily=official)     # 16:50 Oslo
    s = after["session"]
    assert s["session_over"] and s["last_basis"] == "official close" and not s["market_open"]
    assert after["index"]["last"] == 103.0 and after["index"]["last_at"] == "2026-09-22T14:25+00:00"
    assert after["index"]["change"] == pytest.approx(103 / 100.5 - 1, abs=1e-5)
    assert after["stocks"]["AAA.OL"]["last"] == 52.0
    assert after["stocks"]["AAA.OL"]["change"] == pytest.approx(52 / 50.5 - 1, abs=1e-5)
    assert after["stocks"]["BBB.OL"]["last"] == 19.0                     # no daily bar yet: its last 15-minute bar stands
    assert after["coverage"]["official_last"] == 1 and after["coverage"]["official_previous_close"] == 3
    assert s["latest_bar"] == before["session"]["latest_bar"]            # Brent stays aligned to Oslo's last bar
    assert after["brent"]["change_oslo"] == before["brent"]["change_oslo"]
    weekend = quotes.build(cfg, market, now=datetime(2026, 9, 26, 10, 0, tzinfo=UTC), daily=official)
    assert weekend["index"]["last"] == 103.0 and weekend["session"]["session_over"]
    # if the daily bars then fail, the published official closes stay: nothing falls back to an earlier price
    no_daily = quotes.build(cfg, market, now=datetime(2026, 9, 22, 15, 5, tzinfo=UTC), previous=after)
    assert no_daily["index"] == after["index"] and no_daily["session"]["last_basis"] == "official close"
    assert no_daily["stocks"]["AAA.OL"] == after["stocks"]["AAA.OL"]
    assert set(no_daily["coverage"]["carried_forward"]) == {"index", "AAA.OL"}
    # and the references stay official too, taken from the document already published for this session
    assert {t: s["prev_close"] for t, s in no_daily["stocks"].items()} == {t: s["prev_close"] for t, s in after["stocks"].items()}
    assert no_daily["coverage"]["official_previous_close"] == 3 and no_daily["coverage"]["reference_from_published"] == ["BBB.OL", "CCC.OL"]
    assert no_daily["coverage"]["official_last"] == 1                    # the carried official close still counts as one


def test_a_carried_official_close_stays_counted_as_official(cfg, market, official):
    """5 October 2026, 20:50 Oslo: one stock's daily bars failed to download ('database is locked'), the guard kept its
    published official close, and the document reported 62 official closes out of 63 that were all official."""
    after = quotes.build(cfg, market, now=datetime(2026, 9, 22, 14, 50, tzinfo=UTC), daily=official)
    lost = {t: f for t, f in official.items() if t != "AAA.OL"}           # the failed download
    again = quotes.build(cfg, market, now=datetime(2026, 9, 22, 18, 50, tzinfo=UTC), daily=lost, previous=after)
    assert again["coverage"]["carried_forward"] == ["AAA.OL"] and again["stocks"]["AAA.OL"] == after["stocks"]["AAA.OL"]
    assert again["stocks"]["AAA.OL"]["last_basis"] == "official close"
    assert again["coverage"]["official_last"] == after["coverage"]["official_last"] == 1
    assert again["coverage"]["official_previous_close"] == after["coverage"]["official_previous_close"] == 3


def test_the_reference_survives_a_blank_daily_bar_overnight(cfg, market, official):
    """After midnight Oslo time Yahoo blanks the last session's daily bar for some hours (measured 5-6 October 2026).
    The next morning's reference must still be the official close that was published the evening before."""
    monday = {k: v.loc[v.index < pd.Timestamp("2026-09-22", tz="UTC")] for k, v in market.items()}
    evening = quotes.build(cfg, monday, now=datetime(2026, 9, 21, 15, 0, tzinfo=UTC), daily=official)    # 17:00 Oslo
    assert evening["session"]["date"] == "2026-09-21" and evening["index"]["last"] == 100.5
    assert evening["index"]["last_basis"] == "official close" and evening["stocks"]["AAA.OL"]["last"] == 50.5

    blank = {t: f.loc[f.index != pd.Timestamp("2026-09-21", tz="UTC")] for t, f in official.items()}   # Monday's row gone
    with_daily = quotes.build(cfg, market, now=datetime(2026, 9, 22, 10, 5, tzinfo=UTC), daily=official)
    morning = quotes.build(cfg, market, now=datetime(2026, 9, 22, 10, 5, tzinfo=UTC), daily=blank, previous=evening)
    for key in ("index", "AAA.OL", "BBB.OL", "CCC.OL"):
        a = morning["index"] if key == "index" else morning["stocks"][key]
        b = with_daily["index"] if key == "index" else with_daily["stocks"][key]
        assert (a["prev_close"], a["prev_close_at"], a["change"], a["prev_close_basis"]) == \
               (b["prev_close"], b["prev_close_at"], b["change"], b["prev_close_basis"]), key
    assert morning["session"]["previous_close_basis"] == "official close"
    assert morning["coverage"]["reference_from_published"] == ["AAA.OL", "BBB.OL", "CCC.OL"]
    # later the same morning the reference comes from the session's own published document
    later = quotes.build(cfg, market, now=datetime(2026, 9, 22, 10, 20, tzinfo=UTC), daily=blank, previous=morning)
    assert later["index"]["prev_close"] == 100.5 and later["coverage"]["official_previous_close"] == 3
    # once Yahoo has the row back, the daily bars take over with the same numbers
    back = quotes.build(cfg, market, now=datetime(2026, 9, 22, 10, 35, tzinfo=UTC), daily=official, previous=later)
    assert back["coverage"]["reference_from_published"] == [] and back["stocks"]["AAA.OL"]["prev_close"] == 50.5

    # a document published before per-series bases existed still hands its official closes on
    old = json.loads(json.dumps(evening))
    for entry in [old["index"], *old["stocks"].values()]:
        entry.pop("prev_close_basis"), entry.pop("last_basis")
    from_old = quotes.build(cfg, market, now=datetime(2026, 9, 22, 10, 5, tzinfo=UTC), daily=blank, previous=old)
    assert from_old["index"]["prev_close"] == 100.5 and from_old["coverage"]["official_previous_close"] == 3

    # but a document from an unrelated session proves nothing: back to the last 15-minute bar, and said so
    stray = json.loads(json.dumps(evening))
    stray["session"]["date"] = "2026-09-18"
    unrelated = quotes.build(cfg, market, now=datetime(2026, 9, 22, 10, 5, tzinfo=UTC), daily=blank, previous=stray)
    assert unrelated["index"]["prev_close"] == 100.0 and unrelated["session"]["previous_close_basis"] == "last 15-minute bar"


def test_tickers_missing_from_the_parallel_download_are_fetched_once_more(monkeypatch):
    """yfinance's parallel download dropped one ticker in production ('database is locked'); retry it alone."""
    import yfinance

    from oilbeta.data import intraday

    def frame(tickers):
        idx = pd.date_range("2026-10-05 07:00", periods=3, freq="15min", tz="UTC")
        cols = pd.MultiIndex.from_product([tickers, ["Open", "High", "Low", "Close", "Volume"]])
        return pd.DataFrame(1.0, index=idx, columns=cols)

    calls = []

    def fake_download(tickers, threads=True, **kwargs):
        calls.append((list(tickers), threads))
        if threads:                                           # the parallel call loses VEI.OL
            out = frame(list(tickers))
            out.loc[:, ("VEI.OL", "Close")] = np.nan
            return out
        return frame(list(tickers))

    monkeypatch.setattr(yfinance, "download", fake_download)
    bars = intraday.fetch_intraday(["EQNR.OL", "VEI.OL", "OSEBX.OL"])
    assert set(bars) == {"EQNR.OL", "VEI.OL", "OSEBX.OL"} and len(bars["VEI.OL"]) == 3
    assert calls == [(["EQNR.OL", "VEI.OL", "OSEBX.OL"], True), (["VEI.OL"], False)]
    calls.clear()
    daily = intraday.fetch_daily_ohlc(["EQNR.OL", "VEI.OL"], "2026-09-28", "2026-10-05")
    assert set(daily) == {"EQNR.OL", "VEI.OL"} and calls[1] == (["VEI.OL"], False)


def test_a_quote_never_goes_back_in_time(cfg, market):
    published = quotes.build(cfg, market, now=datetime(2026, 9, 22, 10, 5, tzinfo=UTC))
    later = datetime(2026, 9, 22, 10, 20, tzinfo=UTC)
    # the vendor answers with an older view of one stock: its last three bars are gone and the last one left differs
    older = market["AAA.OL"].iloc[:-3].copy()
    older.iloc[-1, older.columns.get_loc("Close")] = 55.0
    stale = {**market, "AAA.OL": older}
    again = quotes.build(cfg, stale, now=later, previous=published)
    assert again["stocks"]["AAA.OL"] == published["stocks"]["AAA.OL"] and again["coverage"]["carried_forward"] == ["AAA.OL"]
    assert again["stocks"]["BBB.OL"] == published["stocks"]["BBB.OL"]
    assert quotes.build(cfg, stale, now=later)["stocks"]["AAA.OL"]["last"] == 55.0      # what would have been published

    # a series missing from the response altogether is carried as well
    missing = {k: v for k, v in market.items() if k != "BBB.OL"}
    again = quotes.build(cfg, missing, now=later, previous=published)
    assert again["stocks"]["BBB.OL"] == published["stocks"]["BBB.OL"] and again["coverage"]["carried_forward"] == ["BBB.OL"]
    assert again["coverage"]["stocks_with_quotes"] == 3

    # Brent is protected the same way
    stale_oil = {**market, cfg.oil_ticker: market[cfg.oil_ticker].iloc[:-1]}
    again = quotes.build(cfg, stale_oil, now=later, previous=published)
    assert again["brent"] == published["brent"] and again["coverage"]["carried_forward"] == ["brent"]

    # a document from another session protects nothing
    yesterday = json.loads(json.dumps(published))
    yesterday["session"]["date"] = "2026-09-21"
    fresh = quotes.build(cfg, stale, now=later, previous=yesterday)
    assert fresh["stocks"]["AAA.OL"]["last"] == 55.0 and fresh["coverage"]["carried_forward"] == []

    # and an index that goes backwards is an error, not a document
    back = {**market, cfg.market.late_ticker: market[cfg.market.late_ticker].iloc[:-2]}
    with pytest.raises(ValueError, match="went back in time"):
        quotes.build(cfg, back, now=later, previous=published)


def test_a_stock_that_has_not_traded_today_keeps_yesterdays_print_and_no_change(cfg, market):
    doc = quotes.build(cfg, market, now=datetime(2026, 9, 22, 10, 5, tzinfo=UTC))
    ccc = doc["stocks"]["CCC.OL"]
    assert ccc["last"] == 5.0 and ccc["last_at"].startswith("2026-09-21")
    assert ccc["change"] == pytest.approx(0.0)                          # its last print IS the previous close
    assert doc["coverage"]["stocks_with_quotes"] == 3 and doc["coverage"]["stocks_in_universe"] == 3


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
    (oslo(2026, 9, 22, 16, 40), oslo(2026, 9, 22, 16, 46)),     # the last continuous bar, delayed
    (oslo(2026, 9, 22, 16, 50), oslo(2026, 9, 22, 17, 1)),      # one more, for the official closing price
])
def test_ticks_fall_one_minute_after_each_quarter_hour(now, expected):
    assert quotes.next_tick(now) == expected


@pytest.mark.parametrize("now", [
    oslo(2026, 9, 22, 17, 1, 1),                                 # after the last tick
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
