"""Load the YAML config into a small typed object."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Config:
    raw: dict
    root: Path
    live_end: str | None = None      # set in live mode: the last completed trading day we ask for

    # --- sample -----------------------------------------------------------
    @property
    def start(self) -> str:
        return self.raw["sample"]["start"]

    @property
    def end(self) -> str:
        return self.live_end or self.raw["sample"]["end"]

    @property
    def is_live(self) -> bool:
        return self.live_end is not None

    def as_live(self, today: date | None = None) -> "Config":
        """Same study, moving end date: everything up to yesterday's close.

        Yesterday rather than today, because an intraday run would otherwise mix half-finished
        daily bars into the sample. Live output goes to its own folder so the pinned research
        snapshot in results/ stays reproducible.
        """
        today = today or date.today()
        return replace(self, live_end=(today - timedelta(days=1)).isoformat())

    # --- factors ----------------------------------------------------------
    @property
    def oil_ticker(self) -> str:
        return self.raw["factors"]["oil"]["ticker"]

    @property
    def market(self) -> dict:
        return self.raw["factors"]["market"]

    @property
    def context(self) -> dict[str, str]:
        return self.raw["factors"].get("context", {})

    # --- universe ---------------------------------------------------------
    @property
    def universe(self) -> dict[str, dict[str, str]]:
        return self.raw["universe"]

    @property
    def tickers(self) -> list[str]:
        return [t for members in self.universe.values() for t in members]

    @property
    def names(self) -> dict[str, str]:
        return {t: n for members in self.universe.values() for t, n in members.items()}

    @property
    def sector_of(self) -> dict[str, str]:
        return {t: s for s, members in self.universe.items() for t in members}

    @property
    def download_list(self) -> list[str]:
        m = self.market
        return [self.oil_ticker, m["early_ticker"], m["late_ticker"], *self.context.values(), *self.tickers]

    # --- paths ------------------------------------------------------------
    @property
    def raw_dir(self) -> Path:
        return self.root / "data" / "raw"

    @property
    def prices_path(self) -> Path:
        return self.raw_dir / ("prices_live.csv" if self.is_live else "prices.csv")

    @property
    def manifest_path(self) -> Path:
        return self.root / "data" / ("manifest_live.json" if self.is_live else "manifest.json")

    @property
    def results_dir(self) -> Path:
        return self.root / ("live" if self.is_live else "results")

    def section(self, name: str) -> dict:
        return self.raw[name]


def load_config(path: str | Path) -> Config:
    path = Path(path).resolve()
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    tickers = [t for members in raw["universe"].values() for t in members]
    dupes = {t for t in tickers if tickers.count(t) > 1}
    if dupes:
        raise ValueError(f"Tickers listed in more than one sector: {sorted(dupes)}")
    # configs/ sits one level below the repo root
    return Config(raw=raw, root=path.parent.parent)
