"""Configuration: three YAML files, validated before anything runs.

    configs/study.yaml            how the study is done (sample, factors, windows, thresholds)
    configs/universe.yaml         which stocks, in which sectors
    configs/data_exceptions.yaml  every manual intervention in the data, each with its reason

Unknown keys are rejected, so a typo (`roling_window`) stops the run instead of silently
falling back to a default. Cross-file rules are checked too: a ticker may sit in only one
sector, and a data exception must point at a ticker that is actually in the universe.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

STUDY_FILE, UNIVERSE_FILE, EXCEPTIONS_FILE = "study.yaml", "universe.yaml", "data_exceptions.yaml"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# --- study.yaml ---------------------------------------------------------------
class Sample(Strict):
    start: date
    end: date

    @model_validator(mode="after")
    def _ordered(self):
        if self.start >= self.end:
            raise ValueError("sample.start must be before sample.end")
        return self


class OilFactor(Strict):
    ticker: str
    name: str


class MarketFactor(Strict):
    name: str
    early_ticker: str
    late_ticker: str
    splice_date: date


class Factors(Strict):
    oil: OilFactor
    market: MarketFactor
    context: dict[str, str] = {}


class Betas(Strict):
    frequency: Literal["weekly"]
    rolling_window: int = Field(gt=10)
    rolling_min_obs: int = Field(gt=10)
    min_history: int = Field(gt=0)
    hac_lags: int | Literal["auto"] = "auto"

    @model_validator(mode="after")
    def _window_holds_min_obs(self):
        if self.rolling_min_obs > self.rolling_window:
            raise ValueError("betas.rolling_min_obs cannot exceed betas.rolling_window")
        return self


Window = tuple[int, int]


class Events(Strict):
    z_threshold: float = Field(gt=0)
    vol_window: int = Field(gt=20)
    min_gap: int = Field(ge=1)
    min_post_days: int = Field(ge=1)
    estimation_window: Window
    windows: dict[str, Window]

    @model_validator(mode="after")
    def _windows_make_sense(self):
        first, last = self.estimation_window
        if not first < last < 0:
            raise ValueError("events.estimation_window must lie before the event, e.g. [-270, -21]")
        for name, (a, b) in self.windows.items():
            if a > b:
                raise ValueError(f"events.windows.{name}: start is after end")
            if a <= last:
                raise ValueError(f"events.windows.{name} overlaps the estimation window")
        missing = {"impact", "drift"} - set(self.windows)
        if missing:
            raise ValueError(f"events.windows needs {sorted(missing)} (used by the out-of-sample test)")
        if self.windows["impact"][1] < self.min_post_days:
            raise ValueError("events.min_post_days cannot reach past the end of the impact window")
        return self


class Scenarios(Strict):
    window: int = Field(gt=50)
    shocks: list[float]
    oos_min_history: int = Field(gt=20)

    @model_validator(mode="after")
    def _shocks_are_returns(self):
        if not self.shocks or any(s <= -1 or s == 0 for s in self.shocks):
            raise ValueError("scenarios.shocks are simple returns such as -0.10 and 0.10 (non-zero, above -100%)")
        return self


class Regimes(Strict):
    vol_window: int = Field(gt=4)


class Validation(Strict):
    max_abs_daily_return: float = Field(gt=0)
    max_zero_return_share: float = Field(gt=0, le=1)


class Study(Strict):
    sample: Sample
    factors: Factors
    betas: Betas
    events: Events
    scenarios: Scenarios
    regimes: Regimes
    validation: Validation


# --- data_exceptions.yaml -------------------------------------------------------
class DropReturn(Strict):
    ticker: str
    date: date
    reason: str = Field(min_length=4)      # an intervention without a reason is not allowed


class HistoryStart(Strict):
    date: date
    reason: str = Field(min_length=4)


class DataExceptions(Strict):
    drop_returns: list[DropReturn] = []
    history_start: dict[str, HistoryStart] = {}


# --- the object the rest of the package uses -----------------------------------
Universe = dict[str, dict[str, str]]          # sector -> {ticker: company name}


@dataclass(frozen=True)
class Config:
    study: Study
    universe: Universe
    exceptions: DataExceptions
    root: Path
    live_end: str | None = None      # set in live mode: the last completed trading day we ask for

    def __post_init__(self):
        tickers = self.tickers
        dupes = sorted({t for t in tickers if tickers.count(t) > 1})
        if dupes:
            raise ValueError(f"universe: tickers listed in more than one sector: {dupes}")
        if not tickers:
            raise ValueError("universe: no tickers")
        touched = {d.ticker for d in self.exceptions.drop_returns} | set(self.exceptions.history_start)
        unknown = sorted(touched - set(tickers))
        if unknown:
            raise ValueError(f"data_exceptions: tickers that are not in the universe: {unknown}")

    @classmethod
    def from_dicts(cls, study: dict, universe: dict, exceptions: dict | None, root: Path) -> Config:
        return cls(study=Study.model_validate(study), universe=universe,
                   exceptions=DataExceptions.model_validate(exceptions or {}), root=Path(root))

    # --- sections of the study -------------------------------------------------
    @property
    def betas(self) -> Betas:
        return self.study.betas

    @property
    def events(self) -> Events:
        return self.study.events

    @property
    def scenarios(self) -> Scenarios:
        return self.study.scenarios

    @property
    def regimes(self) -> Regimes:
        return self.study.regimes

    @property
    def validation(self) -> Validation:
        return self.study.validation

    # --- sample -----------------------------------------------------------------
    @property
    def start(self) -> str:
        return self.study.sample.start.isoformat()

    @property
    def end(self) -> str:
        return self.live_end or self.study.sample.end.isoformat()

    @property
    def is_live(self) -> bool:
        return self.live_end is not None

    def as_live(self, today: date | None = None) -> Config:
        """Same study, moving end date: everything up to yesterday's close.

        Yesterday rather than today, because an intraday run would otherwise mix half-finished
        daily bars into the sample. Live output goes to its own folder so the pinned research
        snapshot in results/ stays reproducible.
        """
        today = today or date.today()
        return replace(self, live_end=(today - timedelta(days=1)).isoformat())

    def with_stock(self, ticker: str, sector: str = "Ad hoc") -> Config:
        """A copy with one extra ticker (for `oilbeta stock <any Yahoo ticker>`)."""
        universe = {s: dict(members) for s, members in self.universe.items()}
        universe.setdefault(sector, {})[ticker] = ticker
        return replace(self, universe=universe)

    # --- factors ------------------------------------------------------------------
    @property
    def oil_ticker(self) -> str:
        return self.study.factors.oil.ticker

    @property
    def market(self) -> MarketFactor:
        return self.study.factors.market

    @property
    def context(self) -> dict[str, str]:
        return self.study.factors.context

    # --- universe -----------------------------------------------------------------
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
        return [self.oil_ticker, m.early_ticker, m.late_ticker, *self.context.values(), *self.tickers]

    # --- paths --------------------------------------------------------------------
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


def _read(path: Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_config(path: str | Path = "configs") -> Config:
    """Load the three files from a config directory (or from the directory of a given study file)."""
    path = Path(path).resolve()
    folder = path if path.is_dir() else path.parent
    exceptions_file = folder / EXCEPTIONS_FILE
    return Config.from_dicts(
        study=_read(folder / STUDY_FILE),
        universe=_read(folder / UNIVERSE_FILE),
        exceptions=_read(exceptions_file) if exceptions_file.exists() else {},
        root=folder.parent,                     # configs/ sits one level below the repo root
    )
