"""Where prices come from. One small interface, so a vendor can be swapped or cross-checked.

    source.fetch(tickers, start, end) -> DataFrame of daily levels, one column per ticker,
                                         DatetimeIndex named "Date", end date inclusive
"""
from __future__ import annotations

import io
from datetime import timedelta
from typing import Protocol

import pandas as pd


class PriceSource(Protocol):
    name: str

    def fetch(self, tickers: list[str], start: str, end: str) -> pd.DataFrame: ...


class YahooSource:
    """Auto-adjusted daily closes. Free and broad, but not audited: see data_exceptions.yaml."""

    name = "Yahoo Finance via yfinance (auto-adjusted closes)"

    def fetch(self, tickers: list[str], start: str, end: str) -> pd.DataFrame:
        import yfinance as yf

        end_exclusive = (pd.Timestamp(end) + timedelta(days=1)).strftime("%Y-%m-%d")
        raw = yf.download(list(tickers), start=start, end=end_exclusive, auto_adjust=True, progress=False, threads=True)
        prices = raw["Close"]
        if isinstance(prices, pd.Series):                  # a single ticker comes back as a Series
            prices = prices.to_frame(tickers[0])
        prices = prices.sort_index()
        prices.index = pd.to_datetime(prices.index).tz_localize(None)
        prices.index.name = "Date"
        return prices.reindex(columns=list(tickers)).dropna(how="all")


class FredSource:
    """Daily series from FRED's public CSV endpoint (no API key).

    Used for Brent spot (DCOILBRENTEU, source: U.S. Energy Information Administration): an
    official series that goes back to 1987 and is independent of Yahoo. It is published with a
    lag of about a week, so it suits history and cross-checks, not the live monitor.
    """

    name = "FRED, Federal Reserve Bank of St. Louis (graph CSV endpoint)"
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}&cosd={start}&coed={end}"

    def fetch(self, tickers: list[str], start: str, end: str) -> pd.DataFrame:
        from curl_cffi import requests  # FRED resets plain urllib/requests connections; a browser TLS profile works

        columns = []
        for series in tickers:
            response = requests.get(self.url.format(series=series, start=start, end=end), impersonate="chrome", timeout=60)
            response.raise_for_status()
            frame = pd.read_csv(io.StringIO(response.text), na_values=".", index_col=0, parse_dates=True)
            if frame.shape[1] != 1 or frame.empty:
                raise RuntimeError(f"FRED returned nothing usable for {series}")
            columns.append(frame.iloc[:, 0].rename(series).astype(float))
        prices = pd.concat(columns, axis=1).sort_index()
        prices.index.name = "Date"
        return prices.dropna(how="all")
