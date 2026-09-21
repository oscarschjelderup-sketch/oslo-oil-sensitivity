"""The narrative research report: one self-contained HTML file with the figures embedded.

Headline sentences are assembled from the numbers (`_findings`), so they cannot drift away from
the tables. The layout lives in templates/report.html.j2.
"""
from __future__ import annotations

import base64
from importlib import resources
from pathlib import Path

import pandas as pd
from jinja2 import Template

from .. import MARKET
from ..analysis import robustness as rb
from ..pipeline import Results


# --------------------------------------------------------------------------
def _findings(res: Results) -> list[str]:
    T = res.tables
    full, recent, s = T["betas_full"], T["scenarios"], T["oos_summary"]
    roll = T["betas_rolling"]
    mroll = roll[roll["unit"] == MARKET].set_index("date")["beta_oil_total"]
    early = mroll.loc[:"2013-12-31"].mean()
    stocks = full[full["kind"] == "stock"]
    keeps = stocks[(stocks["partial_q"] < 0.05) & (stocks["beta_oil_partial"] > 0)]     # 5% false discovery rate
    n_partial = len(keeps)
    n_negative = int(((stocks["partial_q"] < 0.05) & (stocks["beta_oil_partial"] < 0)).sum())
    n_energy = int(keeps["sector"].isin(["Exploration & production", "Oil service & drilling"]).sum())
    neg = stocks.sort_values("beta_oil_partial").iloc[0]
    sectors_recent = recent[recent["kind"] == "sector"]
    flat = sectors_recent[(sectors_recent["total_lo"] < 0) & (sectors_recent["total_hi"] > 0)]
    d = T["regime_direction"].loc[MARKET]
    sb = T["shock_betas"].join(full[["beta_oil_total", "kind"]])
    sb = sb[sb["kind"] == "stock"]
    top = recent[recent["kind"] == "sector"].iloc[0]
    counts, by_type = T["shock_type_counts"], T["shock_betas_by_type"]
    net = T["shock_betas_net_of_world"].loc[MARKET]
    energy = "Exploration & production"
    findings = [
        f"<b>The oil beta of Oslo Børs has gone from {early:.2f} to {mroll.iloc[-1]:.2f}.</b> Over the full sample a "
        f"10% move in Brent has come with a {full.loc[MARKET, 'beta_oil_total'] * 10:.1f}% move in the benchmark "
        f"index. The rolling two-year beta averaged {early:.2f} up to 2013, {mroll.loc['2015-01-01':].mean():.2f} "
        f"since 2015, and is {mroll.iloc[-1]:.2f} today.",
        f"<b>Only energy carries oil risk beyond the index.</b> Once the index is held fixed, {n_partial} of "
        f"{len(stocks)} stocks keep a significantly positive oil beta at a 5% false discovery rate, {n_energy} of them "
        f"in E&amp;P and oil service; {n_negative} have a significantly negative one. The most negative belongs to {neg['name']} ({neg['beta_oil_partial']:+.2f}), where fuel is a cost.",
        f"<b>Over the last five years oil has stopped mattering for {len(flat)} of {len(sectors_recent)} sectors.</b> For "
        f"{', '.join(flat['name'].str.lower())} the recent total oil beta cannot be told apart from zero. "
        f"{top['name']} still moves {top['exp_+10%']:+.1%} for a +10% Brent move.",
        f"<b>Oil shocks are priced within two days.</b> Across {len(T['events'])} rule-based shocks the reaction lands "
        f"in the [0,+1] window. Betas measured only in those shock days line up with ordinary weekly betas "
        f"(correlation {sb['shock_beta'].corr(sb['beta_oil_total']):.2f} across stocks).",
        f"<b>Outside energy, the oil beta is mostly a demand-shock beta.</b> {counts.loc['down', 'share_demand']:.0%} of "
        f"the large oil declines are demand-type shocks (global equities fall with oil), against "
        f"{counts.loc['up', 'share_demand']:.0%} of the large rises. The index reacts with a beta of "
        f"{by_type.loc[MARKET, 'beta_demand']:.2f} in demand-type shocks and {by_type.loc[MARKET, 'beta_supply']:.2f} in "
        f"supply-type shocks (p = {by_type.loc[MARKET, 'p_diff']:.3f}); {energy} reacts the same in both "
        f"({by_type.loc[energy, 'beta_demand']:.2f} and {by_type.loc[energy, 'beta_supply']:.2f}). Holding the S&amp;P 500 "
        f"move fixed, the index's shock beta falls from {net['shock_beta']:.2f} to {net['beta_oil_net']:.2f}.",
        f"<b>Sensitivity is stable, predictability is absent.</b> Betas estimated only on past data rank stocks "
        f"correctly in the next shock (mean rank correlation {s.loc['spearman_impact', 'mean']:+.2f}, "
        f"t = {s.loc['spearman_impact', 't']:.1f}, positive in {s.loc['spearman_impact', 'share_positive']:.0%} of "
        f"shocks). The same ranking says nothing about the following days "
        f"({s.loc['spearman_drift', 'mean']:+.2f}, t = {s.loc['spearman_drift', 't']:.1f}). "
        f"This is a risk tool, not a trading signal.",
        f"<b>The downside beta is larger.</b> The index's oil beta is {d['beta_down']:.2f} in weeks when oil falls "
        f"and {d['beta_up']:.2f} when it rises (p = {d['p_diff']:.3f}). That is the same fact seen from another side: "
        f"large declines are mostly demand scares that hit all equities, so part of the downside beta is shared macro "
        f"news rather than oil itself.",
    ]
    if "robustness_oil_series" in T:
        r, a = T["robustness_oil_series"], res.info["robustness"]
        pre, crisis, since_2015 = a["pre_crisis"]["mean"], a["crisis_era"]["mean"], mroll.loc["2015-01-01":].mean()
        reading = (f"The pre-crash level is close to the average since 2015 ({since_2015:.2f}), so the decline after 2013 "
                   f"is as much the crash leaving the window as oil leaving Oslo Børs."
                   if abs(pre - since_2015) < 0.5 * abs(crisis - since_2015) else
                   f"The average since 2015 is {since_2015:.2f}.")
        findings.append(
            f"<b>The betas of 2009-2013 were a crash-era level, and no result depends on the oil series.</b> "
            f"With Brent spot from FRED instead of the Yahoo future the index beta is {r.loc[rb.SPOT, 'index_beta']:.2f} "
            f"against {r.loc[rb.BASELINE, 'index_beta']:.2f}, and stocks rank the same (rank correlation "
            f"{r.loc[rb.SPOT, 'rank_corr_with_baseline']:.2f}). Starting in 2005 instead of 2007, two-year windows that end "
            f"before the autumn-2008 crash average {pre:.2f}; windows ending 2009-2013 average {crisis:.2f}. {reading}")
    return findings


