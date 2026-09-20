"""Write the deliverables: CSV tables, one Excel workbook and a self-contained HTML report."""
from __future__ import annotations

import base64
from pathlib import Path

import pandas as pd
from jinja2 import Template

from . import MARKET, dashboard, plots
from .pipeline import Results

EXCEL_SHEETS = {
    "betas_full": "Betas (full sample)",
    "scenarios": "Scenarios (recent betas)",
    "shock_betas": "Shock betas",
    "event_summary_total": "Event CARs (total)",
    "event_summary_relative": "Event CARs (vs index)",
    "events": "Oil shocks",
    "oos_summary": "Out-of-sample summary",
    "oos_events": "Out-of-sample by event",
    "regime_direction": "Regime up vs down",
    "regime_volatility": "Regime calm vs turbulent",
    "pca_summary": "PCA summary",
    "pca_loadings": "PCA loadings",
    "validation": "Data validation",
}


def write_tables(res: Results, out_dir: Path) -> None:
    tables = out_dir / "tables"
    tables.mkdir(parents=True, exist_ok=True)
    aggregates = set(res.meta.index[res.meta["kind"] != "stock"])
    for name, df in res.tables.items():
        if name == "event_cars":                       # large intermediate, rebuilt on every run
            continue
        if name == "betas_rolling":                    # stocks' rolling paths stay in memory; keep the repo small
            df = df[df["unit"].isin(aggregates)]
        df.to_csv(tables / f"{name}.csv", float_format="%.5f")
    with pd.ExcelWriter(out_dir / "oil_sensitivity.xlsx", engine="openpyxl") as xl:
        for name, sheet in EXCEL_SHEETS.items():
            df = res.tables[name].copy()
            for col in df.select_dtypes(include=["datetimetz", "datetime"]).columns:
                df[col] = df[col].dt.date
            df.to_excel(xl, sheet_name=sheet[:31])
            ws = xl.sheets[sheet[:31]]
            ws.freeze_panes = "B2"
            for cells in ws.columns:
                width = max(len(str(c.value)) if c.value is not None else 0 for c in cells[:60])
                ws.column_dimensions[cells[0].column_letter].width = min(max(10, width + 2), 44)


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
    ex = res.cfg.raw.get("data_exceptions") or {}
    return {
        "flagged": [f"{r['name']} ({r['flags']})" for _, r in flagged.iterrows()],
        "dropped": [f"{e['ticker']} {e['date']}: {e['reason']}" for e in ex.get("drop_returns", [])],
        "trimmed": [f"{t} from {r['date']}: {r['reason']}" for t, r in ex.get("history_start", {}).items()],
    }


