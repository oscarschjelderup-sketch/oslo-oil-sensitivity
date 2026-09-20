"""Run every step and collect the results in one object."""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from . import MARKET, OIL, betas, data, events, pca, regimes, scenarios
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


def run(cfg: Config, refresh: bool = False, log=print) -> Results:
    b, e, s = cfg.section("betas"), cfg.section("events"), cfg.section("scenarios")

    log("1/6  data: snapshot, alignment, validation")
    stale = False
    try:
        prices = data.fetch_prices(cfg, refresh=refresh)
    except Exception as exc:                       # network down, Yahoo hiccup: keep serving the last good snapshot
        if not (refresh and cfg.prices_path.exists()):
            raise
        log(f"     download failed ({exc}); using the cached snapshot")
        prices, stale = data.fetch_prices(cfg, refresh=False), True
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
    res.tables["betas_full"] = betas.beta_table(frame_w, meta, fac_w, b["min_history"], b["hac_lags"])
    res.tables["betas_rolling"] = betas.rolling_betas(frame_w, fac_w, b["rolling_window"],
                                                      b["rolling_min_obs"], b["hac_lags"])

    log("3/6  event study: rule-based oil shocks and abnormal returns")
    est = tuple(e["estimation_window"])
    ev = events.find_events(daily[OIL], e["z_threshold"], e["vol_window"], e["min_gap"], lead=-est[0], lag=e["min_post_days"])
    cars = events.abnormal_returns(frame_d, fac_d, ev, est, e["windows"])
    res.tables["events"] = ev
    res.tables["event_cars"] = cars
    res.tables["event_summary_total"] = events.summarise(cars, "car_total")
    res.tables["event_summary_relative"] = events.summarise(cars, "car_relative")
    res.tables["shock_betas"] = events.shock_betas(cars)
    aggregates = meta.index[meta["kind"] != "stock"]
    res.tables["event_paths"] = events.car_paths(frame_d[aggregates], fac_d, ev, est)

    log("4/6  scenarios and out-of-sample check")
    res.tables["scenarios"] = scenarios.scenario_table(frame_w, meta, fac_w, s["window"], s["shocks"],
                                                       b["min_history"])
    oos = scenarios.out_of_sample(frame_w, fac_w, cars, ev, cfg.tickers, s["window"], s["oos_min_history"])
    res.tables["oos_events"] = oos
    res.tables["oos_summary"] = scenarios.summarise_oos(oos)

    log("5/6  regimes: up/down and calm/turbulent oil betas")
    direction, volatility = regimes.regime_tables(frame_w, meta, fac_w, cfg.section("regimes")["vol_window"],
                                                  b["min_history"])
    res.tables["regime_direction"], res.tables["regime_volatility"] = direction, volatility

    log("6/6  PCA on the cross-section of returns")
    context = [c for c in ("USDNOK", "VIX") if c in weekly]
    comp = pca.return_pca(weekly[cfg.tickers], weekly[[MARKET, OIL, *context]])
    res.tables["pca_summary"], res.tables["pca_loadings"] = comp["summary"], comp["loadings"]
    res.info["pca"] = dict(comp["summary"].attrs)
    return res
