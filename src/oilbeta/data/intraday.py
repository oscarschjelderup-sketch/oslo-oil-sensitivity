"""Raw bars for the live layer: 15-minute intraday bars and daily OHLC candles.

These are *unadjusted* prices, which is what a trader sees on a chart. Everything the study
estimates (betas, events, scenarios) keeps using the adjusted closes in `sources.py`; nothing
here feeds an estimate. The two never mix: this module returns bars, `outputs/quotes.py` and
`outputs/candles.py` turn them into documents for the page.

Free Oslo Børs data is delayed 15 minutes by the exchange, and Yahoo publishes 15-minute bars
for the last 60 days only. Both limits are stated on the page.

yfinance downloads many tickers on parallel threads, and now and then one of them fails on the
library's own cache ("database is locked", seen in production on 5 October 2026). Whatever is
missing after the parallel download is fetched once more, one ticker at a time.
"""
from __future__ import annotations

import pandas as pd

BAR_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]
DELAY_MINUTES = 15


def _split(raw: pd.DataFrame, tickers: list[str]) -> dict[str, pd.DataFrame]:
    """yfinance returns one wide frame (ticker, field); hand back one clean frame per ticker."""
    out = {}
    if raw is None or raw.empty:
        return out
    for t in tickers:
        try:
            frame = raw[t] if isinstance(raw.columns, pd.MultiIndex) else raw
        except KeyError:
            continue
        frame = frame.reindex(columns=BAR_COLUMNS).dropna(subset=["Close"])
        if frame.empty:
            continue
        idx = pd.to_datetime(frame.index)
        frame.index = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
        frame.index.name = "time"
        out[t] = frame.sort_index()
    return out


def _download(tickers: list[str], **kwargs) -> dict[str, pd.DataFrame]:
    """Parallel download, then one sequential retry for the tickers that came back empty."""
    import yfinance as yf

    common = dict(auto_adjust=False, progress=False, group_by="ticker")
    out = _split(yf.download(list(tickers), threads=True, **common, **kwargs), list(tickers))
    missing = [t for t in tickers if t not in out]
    if missing:
        out.update(_split(yf.download(missing, threads=False, **common, **kwargs), missing))
    return out


def fetch_intraday(tickers: list[str], period: str = "5d", interval: str = "15m") -> dict[str, pd.DataFrame]:
    """15-minute bars (UTC index) for the last few sessions, one frame per ticker."""
    return _download(list(tickers), period=period, interval=interval)


def fetch_daily_ohlc(tickers: list[str], start: str, end: str) -> dict[str, pd.DataFrame]:
    """Unadjusted daily candles, one frame per ticker, index = trading date (UTC midnight)."""
    end_exclusive = (pd.Timestamp(end) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    frames = _download(list(tickers), start=start, end=end_exclusive, interval="1d")
    for frame in frames.values():
        frame.index = frame.index.normalize()
    return frames
