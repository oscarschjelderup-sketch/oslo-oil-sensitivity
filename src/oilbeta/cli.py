"""Command line: `oilbeta run` (pinned research), `oilbeta live` (moving monitor), `fetch`, `stock EQNR.OL`."""
from __future__ import annotations

import warnings
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from . import MARKET, OIL, data, outputs, pipeline
from .analysis import betas
from .config import load_config

app = typer.Typer(add_completion=False, help="Oil-price sensitivity of Oslo Børs stocks and sectors.")
console = Console()
DEFAULT_CONFIG = Path("configs")


@app.callback()
def _quiet() -> None:
    warnings.filterwarnings("ignore", category=FutureWarning)


@app.command()
def fetch(config: Path = DEFAULT_CONFIG, refresh: bool = typer.Option(False, help="Re-download from Yahoo.")):
    """Download (or load) the price snapshot and print the validation report."""
    cfg = load_config(config)
    prices = data.fetch_prices(cfg, refresh=refresh)
    panel = data.build_panel(prices, cfg)
    report_df = data.validate(panel, cfg)
    splice = data.splice_diagnostics(prices, cfg)
    console.print(f"[bold]{len(panel):,}[/] common trading days, {panel.index.min().date()} to {panel.index.max().date()}")
    console.print(f"Index splice check: correlation {splice['return_correlation']} over {splice['overlap_days']} overlap days")
    table = Table("Series", "From", "Weeks", "Zero-return days", "Max |daily|", "Flags")
    for _, r in report_df[report_df["flags"] != "ok"].iterrows():
        table.add_row(r["series"], str(r["first"]), str(r["weekly_obs"]), f"{r['zero_return_share']:.0%}",
                      f"{r['max_abs_daily_return']:.0%}", r["flags"])
    console.print(table if table.row_count else "[green]No flags.[/]")


@app.command()
def run(config: Path = DEFAULT_CONFIG, refresh: bool = typer.Option(False, help="Re-download from Yahoo first.")):
    """Run all six steps and write tables, workbook, figures and the HTML report."""
    cfg = load_config(config)
    res = pipeline.run(cfg, refresh=refresh, log=lambda msg: console.print(f"[dim]{msg}[/]"))
    paths = outputs.write_all(res)
    full, oos = res.tables["betas_full"], res.tables["oos_summary"]
    console.print(f"\nOslo Børs oil beta: [bold]{full.loc[MARKET, 'beta_oil_total']:.2f}[/] "
                  f"({full.loc[MARKET, 'total_lo']:.2f} to {full.loc[MARKET, 'total_hi']:.2f})")
    console.print(f"Out-of-sample rank correlation on shock days: [bold]{oos.loc['spearman_impact', 'mean']:+.2f}[/] "
                  f"(t = {oos.loc['spearman_impact', 't']:.1f}); in the days after: {oos.loc['spearman_drift', 'mean']:+.2f}")
    for label, path in paths.items():
        console.print(f"  {label:<9} {path}")


@app.command()
def live(config: Path = DEFAULT_CONFIG,
         offline: bool = typer.Option(False, help="Rebuild from the cached live snapshot without downloading."),
         retries: int = typer.Option(0, help="Extra download attempts before falling back to the cached snapshot.")):
    """Refresh prices up to yesterday's close, re-estimate everything and rebuild the live monitor."""
    cfg = load_config(config).as_live()
    res = pipeline.run(cfg, refresh=not offline, retries=retries, log=lambda msg: console.print(f"[dim]{msg}[/]"))
    paths = outputs.write_live(res)
    now = res.tables["betas_rolling"].query("unit == @MARKET").iloc[-1]
    state = ("[yellow]cached data (download failed)[/]" if res.info["stale"]
             else "cached snapshot (offline rebuild)" if offline else "[green]fresh data[/]")
    console.print()
    console.print(f"Prices through [bold]{res.panel.index.max().date()}[/], {state}")
    console.print(f"Index oil beta, latest window: [bold]{now['beta_oil_total']:.2f}[/] "
                  f"({now['total_lo']:.2f} to {now['total_hi']:.2f}); {len(res.tables['events'])} oil shocks in the sample")
    console.print(f"  monitor   {paths['dashboard']}")


@app.command()
def stock(ticker: str, config: Path = DEFAULT_CONFIG,
          json_out: Path = typer.Option(None, "--json", help="Also write a factsheet another tool can read (schema oilbeta.stock/1).")):
    """Oil sensitivity of one stock (any Yahoo ticker on the Oslo calendar, not only the configured universe)."""
    cfg = load_config(config)
    prices = data.fetch_prices(cfg)
    if ticker not in prices:
        import yfinance as yf
        extra = yf.download(ticker, start=cfg.start, end=cfg.end, auto_adjust=True, progress=False)["Close"]
        prices[ticker] = extra.squeeze().reindex(prices.index)
        cfg = cfg.with_stock(ticker)
    panel = data.build_panel(prices, cfg)
    weekly = data.weekly_returns(panel, cfg)
    window = cfg.scenarios.window
    table = Table("Sample", "Weeks", "Market beta", "Oil beta (partial)", "Oil beta (total)", "95% interval", "Brent +10%")
    for label, w in (("Full history", weekly), (f"Last {window // 52} years", weekly.iloc[-window:])):
        est = betas.oil_betas(w[ticker].to_numpy(), w[MARKET].to_numpy(), w[OIL].to_numpy())
        table.add_row(label, str(est["nobs"]), f"{est['beta_mkt']:.2f}", f"{est['beta_oil_partial']:+.2f}",
                      f"{est['beta_oil_total']:+.2f}", f"{est['total_lo']:+.2f} to {est['total_hi']:+.2f}",
                      f"{(1.1 ** est['beta_oil_total'] - 1):+.1%}")
    console.print(f"[bold]{cfg.names.get(ticker, ticker)}[/]")
    console.print(table)
    if json_out:
        sectors = data.sector_returns(weekly, cfg)
        frame, meta = betas.units_frame(weekly, sectors, cfg)
        table_all = betas.beta_table(frame[sectors.columns], meta, weekly[[MARKET, OIL]], cfg.betas.min_history)
        doc = outputs.factsheet.build(cfg, weekly, ticker, sector_betas=table_all)
        console.print(f"  factsheet {outputs.factsheet.write(doc, json_out)}")


if __name__ == "__main__":
    app()
