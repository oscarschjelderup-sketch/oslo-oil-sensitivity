"""Run every step and collect the results in one object."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import pandas as pd

from . import MARKET, OIL, data
from .analysis import betas, events, pca, regimes, robustness, scenarios, shocktype
from .config import Config


@dataclass
class Results:
    cfg: Config
    panel: pd.DataFrame
    weekly: pd.DataFrame
    daily: pd.DataFrame
    meta: pd.DataFrame
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    info: dict = field(default_factory=dict)


def run(cfg: Config, refresh: bool = False, log=print, rolling_stocks: bool = True,
        retries: int = 0, retry_wait: float = 45.0) -> Results:
    """Run all six steps. `rolling_stocks=False` keeps rolling betas to the index and sectors (the slow
    part is 60+ stocks x ~900 windows); the monitor needs them all, a regression test does not."""
    b, e, s = cfg.betas, cfg.events, cfg.scenarios

    log("1/6  data: snapshot, alignment, validation")
    stale = False
    for attempt in range(retries + 1):
        try:
            prices = data.fetch_prices(cfg, refresh=refresh)
            break
        except Exception as exc:                   # network down, Yahoo hiccup or a throttled cloud IP
            if attempt < retries:
                log(f"     download failed ({exc}); retrying in {retry_wait:.0f}s")
                time.sleep(retry_wait)
            elif refresh and cfg.prices_path.exists():
                log(f"     download failed ({exc}); serving the last good snapshot")
                prices, stale = data.fetch_prices(cfg, refresh=False), True
            else:
                raise
    panel = data.build_panel(prices, cfg)
    weekly, daily = data.weekly_returns(panel, cfg), data.daily_returns(panel, cfg)
    frame_w, meta = betas.units_frame(weekly, data.sector_returns(weekly, cfg), cfg)
    frame_d, _ = betas.units_frame(daily, data.sector_returns(daily, cfg), cfg)
    fac_w, fac_d = weekly[[MARKET, OIL]], daily[[MARKET, OIL]]
    res = Results(cfg=cfg, panel=panel, weekly=frame_w.join(weekly[[OIL]]), daily=frame_d.join(daily[[OIL]]), meta=meta)
    res.tables["validation"] = data.validate(panel, cfg)
    res.info["splice"] = data.splice_diagnostics(prices, cfg)
    res.info["stale"] = stale
    res.info["sample"] = {"start": str(panel.index.min().date()), "end": str(panel.index.max().date()),
                          "trading_days": len(panel), "weeks": len(weekly), "stocks": len(cfg.tickers)}

    log("2/6  betas: full-sample and rolling two-factor regressions")
    res.tables["betas_full"] = betas.beta_table(frame_w, meta, fac_w, b.min_history, b.hac_lags)
    rolling_frame = frame_w if rolling_stocks else frame_w[meta.index[meta["kind"] != "stock"]]
    res.tables["betas_rolling"] = betas.rolling_betas(rolling_frame, fac_w, b.rolling_window,
                                                      b.rolling_min_obs, b.hac_lags)

    log("3/6  event study: rule-based oil shocks and abnormal returns")
    est = e.estimation_window
    ev = events.find_events(daily[OIL], e.z_threshold, e.vol_window, e.min_gap, lead=-est[0], lag=e.min_post_days)
    cars = events.abnormal_returns(frame_d, fac_d, ev, est, e.windows)
    impact_oil = cars[cars["window"] == "impact"].groupby("event_id")["oil_move"].first()
    ev = shocktype.classify_events(ev, panel, impact_oil, e.windows["impact"])
    res.tables["events"] = ev
    res.tables["event_cars"] = cars
    res.tables["event_summary_total"] = events.summarise(cars, "car_total")
    res.tables["event_summary_relative"] = events.summarise(cars, "car_relative")
    res.tables["shock_betas"] = events.shock_betas(cars)
    res.tables["shock_type_counts"] = shocktype.type_counts(ev)
    res.tables["shock_betas_by_type"] = shocktype.betas_by_type(cars, ev, meta)
    res.tables["shock_betas_net_of_world"] = shocktype.betas_net_of_world(cars, ev, meta)
    aggregates = meta.index[meta["kind"] != "stock"]
    res.tables["event_paths"] = events.car_paths(frame_d[aggregates], fac_d, ev, est)

    log("4/6  scenarios and out-of-sample check")
    res.tables["scenarios"] = scenarios.scenario_table(frame_w, meta, fac_w, s.window, s.shocks,
                                                       b.min_history)
    oos = scenarios.out_of_sample(frame_w, fac_w, cars, ev, cfg.tickers, s.window, s.oos_min_history)
    res.tables["oos_events"] = oos
    res.tables["oos_summary"] = scenarios.summarise_oos(oos)

    log("5/6  regimes: up/down and calm/turbulent oil betas")
    direction, volatility = regimes.regime_tables(frame_w, meta, fac_w, cfg.regimes.vol_window,
                                                  b.min_history)
    res.tables["regime_direction"], res.tables["regime_volatility"] = direction, volatility

    log("6/6  PCA on the cross-section of returns")
    context = [c for c in ("USDNOK", "VIX") if c in weekly]
    comp = pca.return_pca(weekly[cfg.tickers], weekly[[MARKET, OIL, *context]])
    res.tables["pca_summary"], res.tables["pca_loadings"] = comp["summary"], comp["loadings"]
    res.info["pca"] = dict(comp["summary"].attrs)

    if cfg.study.robustness is not None and not cfg.is_live:
        log("+    robustness: another oil series, a longer sample")
        try:
            extra = data.fetch_robustness(cfg, refresh=refresh)
            check = robustness.oil_series_check(cfg, prices, extra["fred"], extra["long"])
            res.tables["robustness_oil_series"], res.tables["robustness_rolling"] = check["summary"], check["rolling"]
            res.info["robustness"] = check["agreement"]
        except Exception as exc:                   # an optional check must never take the study down with it
            log(f"     skipped ({exc})")
            res.info["robustness_skipped"] = str(exc)
    return res
