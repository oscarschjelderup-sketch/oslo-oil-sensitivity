import copy
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from oilbeta.config import Config, DataExceptions

REPO = Path(__file__).resolve().parents[1]


def study_dict() -> dict:
    """The real study parameters as a plain dict, for tests that need to bend one or two of them."""
    return copy.deepcopy(yaml.safe_load((REPO / "configs" / "study.yaml").read_text(encoding="utf-8")))


def with_exceptions(cfg: Config, exceptions: dict) -> Config:
    return replace(cfg, exceptions=DataExceptions.model_validate(exceptions))


@pytest.fixture
def rng():
    return np.random.default_rng(42)


@pytest.fixture
def mini_cfg(tmp_path):
    study = study_dict()
    study["sample"] = {"start": "2020-01-01", "end": "2020-12-31"}
    study["factors"] = {
        "oil": {"ticker": "BZ=F", "name": "Brent"},
        "market": {"name": "Index", "early_ticker": "OLD.OL", "late_ticker": "NEW.OL", "splice_date": "2020-01-08"},
        "context": {},
    }
    study["betas"]["min_history"] = 1
    universe = {"Energy": {"AAA.OL": "Alpha", "BBB.OL": "Beta"}, "Fish": {"CCC.OL": "Gamma"}}
    return Config.from_dicts(study, universe, None, tmp_path)


@pytest.fixture
def mini_prices():
    """Eight business days. Oslo is closed on 2020-01-07 (index + stocks missing), oil trades."""
    idx = pd.bdate_range("2020-01-01", periods=8)
    df = pd.DataFrame({
        "BZ=F":   [50, 51, 52, 53, 54, 55, 56, 57],
        "OLD.OL": [100, 101, 102, 103, np.nan, 105, 106, 107],
        "NEW.OL": [np.nan, np.nan, np.nan, 200, np.nan, 210, 220, 230],
        "AAA.OL": [10, 11, 12, 13, np.nan, 15, 16, 17],
        "BBB.OL": [20, 20, 20, 20, np.nan, 20, 20, 20],
        "CCC.OL": [5, 5, 6, 6, np.nan, 7, 7, 8],
    }, index=idx, dtype=float)
    df.index.name = "Date"
    return df
