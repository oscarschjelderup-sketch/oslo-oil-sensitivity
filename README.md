# How much oil is left in Oslo Børs?

[![CI](https://github.com/oscarschjelderup-sketch/oslo-oil-sensitivity/actions/workflows/ci.yml/badge.svg)](https://github.com/oscarschjelderup-sketch/oslo-oil-sensitivity/actions/workflows/ci.yml)
[![Live monitor](https://github.com/oscarschjelderup-sketch/oslo-oil-sensitivity/actions/workflows/live-monitor.yml/badge.svg)](https://github.com/oscarschjelderup-sketch/oslo-oil-sensitivity/actions/workflows/live-monitor.yml)

**Live monitor, rebuilt after every trading day: https://oscarschjelderup-sketch.github.io/oslo-oil-sensitivity/**

**A factor study of 63 Norwegian stocks and 10 sectors, 2007–2026: how much each one moves when Brent moves, how sure
we can be about it, and whether that knowledge survives an out-of-sample test.**

```bash
oilbeta run
```

![Rolling oil beta of the Oslo Børs benchmark index](results/figures/02_market_rolling_beta.png)

Everyone "knows" Oslo Børs is an oil market. This project measures it properly and finds that the statement is about a
decade out of date: the benchmark's oil beta averaged **0.49** up to 2013 and is **0.13** today. Outside energy and
shipping, the link to oil over the last five years cannot be told apart from zero.

| | |
|---|---|
| ![Sector betas](results/figures/01_sector_betas.png) | ![Full sample vs last five years](results/figures/03_then_vs_now.png) |
| ![Event study](results/figures/05_event_paths.png) | ![Out-of-sample test](results/figures/07_out_of_sample.png) |

The full write-up is the [research report](https://oscarschjelderup-sketch.github.io/oslo-oil-sensitivity/paper/report.html); every number behind it is in
[results/tables/](results/tables) and in the workbook attached to the [latest paper release](https://github.com/oscarschjelderup-sketch/oslo-oil-sensitivity/releases/latest).

## Findings

1. **The oil beta of Oslo Børs has fallen from 0.49 to 0.13.** Over the full sample a 10% move in Brent has come with a
   2.9% move in the index (95% interval 2.1–3.6%).
2. **Only energy carries oil risk beyond the index.** Once the index is held fixed, 16 of 63 stocks keep a significantly
   positive oil beta, and 15 of them are E&P or oil service. Seventeen have a significantly *negative* partial beta, led
   by Norwegian Air Shuttle (−0.32), where fuel is a cost.
3. **Oil shocks are priced within two days.** Across 69 rule-based shocks the reaction lands on the shock day and the
   day after. Betas measured only on those days agree with ordinary weekly betas (correlation 0.89 across stocks).
4. **Sensitivity is stable; predictability is absent.** Betas estimated only on past data rank stocks correctly in the
   *next* shock: mean rank correlation +0.28 (t = 10.5), positive in 90% of shocks. The same ranking says nothing about
   the days that follow (−0.01, t = −0.3). This is a risk tool, not a trading signal, and the report says so.
5. **The downside beta is larger — because the downside is where the demand scares are.** The index's oil beta is 0.37
   in weeks when oil falls and 0.19 when it rises (p = 0.012). Labelling each shock by whether the S&P 500 moved with
   oil or against it: 79% of the large declines are demand-type against 50% of the large rises. The index reacts with a
   beta of 0.30 to demand-type shocks and 0.09 to supply-type ones (p = 0.002); E&P reacts the same to both (0.56 and
   0.57). Energy responds to the oil price, the rest of the market mostly to the news that moved it.
6. **The high betas were a crash-era level, and nothing depends on the vendor.** Re-running everything on Brent *spot*
   from FRED instead of the Yahoo future gives an index beta of 0.25 against 0.29 and the same stock ranking (rank
   correlation 0.99). Starting the sample in 2005 instead of 2007: two-year windows ending before the autumn-2008 crash
   average 0.23, windows ending 2009–2013 average 0.51, and the average since 2015 is 0.21. So the "decline" is largely
   the 2008 crash leaving the rolling window.

## Two modes: a pinned paper and a live monitor

| | `oilbeta run` | `oilbeta live` |
|---|---|---|
| Purpose | The research report: numbers that can be cited and reproduced | The monitor: how much oil is in Oslo Børs *now* |
| Sample end | Fixed in the config | Yesterday's close, every time it runs |
| Output | `results/` (committed): narrative report, figures, workbook | `live/` (git-ignored): interactive dashboard, tables, workbook |
| Text | Written findings, checked against the snapshot | No hard-coded claims: every sentence is assembled from the numbers |

`oilbeta live` re-downloads prices, re-estimates every beta, re-runs the event study and rebuilds
`live/dashboard.html`, a single self-contained page with a Brent what-if slider, rolling betas with intervals for any
stock, and a predicted-versus-realised scorecard that gains a row each time Brent has a shock. A new shock enters as
soon as its two-day impact window exists; its drift window stays empty until those days have happened, never a partial
sum. If the download fails, the last good snapshot is served and the page says so.

### How it runs

GitHub Actions is the run model; nothing has to be switched on anywhere.

- [live-monitor.yml](.github/workflows/live-monitor.yml) runs at 05:30 UTC the morning after each trading day (and on
  every change to the code): it installs the locked environment, runs `oilbeta live --retries 3` and deploys the page,
  the pinned report and the workbook to GitHub Pages. Yahoo sometimes throttles cloud IPs, so the last good price
  snapshot is kept in the Actions cache and served, visibly marked, when a download fails. The job only goes red when
  the page has been stale for more than a week.
- [ci.yml](.github/workflows/ci.yml) lints and runs the test suite on every push and pull request.
- For a local refresh on a schedule there is [scripts/update_live.ps1](scripts/update_live.ps1) (Windows Task Scheduler).

## What it does

```mermaid
flowchart LR
    subgraph "1 Data"
        Y[Yahoo Finance<br/>63 stocks · Brent · OSEBX] --> S[(pinned snapshot<br/>+ manifest)]
        S --> A[common calendar<br/>returns after alignment]
        A --> V[validation report<br/>documented exceptions]
    end
    subgraph "2 Betas"
        A --> B[two-factor OLS<br/>Newey-West intervals]
        B --> R[rolling 104-week betas]
    end
    subgraph "3 Events"
        A --> E[rule-based oil shocks<br/>no look-ahead]
        E --> C[abnormal returns<br/>CAR windows]
    end
    subgraph "4–6 Use and stress"
        B --> SC[scenario table]
        C --> O[out-of-sample<br/>rank test]
        B --> G[regimes:<br/>up/down · calm/turbulent]
        A --> P[PCA on returns]
    end
    SC & O & G & P & R --> OUT[HTML report · Excel · CSV · figures]
```

| Step | Question | Method |
|---|---|---|
| 1 Data | Can the inputs be trusted and reproduced? | Fixed end date, SHA-256 manifest, returns computed *after* calendar alignment, equal-weighted sector portfolios from constituents only, every manual fix listed in the config with its reason |
| 2 Betas | How much does each stock move with oil? | `r = α + β_mkt·OSEBX + β_oil·Brent + ε` on weekly returns, Newey-West errors, full-sample and rolling. Reports a *partial* and a *total* oil beta (see below) |
| 3 Events | What happens when oil jumps? | Shocks = Brent moves above 2.5 trailing σ, de-clustered; market-model abnormal returns; CARs over [−5,−1], [0,+1], [+2,+10] |
| 4 Scenarios | What should I expect if Brent moves 10%? And should I believe it? | Expected move with interval from recent betas, the probability the stock actually moves that way, and an out-of-sample rank test on shocks the betas never saw |
| 5 Regimes | Is the beta the same up and down, calm and turbulent? | Split-beta regressions with equality tests; regime flags use only past information |
| 6 PCA | Do returns alone reveal an oil factor? | PCA on the cross-section of weekly returns (not on engineered columns) |
| + Shock types | Is this the effect of oil, or of the news that moved oil? | Each shock labelled demand-type or supply-type by the sign of the S&P 500 move over the same two days; separate shock betas, an equality test, and a version that holds the world move fixed |
| + Robustness | Does the answer depend on the vendor or on where the sample starts? | The whole beta step re-run with Brent spot from FRED, and with stock prices from 2005 |

Across units, p-values come with Benjamini-Hochberg q-values: with 63 stocks, a 5% test alone produces about three
"significant" betas from nothing. The report and figures use a 5% false discovery rate.

### Partial versus total oil beta

Oslo Børs is itself oil-heavy, so controlling for the index hides part of every stock's oil exposure inside its market
beta. The project therefore reports two numbers that answer two questions:

- **Partial beta**: the index enters the regression as it is. *Does this stock carry oil risk beyond what the index
  already has?* For DNB the answer is no (−0.07).
- **Total beta**: the index is first stripped of its own oil component. *If Brent moves 10%, what happens to this
  stock through every channel?* For DNB over the full sample: +0.29.

They are tied by an identity that the test suite checks to machine precision:
`total = partial + β_mkt × (the index's own oil beta)`.

## Quick start

```bash
uv sync --extra dev         # exact, locked environment (uv.lock); or: pip install -e ".[dev]"
oilbeta run                 # all six steps on the pinned snapshot -> results/
oilbeta live                # same model on prices up to yesterday -> live/dashboard.html
oilbeta fetch               # data snapshot + validation report only
oilbeta stock NAS.OL        # one stock, including tickers outside the configured universe
oilbeta stock EQNR.OL --json oil/EQNR.OL.json   # the same, as a factsheet another tool can read
pytest tests/unit           # 56 fast tests (~10 s); plain `pytest` adds the two golden tests (~1 min)
ruff check .                # lint
```

`oilbeta run --refresh` downloads a new snapshot. Without it the cached snapshot is reused, so results are identical
from run to run. Everything that shapes the results lives in three validated files under [configs/](configs):
[study.yaml](configs/study.yaml) (sample, factors, windows, thresholds), [universe.yaml](configs/universe.yaml)
(stocks and sectors) and [data_exceptions.yaml](configs/data_exceptions.yaml) (every manual data fix, with its
reason). Unknown keys, impossible windows, a ticker in two sectors or a data fix without a reason stop the run.

## Design decisions worth defending

- **Weekly returns for betas, daily for events.** Oslo closes about six hours before Brent settles. Friday-to-Friday
  returns dilute that gap and the stale prices of small caps; the event study handles it by using a two-day impact
  window.
- **Standard errors written out in numpy.** OLS and the Newey-West covariance are ~40 lines in
  [regression.py](src/oilbeta/regression.py), tested against scipy, against White's estimator at lag zero and against
  a naive double-loop implementation.
- **Flags, never silent fixes.** The validation step found four vendor errors (an unadjusted NOK 21 extraordinary
  dividend in Aker Solutions that shows up as a −41% day, two mis-applied share consolidations) and one ticker whose
  early history is a different company (Nel was DiaGenic until 2014). Each is removed by an explicit line in the config.
  Real crashes (Norwegian 2020, Frontline 2011) stay in.
- **No look-ahead anywhere.** Shock thresholds use volatility up to the day before; regime flags use an expanding
  median; out-of-sample betas use only weeks that ended before each event. Each has a test that tampers with the
  future and checks the past does not change.
- **The numbers are locked twice.** `uv.lock` pins every dependency, and two golden tests pin the results: one re-runs
  the study on the pinned snapshot and compares 22 headline numbers with the README (wherever the raw prices exist),
  the other pushes a seeded synthetic market through the whole chain, report and dashboard included, on every push.
  A refactor cannot move a number without a test going red.
- **Null results are reported.** The drift test and the volatility-regime split find nothing, and the report shows them.

## What this study cannot tell you

- **Survivorship.** The universe is today's listings with Yahoo history. PGS, Seadrill, Golden Ocean and Flex LNG are
  no longer on Yahoo's Oslo feed, so the sample is tilted towards survivors.
- **Co-movement, not causation.** Brent moves for demand and supply reasons. The shock-type split measures how much
  that matters (it is most of the non-energy oil beta) but does not remove it: the label is assigned after the fact,
  from the same two days as the reaction it explains.
- **Equal weights, hand-made sectors.** Sector portfolios are not investable indices.
- **USD oil, NOK stocks.** The krone's own oil sensitivity is part of the total beta by design.
- **One vendor for stock prices.** The oil series is cross-checked against FRED, but the Oslo prices are Yahoo's alone.
- **Index history is spliced.** OSEBX on Yahoo starts in 2013; earlier returns come from OSEFX (0.99 return
  correlation in the 625-day overlap, re-checked on every fetch).

Methodology in full: [docs/methodology.md](docs/methodology.md).

## Repository layout

```
configs/
  study.yaml               sample, factors, windows, thresholds
  universe.yaml            63 stocks in 10 sectors
  data_exceptions.yaml     every manual data fix, with its reason
src/oilbeta/
  config.py                pydantic models: the three files are validated before anything runs
  data/                    sources.py (Yahoo, FRED) · snapshot.py (cache, manifest) · align.py · validate.py
  stats/                   ols.py · hac.py · multiple.py: numpy only, arrays in and numbers out
  analysis/                betas · events · shocktype · scenarios · regimes · pca · robustness
  outputs/                 tables · figures · report · dashboard · templates/
  pipeline.py  cli.py      the six steps in order, and the `oilbeta` command
tests/
  unit/                    config, data, sources, stats, analysis, shock types, live mode: synthetic data with known answers
  integration/             golden tests: the pinned snapshot's numbers, and a synthetic market end to end
docs/
  methodology.md           every formula and parameter
  decisions/               eight short notes on why it is built this way
.github/workflows/         ci.yml (lint + tests) · live-monitor.yml (scheduled rebuild + GitHub Pages)
scripts/update_live.ps1    optional local refresh
uv.lock                    locked environment
results/                   tables and figures of the pinned snapshot (the report and workbook are release assets)
live/                      output of `oilbeta live` (git-ignored, rebuilt on every refresh)
data/manifest.json         what was downloaded, when, and its SHA-256 (raw prices are not redistributed)
```

The layering is one-way: `stats` knows nothing about pandas or tickers, `analysis` knows nothing about files, and
`outputs` never computes a result. Why things are built the way they are is written down in
[docs/decisions/](docs/decisions/README.md).

## Feeding a valuation case

`oilbeta stock <TICKER> --json <path>` writes a small versioned document (schema `oilbeta.stock/1`) with both betas,
their intervals, the scenarios, the share of weekly variance oil explains — and the caveats above, so they travel with
the numbers.

The companion project [equity-research-engine](https://github.com/oscarschjelderup-sketch/equity-research-engine) reads it into the risk section of an investment case, which then
states a measured exposure instead of the usual sentence about commodity prices:

> **Oil price:** a 20% fall in Brent has come with an 8.4% fall in the share (5.2% to 11.5% interval, 260 weeks to
> 2026-09-11); that is oil risk beyond the index's own. Oil explains 19% of weekly variance and the move goes that way
> 98% of the time. *— Subsea 7*

> **Oil price:** no measurable direct exposure — an interval of −0.04 to +0.09 that spans zero; a higher oil price has
> been a cost: holding the index fixed, the share has moved −0.12% per 1% move in Brent. *— Mowi*

The two projects share the schema, not an import, so either can be rewritten independently. On the engine's side the
factsheet is context and never a driver: it does not touch the forecast, the WACC or the DCF, and a test there asserts a
case runs to identical numbers with and without it.

Data: Yahoo Finance via `yfinance`. For education and research; not investment advice. MIT licence.