def _fmt_table(df: pd.DataFrame, formats: dict[str, str], rename: dict[str, str]) -> str:
    out = df[list(formats)].copy()
    for col, fmt in formats.items():
        if fmt:
            out[col] = out[col].map(lambda v, f=fmt: "" if pd.isna(v) else f.format(v))
    return out.rename(columns=rename).to_html(index=False, border=0, classes="data", escape=False)


def _scenario_tables(res: Results) -> tuple[str, str]:
    sc = res.tables["scenarios"].copy()
    sc["ci"] = sc.apply(lambda r: f"{r['lo_+10%']:+.1%} to {r['hi_+10%']:+.1%}", axis=1)
    formats = {"name": "", "beta_oil_total": "{:.2f}", "exp_-10%": "{:+.1%}", "exp_+10%": "{:+.1%}", "ci": "",
               "exp_+20%": "{:+.1%}", "r2_oil_only": "{:.0%}", "p_same_sign": "{:.0%}"}
    rename = {"name": "", "beta_oil_total": "Oil beta", "exp_-10%": "Brent −10%", "exp_+10%": "Brent +10%",
              "ci": "95% interval (+10%)", "exp_+20%": "Brent +20%", "r2_oil_only": "Explained by oil",
              "p_same_sign": "P(same sign)"}
    agg = sc[sc["kind"] != "stock"].sort_values("beta_oil_total", ascending=False)
    stocks = sc[sc["kind"] == "stock"].sort_values("beta_oil_total", ascending=False)
    ends = pd.concat([stocks.head(10), stocks.tail(10)])
    return _fmt_table(agg, formats, rename), _fmt_table(ends, formats, rename)


def _event_table(res: Results) -> str:
    s = res.tables["event_summary_total"]
    meta = res.meta
    s = s[(s["window"] == "impact") & s["unit"].map(lambda u: meta.loc[u, "kind"] != "stock")]
    wide = s.pivot(index="unit", columns="direction", values=["mean_car", "t"])
    wide.columns = [f"{a}_{b}" for a, b in wide.columns]
    wide = wide.join(res.tables["shock_betas"][["shock_beta", "shock_lo", "shock_hi"]]).sort_values("shock_beta", ascending=False)
    wide["name"] = ["Oslo Børs index" if u == MARKET else u for u in wide.index]
    wide["ci"] = wide.apply(lambda r: f"{r['shock_lo']:.2f} to {r['shock_hi']:.2f}", axis=1)
    formats = {"name": "", "mean_car_up": "{:+.1%}", "t_up": "{:.1f}", "mean_car_down": "{:+.1%}", "t_down": "{:.1f}",
               "shock_beta": "{:.2f}", "ci": ""}
    rename = {"name": "", "mean_car_up": "CAR, up-shocks", "t_up": "t", "mean_car_down": "CAR, down-shocks",
              "t_down": "t", "shock_beta": "Shock beta", "ci": "95% interval"}
    return _fmt_table(wide, formats, rename)