TEMPLATE = Template("""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Oslo Børs oil sensitivity</title>
<style>
:root{--ink:#003255;--muted:#5B6B75;--line:#E4E8EB;--blue:#005A9E;--bg:#ffffff;--soft:#F5F7F8}
*{box-sizing:border-box} body{margin:0;background:var(--bg);color:#1c2b36;font:15px/1.55 Arial,Helvetica,sans-serif}
main{max-width:880px;margin:0 auto;padding:40px 16px 80px}
h1,h2{font-family:Cambria,Georgia,serif;color:var(--ink);line-height:1.2} h1{font-size:34px;margin:0 0 6px}
h2{font-size:23px;margin:54px 0 8px;padding-top:14px;border-top:2px solid var(--ink)} h3{color:var(--ink);font-size:15px;margin:26px 0 6px}
.lede{color:var(--muted);font-size:16px;margin:0 0 26px} .step{color:var(--blue);font-size:12px;font-weight:bold;letter-spacing:.08em;text-transform:uppercase}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:22px 0}
.tile{background:var(--soft);padding:14px 16px;border-left:3px solid var(--ink)} .tile b{display:block;font-size:26px;color:var(--ink);font-family:Cambria,Georgia,serif}
.tile span{font-size:12.5px;color:var(--muted)}
ol.findings{padding-left:20px} ol.findings li{margin:0 0 12px}
img{max-width:100%;height:auto;display:block;margin:18px auto} img.tall{max-width:640px} img.narrow{max-width:600px}
.scroll{overflow-x:auto} table.data{border-collapse:collapse;width:100%;font-size:13px;margin:10px 0 4px}
table.data th{text-align:right;color:var(--muted);font-weight:normal;border-bottom:1px solid var(--ink);padding:6px 8px;white-space:nowrap}
table.data td{text-align:right;padding:5px 8px;border-bottom:1px solid var(--line);font-variant-numeric:tabular-nums;white-space:nowrap}
table.data th:first-child,table.data td:first-child{text-align:left;color:#1c2b36}
.note{color:var(--muted);font-size:13px} .method{background:var(--soft);padding:12px 16px;font-size:13.5px;margin:14px 0}
code{background:var(--soft);padding:1px 4px;font-size:13px} ul.tight li{margin-bottom:4px}
</style></head><body><main>
<div class="step">Equity research · factor study</div>
<h1>How much oil is left in Oslo Børs?</h1>
<p class="lede">Oil-price sensitivity of {{ info.sample.stocks }} Norwegian stocks and 10 sectors, {{ info.sample.start[:4] }}–{{ info.sample.end[:4] }}:
two-factor betas with confidence intervals, a rule-based event study, scenario tables and an out-of-sample check.</p>
<div class="tiles">{% for value, label in tiles %}<div class="tile"><b>{{ value }}</b><span>{{ label }}</span></div>{% endfor %}</div>

<h2>What the data says</h2>
<ol class="findings">{% for f in findings %}<li>{{ f }}</li>{% endfor %}</ol>

<div class="step" style="margin-top:50px">Step 1</div>
<h2 style="margin-top:4px">A data foundation that can be audited</h2>
<p>Prices are auto-adjusted closes from Yahoo Finance, pinned to a fixed end date ({{ info.sample.end }}) and described in
<code>data/manifest.json</code>. Three rules separate this from a typical correlation study:</p>
<ul class="tight"><li><b>Align first, then compute returns.</b> Brent trades on days Oslo is closed. Returns are taken on the common
calendar ({{ "{:,}".format(info.sample.trading_days) }} days), so a holiday is folded into the next return instead of pairing mismatched periods.</li>
<li><b>No double counting.</b> Sector series are equal-weighted portfolios of their members. No index or ETF is averaged with its own constituents.</li>
<li><b>Weekly returns for betas.</b> Oslo closes about six hours before Brent settles; Friday-to-Friday returns dilute that timing gap and the stale prices of small caps.</li></ul>
<p>The benchmark is OSEBX, chained with OSEFX returns before {{ splice_date }} because Yahoo's OSEBX history starts there. In the
{{ info.splice.overlap_days }}-day overlap the two have a return correlation of {{ "%.3f"|format(info.splice.return_correlation) }}.</p>
<h3>Manual interventions (all of them)</h3>
<ul class="tight note">{% for d in notes.dropped %}<li>{{ d }}</li>{% endfor %}{% for d in notes.trimmed %}<li>{{ d }}</li>{% endfor %}</ul>
<p class="note">Still flagged but kept, because the moves are real or the issue is mild: {{ notes.flagged|join("; ") }}.</p>

<div class="step" style="margin-top:50px">Step 2</div>
<h2 style="margin-top:4px">Two oil betas, because there are two questions</h2>
<div class="method"><code>r = α + β<sub>mkt</sub>·MARKET + β<sub>oil</sub>·BRENT + ε</code> on weekly log returns, Newey-West standard errors.<br>
<b>Partial</b> beta: the index enters as it is — oil exposure <i>beyond</i> what the index already carries.
<b>Total</b> beta: the index is first stripped of its own oil component — what happens to the stock when Brent moves, through every channel.
Identity: total = partial + β<sub>mkt</sub> × (the index's own oil beta).</div>
<img src="{{ fig['01_sector_betas'] }}" alt="Sector oil betas">
<img src="{{ fig['02_market_rolling_beta'] }}" alt="Rolling oil beta of the index">
<img src="{{ fig['03_then_vs_now'] }}" alt="Full sample versus last five years">
<img src="{{ fig['04_sector_rolling_betas'] }}" alt="Rolling sector betas">

<div class="step" style="margin-top:50px">Step 3</div>
<h2 style="margin-top:4px">Event study: what happens when oil jumps</h2>
<p>A shock is any day where the Brent return exceeds {{ ev.z_threshold }} trailing standard deviations (volatility measured up to the day
before). Shocks within {{ ev.min_gap }} trading days of an accepted one are skipped, leaving {{ n_events }} events
({{ n_up }} up, {{ n_down }} down). Abnormal returns use a market model fitted on days {{ ev.estimation_window[0] }} to {{ ev.estimation_window[1] }}.</p>
<img src="{{ fig['05_event_paths'] }}" alt="Cumulative abnormal returns around oil shocks">
<div class="scroll">{{ event_table }}</div>
<p class="note">CAR = mean cumulative abnormal return over [0,+1], total measure (keeps everything oil did, removes other index noise).
Shock beta = slope of that CAR on the oil move across events. Down-shocks are preceded by a weak index
({{ pre_down }} over the five days before, t = {{ pre_down_t }}): many are demand scares, not supply news.</p>
<img class="narrow" src="{{ fig['06_shock_vs_weekly_beta'] }}" alt="Shock beta versus weekly beta">

<div class="step" style="margin-top:50px">Step 4</div>
<h2 style="margin-top:4px">Scenario table — and whether it deserves trust</h2>
<p>Expected move for a given Brent move, from total betas over the last {{ sc_years }} years. The interval covers uncertainty about the
<i>expected</i> move. <b>P(same sign)</b> is the chance the stock actually moves in that direction in a week where Brent moves
{{ "{:+.0%}".format(ref_shock) }}, given everything else that drives it.</p>
<div class="scroll">{{ scenario_agg }}</div>
<h3>Ten most and ten least oil-sensitive stocks</h3>
<div class="scroll">{{ scenario_stocks }}</div>
<img src="{{ fig['07_out_of_sample'] }}" alt="Out-of-sample test">
<p class="note">For each shock, betas are re-estimated using only weeks that ended before it. Top-minus-bottom tercile spread on the shock
days: {{ spread_impact }} (t = {{ spread_impact_t }}); in the following days: {{ spread_drift }} (t = {{ spread_drift_t }}).</p>

<div class="step" style="margin-top:50px">Step 5</div>
<h2 style="margin-top:4px">Regimes</h2>
<img src="{{ fig['08_asymmetry'] }}" alt="Up versus down oil beta">
<p>Splitting by trailing oil volatility instead (above or below its expanding median, known before the week starts) changes little:
the index's beta is {{ "%.2f"|format(vol.beta_calm) }} in calm and {{ "%.2f"|format(vol.beta_turbulent) }} in turbulent periods
(p = {{ "%.2f"|format(vol.p_diff) }}). The regime that matters is direction, not volatility.</p>

<div class="step" style="margin-top:50px">Step 6</div>
<h2 style="margin-top:4px">Side analysis: is there an oil factor in the returns themselves?</h2>
<img class="narrow" src="{{ fig['09_pca'] }}" alt="PCA loadings">
<p class="note">PC1 is the market. PC2 separates seafood from energy and has a {{ "%.2f"|format(pc2_oil) }} correlation with Brent:
returns alone do not single out oil as the second driver of Oslo Børs.</p>

<h2>All stocks</h2>
<img class="tall" src="{{ fig['10_stock_betas'] }}" alt="Oil beta by stock">

<h2>What this study cannot tell you</h2>
<ul class="tight"><li><b>Survivorship.</b> The universe is today's listings with Yahoo history. Names that have left Yahoo's Oslo feed (PGS, Seadrill, Golden Ocean, Flex LNG) are missing, so the sample is tilted towards survivors.</li>
<li><b>Correlation with a sign, not causation.</b> Brent moves for demand and supply reasons. A demand scare moves oil and equities together without oil causing anything.</li>
<li><b>Equal weights, hand-made sectors.</b> Sector portfolios are not investable indices; Equinor counts as much as Panoro.</li>
<li><b>USD oil, NOK stocks.</b> The krone's own oil sensitivity is part of the total beta by design and is not separated out.</li>
<li><b>Vendor data.</b> Yahoo adjustments contain errors; every one found is listed above, others may remain.</li></ul>
<p class="note" style="margin-top:40px">Generated by <code>oilbeta run</code>. Every number is in <code>results/tables/</code> and <code>results/oil_sensitivity.xlsx</code>; every assumption is in <code>configs/oslo.yaml</code>.</p>
</main></body></html>""")


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
    html = TEMPLATE.render(
        info=res.info, tiles=tiles, findings=_findings(res), fig=fig, notes=_data_notes(res),
        splice_date=cfg.market["splice_date"], ev=cfg.section("events"), n_events=len(ev),
        n_up=int((ev["direction"] == "up").sum()), n_down=int((ev["direction"] == "down").sum()),
        event_table=_event_table(res), pre_down=f"{pre['mean_car']:+.1%}", pre_down_t=f"{pre['t']:.1f}",
        scenario_agg=scenario_agg, scenario_stocks=scenario_stocks,
        sc_years=cfg.section("scenarios")["window"] // 52, ref_shock=float(T["scenarios"]["p_same_sign_shock"].iloc[0]),
        spread_impact=f"{oos.loc['spread_impact', 'mean']:+.1%}", spread_impact_t=f"{oos.loc['spread_impact', 't']:.1f}",
        spread_drift=f"{oos.loc['spread_drift', 'mean']:+.1%}", spread_drift_t=f"{oos.loc['spread_drift', 't']:.1f}",
        vol=T["regime_volatility"].loc[MARKET], pc2_oil=T["pca_summary"].loc["PC2", "OIL"],
    )
    out_path.write_text(html, encoding="utf-8")


def write_all(res: Results) -> dict[str, Path]:
    out = res.cfg.results_dir
    write_tables(res, out)
    figures = plots.save_all(res, out / "figures")
    write_html(res, figures, out / "report.html")
    dashboard.write(res, out)
    return {"report": out / "report.html", "dashboard": out / "dashboard.html", "workbook": out / "oil_sensitivity.xlsx", "tables": out / "tables",
            "figures": out / "figures"}
