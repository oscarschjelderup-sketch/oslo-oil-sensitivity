import numpy as np
import pandas as pd
import pytest

from oilbeta.config import Config


@pytest.fixture
def rng():
    return np.random.default_rng(42)


@pytest.fixture
def mini_cfg(tmp_path):
    raw = {
        "sample": {"start": "2020-01-01", "end": "2020-12-31"},
        "factors": {
            "oil": {"ticker": "BZ=F", "name": "Brent"},
            "market": {"name": "Index", "early_ticker": "OLD.OL", "late_ticker": "NEW.OL",
                       "splice_date": "2020-01-08"},
            "context": {},
        },
        "betas": {"min_history": 1},
        "validation": {"max_abs_daily_return": 0.5, "max_zero_return_share": 0.2},
        "universe": {"Energy": {"AAA.OL": "Alpha", "BBB.OL": "Beta"}, "Fish": {"CCC.OL": "Gamma"}},
    }
    return Config(raw=raw, root=tmp_path)


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