def _shock_type_table(res: Results) -> str:
    t = res.tables["shock_betas_by_type"].join(res.tables["shock_betas_net_of_world"][["shock_beta", "beta_oil_net"]])
    t = t[t["kind"] != "stock"].sort_values("beta_demand", ascending=False)
    t["unit_name"] = ["Oslo Børs index" if u == MARKET else u for u in t.index]
    formats = {"unit_name": "", "shock_beta": "{:.2f}", "beta_demand": "{:.2f}", "beta_supply": "{:.2f}",
               "p_diff": "{:.3f}", "q_diff": "{:.3f}", "beta_oil_net": "{:.2f}"}
    rename = {"unit_name": "", "shock_beta": "All shocks", "beta_demand": "Demand-type", "beta_supply": "Supply-type",
              "p_diff": "p (equal)", "q_diff": "q (FDR)", "beta_oil_net": "Net of S&amp;P 500"}
    return _fmt_table(t, formats, rename)


def _robustness_table(res: Results) -> str:
    t = res.tables["robustness_oil_series"].copy()
    t["variant"] = t.index
    t["interval"] = t.apply(lambda r: f"{r['index_lo']:.2f} to {r['index_hi']:.2f}", axis=1)
    formats = {"variant": "", "first_week": "", "weeks": "{:,.0f}", "index_beta": "{:.2f}", "interval": "",
               "beta: Exploration & production": "{:.2f}", "beta: Banks & insurance": "{:.2f}",
               "rank_corr_with_baseline": "{:.3f}"}
    rename = {"variant": "", "first_week": "First week", "weeks": "Weeks", "index_beta": "Index oil beta",
              "interval": "95% interval", "beta: Exploration & production": "E&amp;P", "beta: Banks & insurance": "Banks",
              "rank_corr_with_baseline": "Stock rank corr. with baseline"}
    return _fmt_table(t, formats, rename)


def _data_notes(res: Results) -> dict:
    v = res.tables["validation"]
    flagged = v[(v["flags"] != "ok") & (v["sector"] != "factor")]
    ex = res.cfg.exceptions
    return {
        "flagged": [f"{r['name']} ({r['flags']})" for _, r in flagged.iterrows()],
        "dropped": [f"{e.ticker} {e.date}: {e.reason}" for e in ex.drop_returns],
        "trimmed": [f"{t} from {r.date}: {r.reason}" for t, r in ex.history_start.items()],
    }


def write_html(res: Results, figure_paths: dict[str, Path], out_path: Path) -> None:
    T, cfg = res.tables, res.cfg
    fig = {k: "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode() for k, p in figure_paths.items()}
    full, oos, ev = T["betas_full"], T["oos_summary"], T["events"]
    roll = T["betas_rolling"]
    mroll = roll[roll["unit"] == MARKET]["beta_oil_total"]
    pre = T["event_summary_total"].set_index(["unit", "direction", "window"]).loc[(MARKET, "down", "pre")]
    scenario_agg, scenario_stocks = _scenario_tables(res)
    tiles = [
        (f"{full.loc[MARKET, 'beta_oil_total']:.2f}", "oil beta of the index, full sample"),
        (f"{mroll.iloc[-1]:.2f}", "same, latest two-year window"),
        (str(len(ev)), "rule-based oil shocks studied"),
        (f"{oos.loc['spearman_impact', 'share_positive']:.0%}", "of shocks where past betas ranked stocks correctly"),
    ]
    template = Template(resources.files("oilbeta.outputs").joinpath("templates/report.html.j2").read_text(encoding="utf-8"))
    html = template.render(
        info=res.info, tiles=tiles, findings=_findings(res), fig=fig, notes=_data_notes(res),
        splice_date=cfg.market.splice_date, ev=cfg.events, n_events=len(ev),
        n_up=int((ev["direction"] == "up").sum()), n_down=int((ev["direction"] == "down").sum()),
        event_table=_event_table(res), pre_down=f"{pre['mean_car']:+.1%}", pre_down_t=f"{pre['t']:.1f}",
        scenario_agg=scenario_agg, scenario_stocks=scenario_stocks,
        sc_years=cfg.scenarios.window // 52, ref_shock=float(T["scenarios"]["p_same_sign_shock"].iloc[0]),
        spread_impact=f"{oos.loc['spread_impact', 'mean']:+.1%}", spread_impact_t=f"{oos.loc['spread_impact', 't']:.1f}",
        spread_drift=f"{oos.loc['spread_drift', 'mean']:+.1%}", spread_drift_t=f"{oos.loc['spread_drift', 't']:.1f}",
        vol=T["regime_volatility"].loc[MARKET], pc2_oil=T["pca_summary"].loc["PC2", "OIL"],
        n_stocks=int((T["betas_full"]["kind"] == "stock").sum()), counts=T["shock_type_counts"],
        shock_type_table=_shock_type_table(res),
        robustness_table=_robustness_table(res) if "robustness_oil_series" in T else None,
        agreement=res.info.get("robustness"),
    )
    out_path.write_text(html, encoding="utf-8")
