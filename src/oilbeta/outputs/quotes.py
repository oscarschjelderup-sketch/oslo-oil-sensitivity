"""The 15-minute document behind the "Today" panel: where prices are now, relative to Oslo's last close.

One question, answered consistently for every series: *how far has it moved since Oslo Børs
last closed?* That is the window over which the page compares Brent's move with each sector's
move, so both sides are measured over the same hours. Brent trades almost around the clock,
so its "since Oslo close" move can start on the previous evening; the page says so.

The document carries prices, times and a staleness flag - nothing estimated. The betas that
turn a Brent move into a predicted stock move come from the daily study; the page joins the two.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .. import __version__
from ..config import Config
from ..data.intraday import DELAY_MINUTES

SCHEMA = "oilbeta.quotes/1"
OSLO = ZoneInfo("Europe/Oslo")
OPEN, CLOSE = time(9, 0), time(16, 25)          # continuous trading 09:00-16:20, closing auction to 16:25
STALE_AFTER_MINUTES = 45                         # during trading hours; beyond this the page shows a warning
# The refresh loop fetches one minute after each quarter-hour. Free data is delayed 15 minutes by the
# exchange, so the bar that closes at 16:30 (the closing auction) is visible at about 16:45: the last
# tick of the day is 16:46.
FIRST_TICK, LAST_TICK = time(9, 1), time(16, 46)
TICK_EVERY = timedelta(minutes=15)
HOLIDAY_CHECK_AFTER = time(10, 30)               # by then a trading day has published bars


def _bars(frame: pd.DataFrame, tz: ZoneInfo, limit: int | None = None) -> list[list]:
    """[t, o, h, l, c, v] with t = local wall-clock time expressed as a UTC epoch (what a chart library
    needs to draw '09:15' at 09:15 without knowing about time zones)."""
    if limit:
        frame = frame.iloc[-limit:]
    local = frame.index.tz_convert(tz).tz_localize(None)
    epoch = (local - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1)
    rows = []
    for t, (o, h, lo, c, v) in zip(epoch, frame[["Open", "High", "Low", "Close", "Volume"]].itertuples(index=False)):
        if not np.isfinite(c):
            continue
        rows.append([int(t), round(float(o), 4), round(float(h), 4), round(float(lo), 4), round(float(c), 4),
                     int(v) if np.isfinite(v) else 0])
    return rows


def _session_dates(frame: pd.DataFrame, tz: ZoneInfo) -> pd.Index:
    return pd.Index(sorted(set(frame.index.tz_convert(tz).date)))


def _last_close_before(frame: pd.DataFrame, cutoff: pd.Timestamp) -> tuple[float | None, pd.Timestamp | None]:
    before = frame.loc[frame.index <= cutoff]
    if before.empty:
        return None, None
    return float(before["Close"].iloc[-1]), before.index[-1]


def build(cfg: Config, intraday: dict[str, pd.DataFrame], now: datetime | None = None) -> dict:
    """Assemble the quotes document. `intraday` is {ticker: bars with a UTC index}."""
    now = (now or datetime.now(UTC)).astimezone(UTC)
    now_oslo = now.astimezone(OSLO)
    index_t, oil_t, fx_t = cfg.market.late_ticker, cfg.oil_ticker, cfg.context.get("usdnok")
    index = intraday.get(index_t)
    if index is None or index.empty:
        raise ValueError(f"no intraday bars for the index {index_t}")

    # --- the Oslo session everything is measured against ------------------------------------
    sessions = _session_dates(index, OSLO)
    session_date = sessions[-1]
    previous_date = sessions[-2] if len(sessions) > 1 else None
    session_start = pd.Timestamp.combine(session_date, OPEN).tz_localize(OSLO).tz_convert("UTC")
    if previous_date is not None:
        prev_close_at = index.loc[index.index < session_start].index[-1]      # Oslo's last bar before this session
    else:
        prev_close_at = None
    is_trading_day = now_oslo.weekday() < 5
    market_open = (is_trading_day and OPEN <= now_oslo.time() < CLOSE and session_date == now_oslo.date())
    latest_bar = index.index[-1]
    age_minutes = (now - latest_bar.to_pydatetime()).total_seconds() / 60
    stale = market_open and age_minutes > STALE_AFTER_MINUTES

    def snapshot(ticker: str, frame: pd.DataFrame | None, bars: int | None = None, name: str | None = None) -> dict | None:
        if frame is None or frame.empty:
            return None
        last_close, last_at = float(frame["Close"].iloc[-1]), frame.index[-1]
        prev, prev_at = _last_close_before(frame, prev_close_at) if prev_close_at is not None else (None, None)
        change = None if not prev else last_close / prev - 1
        doc = {"name": name or cfg.names.get(ticker, ticker), "last": round(last_close, 4),
               "last_at": last_at.isoformat(timespec="minutes"),
               "prev_close": round(prev, 4) if prev else None,
               "prev_close_at": prev_at.isoformat(timespec="minutes") if prev_at is not None else None,
               "change": round(change, 5) if change is not None else None}
        if bars:
            session_bars = frame.loc[frame.index >= session_start]
            doc["session_high"] = round(float(session_bars["High"].max()), 4) if len(session_bars) else None
            doc["session_low"] = round(float(session_bars["Low"].min()), 4) if len(session_bars) else None
            doc["bars"] = _bars(frame, OSLO, bars)
        return doc

    stocks = {t: snapshot(t, intraday.get(t)) for t in cfg.tickers}
    stocks = {t: s for t, s in stocks.items() if s is not None}
    return {
        "schema": SCHEMA,
        "generated_utc": now.isoformat(timespec="seconds"),
        "source": {"study": "oslo-oil-sensitivity", "version": __version__,
                   "prices": "Yahoo Finance, unadjusted 15-minute bars", "delay_minutes": DELAY_MINUTES},
        "session": {
            "tz": "Europe/Oslo", "date": session_date.isoformat(),
            "previous_date": previous_date.isoformat() if previous_date else None,
            "previous_close_at": prev_close_at.isoformat(timespec="minutes") if prev_close_at is not None else None,
            "market_open": bool(market_open), "trading_day": bool(is_trading_day),
            "hours": f"{OPEN:%H:%M}-{CLOSE:%H:%M}",
            "latest_bar": latest_bar.isoformat(timespec="minutes"),
            "age_minutes": round(age_minutes, 1), "stale": bool(stale),
            "note": "Moves are measured from Oslo Børs's previous close. Brent trades almost around the clock, so its "
                    "move over the same window starts the previous evening.",
        },
        "brent": snapshot(oil_t, intraday.get(oil_t), bars=400, name=cfg.study.factors.oil.name),
        "index": snapshot(index_t, index, bars=400, name=cfg.market.name),
        "usdnok": snapshot(fx_t, intraday.get(fx_t), bars=400, name="USD/NOK") if fx_t else None,
        "stocks": stocks,
        "coverage": {"stocks_with_quotes": len(stocks), "stocks_in_universe": len(cfg.tickers)},
    }


def write(doc: dict, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    return path


def load(path: str | Path) -> dict | None:
    path = Path(path)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def mark_stale(previous: dict, now: datetime | None = None, reason: str = "") -> dict:
    """When a refresh fails, keep serving the last good document but say so."""
    now = (now or datetime.now(UTC)).astimezone(UTC)
    doc = json.loads(json.dumps(previous))
    doc["session"]["stale"] = True
    doc["session"]["stale_reason"] = reason or "refresh failed; showing the last successful update"
    doc["session"]["market_open"] = bool(
        now.astimezone(OSLO).weekday() < 5 and OPEN <= now.astimezone(OSLO).time() < CLOSE)
    latest = datetime.fromisoformat(doc["session"]["latest_bar"])
    doc["session"]["age_minutes"] = round((now - latest).total_seconds() / 60, 1)
    doc["refreshed_utc"] = now.isoformat(timespec="seconds")
    return doc


def next_tick(now: datetime | None = None, latest: dict | None = None) -> datetime | None:
    """When the refresh loop should fetch next, or None when today's session is over.

    Called right after a fetch, so a tick that is due exactly now is already done and the next one is
    returned. `latest` is the last published document. It proves the exchange is closed today (a public
    holiday) only if it was itself fetched today after 10:30, successfully, and still has no bars from
    today. An older document - yesterday's, or a stale re-publish after a failed download - says nothing
    about today, so the loop keeps going.
    """
    now_oslo = (now or datetime.now(UTC)).astimezone(OSLO)
    if now_oslo.weekday() >= 5:
        return None
    day = now_oslo.date()
    if latest and now_oslo.time() >= HOLIDAY_CHECK_AFTER:
        session = latest.get("session", {})
        try:
            fetched = datetime.fromisoformat(latest["generated_utc"]).astimezone(OSLO)
        except (KeyError, TypeError, ValueError):
            fetched = None
        fetched_late_today = fetched is not None and fetched.date() == day and fetched.time() >= HOLIDAY_CHECK_AFTER
        if fetched_late_today and not session.get("stale_reason") and session.get("date", day.isoformat()) < day.isoformat():
            return None
    first = datetime.combine(day, FIRST_TICK, tzinfo=OSLO)
    last = datetime.combine(day, LAST_TICK, tzinfo=OSLO)
    if now_oslo < first:
        return first
    base = now_oslo.replace(minute=now_oslo.minute - now_oslo.minute % 15, second=0, microsecond=0)
    tick = base + timedelta(minutes=1)
    if tick <= now_oslo:
        tick += TICK_EVERY
    return tick if tick <= last else None


def oslo_now() -> datetime:
    return datetime.now(OSLO)


def next_session_window(now: datetime | None = None) -> tuple[datetime, datetime]:
    """Start and end of the current or next Oslo session in UTC (used by the scheduler notes)."""
    now_oslo = (now or datetime.now(UTC)).astimezone(OSLO)
    day = now_oslo.date()
    while day.weekday() >= 5 or (day == now_oslo.date() and now_oslo.time() >= CLOSE):
        day += timedelta(days=1)
    start = datetime.combine(day, OPEN, tzinfo=OSLO)
    end = datetime.combine(day, CLOSE, tzinfo=OSLO)
    return start.astimezone(UTC), end.astimezone(UTC)
