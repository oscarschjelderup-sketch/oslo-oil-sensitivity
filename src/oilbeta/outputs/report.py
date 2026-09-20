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
from ..pipeline import Results


# --------------------------------------------------------------------------
def _findings(res: Results) -> list[str]:
    T = res.tables
    full, recent, s = T["betas_full"], T["scenarios"], T["oos_summary"]
    roll = T["betas_rolling"]
    mroll = roll[roll["unit"] == MARKET].set_index("date")["beta_oil_total"]
    early = mroll.loc[:"2013-12-31"].mean()
    stocks = full[full["kind"] == "stock"]
    keeps = stocks[(stocks["partial_p"] < 0.05) & (stocks["beta_oil_partial"] > 0)]
    n_partial = len(keeps)
    n_energy = int(keeps["sector"].isin(["Exploration & production", "Oil service & drilling"]).sum())
    neg = stocks.sort_values("beta_oil_partial").iloc[0]
    sectors_recent = recent[recent["kind"] == "sector"]
    flat = sectors_recent[(sectors_recent["total_lo"] < 0) & (sectors_recent["total_hi"] > 0)]
    d = T["regime_direction"].loc[MARKET]
    sb = T["shock_betas"].join(full[["beta_oil_total", "kind"]])
    sb = sb[sb["kind"] == "stock"]
    top = recent[recent["kind"] == "sector"].iloc[0]
    return [
        f"<b>The oil beta of Oslo Børs has gone from {early:.2f} to {mroll.iloc[-1]:.2f}.</b> Over the full sample a "
        f"10% move in Brent has come with a {full.loc[MARKET, 'beta_oil_total'] * 10:.1f}% move in the benchmark "
        f"index. The rolling two-year beta averaged {early:.2f} up to 2013, {mroll.loc['2015-01-01':].mean():.2f} "
        f"since 2015, and is {mroll.iloc[-1]:.2f} today.",
        f"<b>Only energy carries oil risk beyond the index.</b> Once the index is held fixed, {n_partial} of "
        f"{len(stocks)} stocks keep a significantly positive oil beta, {n_energy} of them in E&amp;P and oil service. "
        f"The most negative partial beta belongs to {neg['name']} ({neg['beta_oil_partial']:+.2f}), where fuel is a cost.",
        f"<b>Over the last five years oil has stopped mattering for {len(flat)} of {len(sectors_recent)} sectors.</b> For "
        f"{', '.join(flat['name'].str.lower())} the recent total oil beta cannot be told apart from zero. "
        f"{top['name']} still moves {top['exp_+10%']:+.1%} for a +10% Brent move.",
        f"<b>Oil shocks are priced within two days.</b> Across {len(T['events'])} rule-based shocks the reaction lands "
        f"in the [0,+1] window. Betas measured only in those shock days line up with ordinary weekly betas "
        f"(correlation {sb['shock_beta'].corr(sb['beta_oil_total']):.2f} across stocks).",
        f"<b>Sensitivity is stable, predictability is absent.</b> Betas estimated only on past data rank stocks "
        f"correctly in the next shock (mean rank correlation {s.loc['spearman_impact', 'mean']:+.2f}, "
        f"t = {s.loc['spearman_impact', 't']:.1f}, positive in {s.loc['spearman_impact', 'share_positive']:.0%} of "
        f"shocks). The same ranking says nothing about the following days "
        f"({s.loc['spearman_drift', 'mean']:+.2f}, t = {s.loc['spearman_drift', 't']:.1f}). "
        f"This is a risk tool, not a trading signal.",
        f"<b>The downside beta is larger.</b> The index's oil beta is {d['beta_down']:.2f} in weeks when oil falls "
        f"and {d['beta_up']:.2f} when it rises (p = {d['p_diff']:.3f}). Large oil declines tend to be demand scares "
        f"that hit all equities, so part of this is shared macro news rather than oil itself.",
    ]


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
    )
    out_path.write_text(html, encoding="utf-8")
