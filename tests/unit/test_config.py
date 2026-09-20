"""The config layer must stop a bad run before it starts."""
from pathlib import Path

import pytest
from pydantic import ValidationError

from conftest import REPO, study_dict
from oilbeta.config import Config, load_config

UNIVERSE = {"Energy": {"AAA.OL": "Alpha", "BBB.OL": "Beta"}, "Fish": {"CCC.OL": "Gamma"}}


def build(study=None, universe=None, exceptions=None) -> Config:
    return Config.from_dicts(study or study_dict(), universe or UNIVERSE, exceptions, Path("."))


def test_the_shipped_config_is_valid_and_complete():
    cfg = load_config(REPO / "configs")
    assert cfg.root == REPO and len(cfg.tickers) == 63 and len(cfg.universe) == 10
    assert cfg.end == "2026-09-11" and cfg.events.windows["impact"] == (0, 1)
    assert {d.ticker for d in cfg.exceptions.drop_returns} == {"AKSO.OL", "SOFF.OL", "BORR.OL"}
    assert load_config(REPO / "configs" / "study.yaml").tickers == cfg.tickers     # a file path works too


def test_a_typo_in_a_key_is_an_error_not_a_silent_default():
    study = study_dict()
    study["betas"]["roling_window"] = study["betas"].pop("rolling_window")
    with pytest.raises(ValidationError, match="roling_window"):
        build(study)


@pytest.mark.parametrize("section, key, value, message", [
    ("sample", "end", "2001-01-01", "start must be before"),
    ("betas", "rolling_min_obs", 500, "cannot exceed"),
    ("events", "estimation_window", [-21, -270], "must lie before the event"),
    ("events", "windows", {"impact": [0, 1]}, "drift"),
    ("events", "windows", {"impact": [0, 1], "drift": [10, 2]}, "start is after end"),
    ("events", "windows", {"impact": [-30, 1], "drift": [2, 10]}, "overlaps the estimation window"),
    ("scenarios", "shocks", [0.1, -1.5], "simple returns"),
    ("validation", "max_zero_return_share", 1.5, "less than or equal to 1"),
])
def test_values_that_make_no_sense_are_rejected(section, key, value, message):
    study = study_dict()
    study[section][key] = value
    with pytest.raises(ValidationError, match=message):
        build(study)


def test_a_ticker_may_sit_in_one_sector_only():
    with pytest.raises(ValueError, match="more than one sector.*AAA.OL"):
        build(universe={"Energy": {"AAA.OL": "Alpha"}, "Fish": {"AAA.OL": "Alpha again"}})


def test_a_data_exception_needs_a_known_ticker_and_a_reason():
    fix = {"ticker": "ZZZ.OL", "date": "2020-01-03", "reason": "vendor error"}
    with pytest.raises(ValueError, match="not in the universe.*ZZZ.OL"):
        build(exceptions={"drop_returns": [fix]})
    with pytest.raises(ValidationError, match="reason"):
        build(exceptions={"drop_returns": [{"ticker": "AAA.OL", "date": "2020-01-03"}]})
    ok = build(exceptions={"drop_returns": [fix | {"ticker": "AAA.OL"}], "history_start": {"CCC.OL": {"date": "2019-01-01", "reason": "new business"}}})
    assert ok.exceptions.drop_returns[0].date.isoformat() == "2020-01-03"


def test_with_stock_adds_a_ticker_without_touching_the_original():
    cfg = build()
    extra = cfg.with_stock("AKVA.OL")
    assert "AKVA.OL" in extra.tickers and extra.sector_of["AKVA.OL"] == "Ad hoc"
    assert "AKVA.OL" not in cfg.tickers
