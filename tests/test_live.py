"""Live mode: moving end date, unfinished weeks, shocks whose later windows have not happened yet."""
import json
from datetime import date

import numpy as np
import pandas as pd

from oilbeta import MARKET, OIL, dashboard, data, events


def test_live_config_ends_yesterday_and_writes_elsewhere(mini_cfg):
    live = mini_cfg.as_live(today=date(2026, 9, 17))
    assert live.end == "2026-09-16" and live.is_live and not mini_cfg.is_live
    assert live.results_dir.name == "live" and mini_cfg.results_dir.name == "results"
    assert live.prices_path != mini_cfg.prices_path and live.manifest_path != mini_cfg.manifest_path
    assert mini_cfg.end == "2020-12-31"                      # the pinned config is untouched


def test_unfinished_week_is_dropped_from_weekly_returns(mini_cfg, mini_prices):
    panel = data.build_panel(mini_prices, mini_cfg)          # last price is Friday 2020-01-10
    full = data.weekly_returns(panel, mini_cfg)
    midweek = mini_cfg.as_live(today=date(2020, 1, 9))       # "yesterday" = Wednesday 2020-01-08
    cut = data.weekly_returns(panel.loc[:"2020-01-08"], midweek)
    assert list(full.index) == [pd.Timestamp("2020-01-10")]   # one complete week-on-week return
    assert cut.empty                                          # the week ending 10 Jan is not over on the 8th


def test_recent_shock_gets_impact_but_no_drift(rng):
    T = 400
    idx = pd.bdate_range("2024-01-01", periods=T)
    o = np.clip(rng.normal(scale=0.01, size=T), -0.02, 0.02)   # no accidental shocks
    o[T - 3] = 0.12                                          # a shock three days before the data ends
    m = 0.3 * o + rng.normal(scale=0.005, size=T)
    frame = pd.DataFrame({MARKET: m, "A": 0.8 * o + rng.normal(scale=0.005, size=T)}, index=idx)
    factors = pd.DataFrame({MARKET: m, OIL: o}, index=idx)
    ev = events.find_events(factors[OIL], 2.5, 250, 11, lead=270, lag=1)
    assert list(ev["pos"]) == [T - 3]
    windows = {"pre": [-5, -1], "impact": [0, 1], "drift": [2, 10]}
    cars = events.abnormal_returns(frame, factors, ev, (-270, -21), windows).set_index(["unit", "window"])
    assert np.isfinite(cars.loc[("A", "impact"), "car_total"]) and cars.loc[("A", "impact"), "car_total"] > 0.05
    assert np.isnan(cars.loc[("A", "drift"), "car_total"])   # never a partial sum passed off as a CAR
    assert np.isnan(cars.loc[("A", "drift"), "oil_move"])
    paths = events.car_paths(frame, factors, ev, (-270, -21))
    assert paths.empty or "A" not in set(paths["unit"])      # incomplete paths are left out of the averages


def test_shock_on_the_last_day_waits_for_its_impact_window(rng):
    o = pd.Series(np.clip(rng.normal(scale=0.01, size=300), -0.02, 0.02), index=pd.bdate_range("2024-01-01", periods=300))
    o.iloc[-1] = 0.15
    assert events.find_events(o, 2.5, 250, 11, lead=270, lag=1).empty
    o.loc[o.index[-1] + pd.offsets.BDay(1)] = 0.0            # one more day of data and it enters
    assert list(events.find_events(o, 2.5, 250, 11, lead=270, lag=1)["pos"]) == [299]


def test_dashboard_payload_is_embedded_safely():
    payload = {"meta": {"note": "</script><b>x</b>"}, "v": dashboard._clean(np.float64("nan")), "w": dashboard._clean(np.float64(0.123456))}
    parts = dashboard.render(payload)
    page, document, data_js = parts["page"], parts["document"], parts["data_js"]
    assert dashboard.MARKER not in page and dashboard.MARKER not in document
    assert payload["v"] is None and payload["w"] == 0.1235
    assert document.startswith("<!doctype html>") and not page.lstrip().startswith("<!doctype")
    assert f'<script src="{dashboard.DATA_FILE}"></script>' in page and "window.OIL_DATA = " not in page
    assert data_js in document and "<\\/script><b>" in data_js       # inlined copy cannot close the script tag
    assert json.loads(data_js[len("window.OIL_DATA = "):].rstrip().rstrip(";").replace("<\\/", "</")) == payload
