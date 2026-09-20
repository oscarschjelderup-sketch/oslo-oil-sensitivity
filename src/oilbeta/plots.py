"""Figures. One visual system: thin marks, hairline grid, text in ink (never in series colour).

Series colours were checked with a colour-vision-deficiency validator (all pairs pass on a
white surface): blue / orange for the two poles of a comparison, green as a third slot.
Navy is the text and emphasis ink; grey de-emphasises.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter, MaxNLocator

from . import MARKET, OIL
from .pipeline import Results

BLUE, ORANGE, GREEN = "#005A9E", "#D9622B", "#1F9E78"
INK, MUTED, GRID, GREY = "#003255", "#5B6B75", "#E4E8EB", "#8F9DA6"

plt.rcParams.update({
    "font.family": "Arial", "font.size": 9, "text.color": INK,
    "axes.edgecolor": GRID, "axes.labelcolor": MUTED, "axes.titlesize": 10.5, "axes.titleweight": "bold",
    "axes.titlelocation": "left", "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
    "xtick.color": MUTED, "ytick.color": MUTED, "xtick.major.size": 0, "ytick.major.size": 0,
    "legend.frameon": False, "figure.dpi": 110, "savefig.dpi": 200, "savefig.bbox": "tight",
    "figure.facecolor": "white", "axes.facecolor": "white",
})

pct = FuncFormatter(lambda v, _: f"{v:+.0%}" if v else "0%")
pct1 = FuncFormatter(lambda v, _: f"{v:+.1%}" if v else "0%")

SHOCK_ERAS = [("2008-09-15", "Financial crisis"), ("2014-11-27", "OPEC no-cut"),
              ("2020-03-09", "Covid / price war"), ("2022-02-24", "Ukraine"), ("2026-02-28", "Hormuz")]


def _title(ax, title: str, subtitle: str | None = None) -> None:
    lines = len(subtitle.splitlines()) if subtitle else 0
    ax.set_title(title, pad=5 + 12.5 * lines)
    if subtitle:
        ax.text(0, 1.0, subtitle, transform=ax.transAxes, va="bottom", ha="left", color=MUTED, fontsize=8.5,
                linespacing=1.3)


def _zero(ax, vertical: bool = True) -> None:
    (ax.axvline if vertical else ax.axhline)(0, color=GREY, lw=0.9, zorder=1)


def _short(name: str) -> str:
    return name.replace("Consumer, telecom & real estate", "Consumer, telecom & RE")


# --------------------------------------------------------------------------
def sector_betas(res: Results):
    t = res.tables["betas_full"]
    t = t[t["kind"] != "stock"].sort_values("beta_oil_total")
    y = np.arange(len(t))
    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    _zero(ax)
    ax.hlines(y, t["total_lo"], t["total_hi"], color=BLUE, lw=1.6, zorder=2)
    ax.scatter(t["beta_oil_total"], y, s=46, color=BLUE, zorder=3, label="Total oil beta (95% CI)",
               edgecolor="white", linewidth=1.2)
    part = t["beta_oil_partial"]
    ax.scatter(part, y, s=40, facecolor="white", edgecolor=ORANGE, linewidth=1.6, zorder=3,
               label="Partial oil beta (index held fixed)")
    labels = ["Oslo Børs index" if u == MARKET else _short(u) for u in t.index]
    ax.set_yticks(y, labels)
    for tick, unit in zip(ax.get_yticklabels(), t.index):
        tick.set_color(INK)
        tick.set_fontweight("bold" if unit == MARKET else "normal")
    ax.set_xlabel("Change in weekly return per 1% change in Brent")
    ax.grid(axis="y", visible=False)
    ax.legend(loc="lower right", fontsize=8.5, handletextpad=0.3)
    span = f"{res.info['sample']['start'][:4]}–{res.info['sample']['end'][:4]}"
    _title(ax, "Every sector on Oslo Børs rises with oil, but only energy carries extra oil risk",
           f"Weekly returns {span}, Newey-West intervals. Outside energy the partial beta is zero or negative:\n"
           "the oil exposure of banks or seafood is simply the index's own oil exposure.")
    return fig


def stock_betas(res: Results):
    t = res.tables["betas_full"]
    t = t[t["kind"] == "stock"].copy()
    order = t.groupby("sector")["beta_oil_total"].mean().sort_values(ascending=False).index
    fig, ax = plt.subplots(figsize=(7.2, 13.5))
    _zero(ax)
    y, ticks, names = 0, [], []
    for sector in order:
        g = t[t["sector"] == sector].sort_values("beta_oil_total", ascending=False)
        ax.annotate(_short(sector), (0, y - 0.62), xycoords=("axes fraction", "data"), xytext=(-150, 0),
                    textcoords="offset points", fontsize=8.5, fontweight="bold", color=INK, va="center",
                    annotation_clip=False)
        y += 0.55
        for unit, row in g.iterrows():
            sig = row["total_lo"] > 0 or row["total_hi"] < 0
            colour = BLUE if sig else GREY
            ax.hlines(y, row["total_lo"], row["total_hi"], color=colour, lw=1.3, zorder=2)
            ax.scatter(row["beta_oil_total"], y, s=26, color=colour, zorder=3, edgecolor="white", linewidth=0.9)
            ticks.append(y)
            names.append(row["name"])
            y += 1
        y += 0.9
    ax.set_yticks(ticks, names, fontsize=8)
    for tick in ax.get_yticklabels():
        tick.set_color(MUTED)
    ax.set_ylim(y - 0.6, -1.4)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Total oil beta (weekly, full available history)")
    ax.scatter([], [], s=26, color=BLUE, label="95% interval excludes zero")
    ax.scatter([], [], s=26, color=GREY, label="Not distinguishable from zero")
    ax.legend(loc="lower right", fontsize=8.5, handletextpad=0.3)
    _title(ax, "Total oil beta by stock", "Dot = estimate, line = 95% Newey-West interval. Sectors ordered by average beta.")
    return fig


def market_rolling(res: Results):
    r = res.tables["betas_rolling"]
    r = r[r["unit"] == MARKET].set_index("date")
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    _zero(ax, vertical=False)
    ax.fill_between(r.index, r["total_lo"], r["total_hi"], color=BLUE, alpha=0.16, lw=0)
    ax.plot(r.index, r["beta_oil_total"], color=BLUE, lw=1.8)
    top = r["total_hi"].max()
    for i, (date, label) in enumerate(SHOCK_ERAS):
        d = pd.Timestamp(date)
        if r.index.min() <= d <= r.index.max():
            ax.axvline(d, color=GREY, lw=0.7, zorder=1)
            ax.text(d, top * (1.04 + 0.09 * (i % 2)), f" {label}", fontsize=7.5, color=MUTED, va="bottom", ha="left")
    last = r.iloc[-1]
    ax.annotate(f"{last['beta_oil_total']:.2f}", (r.index[-1], last["beta_oil_total"]), xytext=(5, 0),
                textcoords="offset points", va="center", fontsize=9, fontweight="bold", color=INK)
    ax.set_ylim(top=top * 1.24)
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.grid(axis="x", visible=False)
    window = res.cfg.section("betas")["rolling_window"]
    _title(ax, "Oslo Børs has become less of an oil bet",
           f"Oil beta of the benchmark index, rolling {window}-week windows, 95% interval. Vertical lines: major oil events.")
    return fig


def sector_rolling(res: Results):
    r = res.tables["betas_rolling"]
    full = res.tables["betas_full"]
    sectors = full[full["kind"] == "sector"].sort_values("beta_oil_total", ascending=False).index
    fig, axes = plt.subplots(5, 2, figsize=(7.2, 9.2), sharex=True, sharey=True)
    for ax, sector in zip(axes.ravel(), sectors):
        g = r[r["unit"] == sector].set_index("date")
        _zero(ax, vertical=False)
        ax.fill_between(g.index, g["total_lo"], g["total_hi"], color=BLUE, alpha=0.16, lw=0)
        ax.plot(g.index, g["beta_oil_total"], color=BLUE, lw=1.4)
        ax.set_title(_short(sector), fontsize=9, pad=4)
        ax.xaxis.set_major_locator(mdates.YearLocator(4))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        ax.grid(axis="x", visible=False)
    fig.suptitle("Rolling total oil beta by sector (104-week windows, 95% interval)", x=0.02, ha="left",
                 fontsize=10.5, fontweight="bold", color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.975))
    return fig


def then_vs_now(res: Results):
    full, recent = res.tables["betas_full"], res.tables["scenarios"]
    t = full[full["kind"] != "stock"][["beta_oil_total"]].join(recent[["beta_oil_total"]], rsuffix="_recent")
    t = t.sort_values("beta_oil_total_recent")
    y = np.arange(len(t))
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    _zero(ax)
    ax.hlines(y, t["beta_oil_total"], t["beta_oil_total_recent"], color=GRID, lw=2.2, zorder=1)
    ax.scatter(t["beta_oil_total"], y, s=44, color=GREY, zorder=3, edgecolor="white", linewidth=1.2,
               label=f"Full sample ({res.info['sample']['start'][:4]}–)")
    years = res.cfg.section("scenarios")["window"] // 52
    ax.scatter(t["beta_oil_total_recent"], y, s=44, color=BLUE, zorder=3, edgecolor="white", linewidth=1.2,
               label=f"Last {years} years")
    ax.set_yticks(y, ["Oslo Børs index" if u == MARKET else _short(u) for u in t.index])
    for tick in ax.get_yticklabels():
        tick.set_color(INK)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Total oil beta")
    ax.legend(loc="lower right", fontsize=8.5, handletextpad=0.3)
    _title(ax, "Outside energy and shipping, the oil link has faded to roughly zero",
           "Banks, seafood, technology and consumer stocks no longer move with Brent; energy betas are lower but intact.")
    return fig


def event_paths(res: Results):
    p = res.tables["event_paths"]
    full = res.tables["betas_full"]
    pick = [OIL, MARKET, "Exploration & production", "Oil service & drilling", "Banks & insurance", "Seafood"]
    titles = {OIL: "Brent itself", MARKET: "Oslo Børs index"}
    fig, axes = plt.subplots(2, 3, figsize=(7.2, 4.9), sharex=True)
    for ax, unit in zip(axes.ravel(), pick):
        _zero(ax, vertical=False)
        ax.axvspan(-0.5, 1.5, color=GRID, alpha=0.55, lw=0, zorder=0)
        for direction, colour in (("up", BLUE), ("down", ORANGE)):
            g = p[(p["unit"] == unit) & (p["direction"] == direction)].sort_values("day")
            ax.fill_between(g["day"], g["mean_car"] - 1.96 * g["se"], g["mean_car"] + 1.96 * g["se"],
                            color=colour, alpha=0.14, lw=0)
            ax.plot(g["day"], g["mean_car"], color=colour, lw=1.6,
                    label=f"Oil up-shocks (n={int(g['n_events'].max())})" if direction == "up"
                    else f"Oil down-shocks (n={int(g['n_events'].max())})")
        ax.set_title(titles.get(unit, _short(unit)), fontsize=9, pad=4)
        ax.yaxis.set_major_locator(MaxNLocator(nbins=5, steps=[1, 2, 4, 5, 10]))
        ax.yaxis.set_major_formatter(pct)
        ax.grid(axis="x", visible=False)
        ax.set_xticks([-5, 0, 5, 10])
    for ax in axes[1]:
        ax.set_xlabel("Trading days from the shock")
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper left", ncol=2, fontsize=8.5, bbox_to_anchor=(0.01, 0.915))
    thr = res.cfg.section("events")["z_threshold"]
    fig.suptitle("Stocks react within two days; after that they simply follow oil's own path",
                 x=0.02, ha="left", fontsize=10.5, fontweight="bold", color=INK)
    fig.text(0.02, 0.925, f"Mean cumulative abnormal return around |Brent move| > {thr}σ days, re-based to the close "
             "before the shock. Shaded: impact window [0,+1].", fontsize=8.5, color=MUTED)
    fig.tight_layout(rect=(0, 0, 1, 0.87))
    return fig


def shock_vs_weekly(res: Results):
    t = res.tables["betas_full"].join(res.tables["shock_betas"], how="inner")
    t = t[t["kind"] == "stock"]
    energy = t["sector"].isin(["Exploration & production", "Oil service & drilling"])
    fig, ax = plt.subplots(figsize=(5.6, 5.0))
    lim = (min(t["beta_oil_total"].min(), t["shock_beta"].min()) - 0.08,
           max(t["beta_oil_total"].max(), t["shock_beta"].max()) + 0.08)
    ax.plot(lim, lim, color=GREY, lw=0.9, zorder=1)
    ax.text(lim[1] - 0.02, lim[1] - 0.06, "equal", color=MUTED, fontsize=8, ha="right", rotation=38)
    ax.scatter(t.loc[~energy, "beta_oil_total"], t.loc[~energy, "shock_beta"], s=34, color=GREY,
               edgecolor="white", linewidth=1, label="Other sectors", zorder=2)
    ax.scatter(t.loc[energy, "beta_oil_total"], t.loc[energy, "shock_beta"], s=34, color=BLUE,
               edgecolor="white", linewidth=1, label="E&P and oil service", zorder=3)
    offsets = {"EQNR.OL": (-6, 6, "right"), "DNO.OL": (6, -9, "left"), "FRO.OL": (6, -9, "left"),
               "DNB.OL": (7, -3, "left"), "PEN.OL": (-6, 5, "right")}
    for unit, (dx, dy, ha) in offsets.items():
        if unit in t.index:
            ax.annotate(t.loc[unit, "name"], (t.loc[unit, "beta_oil_total"], t.loc[unit, "shock_beta"]),
                        xytext=(dx, dy), textcoords="offset points", fontsize=7.5, color=MUTED, ha=ha)
    rho = t["beta_oil_total"].corr(t["shock_beta"])
    ax.set_xlim(lim), ax.set_ylim(lim)
    ax.set_xlabel("Weekly total oil beta (all weeks)")
    ax.set_ylabel("Shock beta (two-day reaction to large oil moves)")
    ax.legend(loc="upper left", fontsize=8.5, handletextpad=0.2)
    _title(ax, "Two independent methods agree", f"One dot per stock. Correlation {rho:.2f}.")
    return fig


def out_of_sample(res: Results):
    o, s = res.tables["oos_events"], res.tables["oos_summary"]
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.5), sharey=True)
    spec = [("spearman_impact", "Reaction on the shock days [0,+1]", BLUE),
            ("spearman_drift", "Drift afterwards [+2,+10]", GREY)]
    for ax, (col, title, colour) in zip(axes, spec):
        _zero(ax, vertical=False)
        ax.scatter(o["date"], o[col], s=24, color=colour, edgecolor="white", linewidth=0.8, zorder=3)
        mean = s.loc[col, "mean"]
        ax.axhline(mean, color=INK, lw=1.3, zorder=2)
        stats_line = (f"mean {mean:+.2f}, t = {s.loc[col, 't']:.1f}, "
                      f"positive in {s.loc[col, 'share_positive']:.0%} of shocks")
        ax.set_title("\n".join([title, stats_line]), fontsize=9, pad=4, linespacing=1.35)
        ax.xaxis.set_major_locator(mdates.YearLocator(4))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        ax.grid(axis="x", visible=False)
    axes[0].set_ylabel("Rank correlation, predicted vs realised")
    fig.suptitle("Betas from the past rank the winners in the next shock, but do not predict what follows",
                 x=0.02, ha="left", fontsize=10.5, fontweight="bold", color=INK)
    fig.text(0.02, 0.9, "One dot per oil shock. Prediction = beta estimated only on earlier data × the oil move.",
             fontsize=8.5, color=MUTED)
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    return fig


def asymmetry(res: Results):
    t = res.tables["regime_direction"]
    t = t[t["kind"] != "stock"].sort_values("beta_down")
    y = np.arange(len(t))
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    _zero(ax)
    ax.hlines(y, t["beta_up"], t["beta_down"], color=GRID, lw=2.2, zorder=1)
    ax.scatter(t["beta_up"], y, s=44, color=BLUE, zorder=3, edgecolor="white", linewidth=1.2, label="Weeks when oil rises")
    ax.scatter(t["beta_down"], y, s=44, color=ORANGE, zorder=3, edgecolor="white", linewidth=1.2, label="Weeks when oil falls")
    labels = []
    for unit, row in t.iterrows():
        star = " *" if row["p_diff"] < 0.05 else ""
        labels.append(("Oslo Børs index" if unit == MARKET else _short(unit)) + star)
    ax.set_yticks(y, labels)
    for tick in ax.get_yticklabels():
        tick.set_color(INK)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Total oil beta")
    ax.legend(loc="lower right", fontsize=8.5, handletextpad=0.3)
    _title(ax, "Oil hurts on the way down more than it helps on the way up",
           "* difference significant at 5%. Falling oil often coincides with global risk-off:\n"
           "this is co-movement, not a pure oil effect.")
    return fig


def pca_loadings(res: Results):
    l = res.tables["pca_loadings"].join(res.meta[["name", "sector"]])
    s = res.tables["pca_summary"]
    groups = {"E&P and oil service": (l["sector"].isin(["Exploration & production", "Oil service & drilling"]), BLUE),
              "Seafood": (l["sector"] == "Seafood", ORANGE)}
    other = ~(groups["E&P and oil service"][0] | groups["Seafood"][0])
    fig, ax = plt.subplots(figsize=(5.6, 4.6))
    _zero(ax, vertical=False)
    ax.scatter(l.loc[other, "PC1"], l.loc[other, "PC2"], s=34, color=GREY, edgecolor="white", linewidth=1, label="Other")
    for label, (mask, colour) in groups.items():
        ax.scatter(l.loc[mask, "PC1"], l.loc[mask, "PC2"], s=34, color=colour, edgecolor="white", linewidth=1, label=label)
    ax.set_xlabel(f"Loading on PC1 ({s.loc['PC1', 'variance_share']:.0%} of variance, corr. with index {s.loc['PC1', MARKET]:.2f})")
    ax.set_ylabel(f"Loading on PC2 ({s.loc['PC2', 'variance_share']:.0%}, corr. with Brent {s.loc['PC2', OIL]:.2f})")
    ax.legend(loc="center left", bbox_to_anchor=(0.0, 0.36), fontsize=8.5, handletextpad=0.2)
    _title(ax, "The second factor is mostly salmon; oil shows up only weakly",
           f"PCA on weekly returns of {res.info['pca']['n_stocks']} stocks with full history. No oil data goes in.")
    return fig


FIGURES = {
    "01_sector_betas": sector_betas,
    "02_market_rolling_beta": market_rolling,
    "03_then_vs_now": then_vs_now,
    "04_sector_rolling_betas": sector_rolling,
    "05_event_paths": event_paths,
    "06_shock_vs_weekly_beta": shock_vs_weekly,
    "07_out_of_sample": out_of_sample,
    "08_asymmetry": asymmetry,
    "09_pca": pca_loadings,
    "10_stock_betas": stock_betas,
}


def save_all(res: Results, out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, make in FIGURES.items():
        fig = make(res)
        paths[name] = out_dir / f"{name}.png"
        fig.savefig(paths[name])
        plt.close(fig)
    return paths
