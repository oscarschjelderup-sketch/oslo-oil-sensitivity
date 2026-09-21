# Methodology

Every choice below maps to a line in [configs/](../configs) or a function in `src/oilbeta/`. The reasoning behind the
main choices is in [decisions/](decisions/README.md).

## 1. Data

**Source.** Auto-adjusted daily closes from Yahoo Finance (`yfinance`). Adjusted closes make stock returns total returns,
consistent with OSEBX, which is a total-return index.

**Snapshot.** The sample end date is fixed in the config. `oilbeta fetch` writes `data/raw/prices.csv` (git-ignored; Yahoo
data is not redistributed) and `data/manifest.json` with first/last date and row count per series plus the file's SHA-256.
Re-running without `--refresh` reuses the snapshot, so committed results are reproducible from the cache.

**Factors.**
- *Oil*: Brent front-month future (`BZ=F`), in USD. History starts 2007-07-30, which sets the sample start.
- *Market*: OSEBX. Yahoo only has it from 2013-03-05, so earlier returns are taken from OSEFX, the capped fund version
  of the same index, and chained into one level series (`data.splice_market`). Returns are chained, not levels. In the
  625-day overlap the two have a daily return correlation of 0.990 and an annualised tracking difference of 2.0%.

**Alignment.** The panel keeps only dates where both the Oslo index and Brent have a price (`data.build_panel`), and
returns are computed *after* that filter. If Oslo is closed while Brent trades, the oil return to the next common date
spans both days. Computing returns per series first and intersecting dates afterwards would pair a one-day stock return
with a one-day oil return that covers a different period. `tests/test_data.py` pins this behaviour.

**Frequency.** Betas use Friday-to-Friday log returns. Oslo closes at 16:25 CET and Brent settles around six hours later,
so part of an oil move on day *t* reaches Oslo prices on *t+1*. Weekly returns dilute this (one boundary day in five) and
also the stale prices of less liquid names (Bouvet has zero-return days on 35% of its history). A week with no price
gives a missing return, never a stale fill. The event study needs daily data and handles the timing gap with a two-day
impact window.

**Sector portfolios.** Equal-weighted averages of constituents' *simple* returns, converted back to logs. At least two
members must have a return that week. No index or ETF is ever averaged with its own constituents.

**Validation and exceptions.** `data.validate` reports coverage, share of zero-return days and extreme prints for every
series. Each flag was checked by hand. Vendor errors are removed through `data_exceptions` in the config, each with a
written reason; genuine crashes stay in the sample:

| Ticker | Date | What happened |
|---|---|---|
| AKSO.OL | 2024-11-25 | Extraordinary dividend of about NOK 21 per share is missing from Yahoo's dividend history, so the ex-date shows as a −41% return. Close went 50.30 → 29.76 with no dividend recorded. |
| SOFF.OL | 2020-10-21 | Yahoo records a 0.001 split ratio on this date, during the 2020 restructuring, and the adjusted series shows a −98% one-day print. |
| BORR.OL | 2021-12-13/14 | 2:1 reverse split applied a day late: price doubles, then reverts. |
| NEL.OL | before 2014-10 | The listed company was DiaGenic (diagnostics). History trimmed. |

## 2. Oil betas

    r_i,t = α + β_mkt · m_t + β_oil · o_t + ε_t

estimated by OLS on weekly log returns. Standard errors are Newey-West (Bartlett kernel, lag
`floor(4·(T/100)^(2/9))`, small-sample factor `T/(T−k)`), implemented in `regression.newey_west_cov`.

**Why two oil betas.** The index has its own oil beta γ (0.29 over the full sample). With `m` on the right-hand side,
the share of a stock's oil exposure that runs through the market is absorbed by β_mkt.

- **Partial beta** = β_oil from the regression above.
- **Total beta**: replace `m` with `m⊥`, the residual from regressing `m` on `o` over the same sample. Because `m⊥` is
  orthogonal to `o` in-sample, the point estimate equals the one-factor oil beta; keeping `m⊥` in the regression only
  removes non-oil market noise from the residual and tightens the interval.
- **Identity**: `total = partial + β_mkt · γ` (tested to 1e-12).

The interval on the total beta treats `m⊥` as given. Since `m⊥` is exactly orthogonal to `o` in the estimation sample,
estimation error in γ does not move the point estimate; its effect on the standard error is second-order and ignored.

**Rolling estimates.** 104-week windows, at least 78 valid observations, re-orthogonalised inside each window.

**Minimum history.** 156 weeks for a full-sample beta.

## 3. Event study

**Event rule.** `z_t = o_t / σ_{t−1}`, where σ is the 250-day rolling standard deviation of Brent returns ending the day
*before* t. A shock is `|z| ≥ 2.5`. Scanning chronologically, a shock is skipped if it falls within 11 trading days of
the last accepted one, so [0,+10] windows never overlap. Events also need 270 days of history and one day of data
after the shock, so the impact window exists (later windows are missing until those days have happened). Result in the
pinned snapshot: 69 events (22 up, 47 down).

**Abnormal returns.** For each event and unit, a market model is fitted on days [−270, −21] (minimum 120 observations):

- *total*: `AR = r − (α̂ + β̂ · m⊥)`, with `m⊥` built from the estimation-window regression of `m` on `o`. Keeps the full
  oil effect, removes other market noise. For the index itself a constant-mean model is used.
- *relative*: `AR = r − (α̂ + β̂ · m)`, the classic market model: performance versus the index during the shock.

**Windows.** pre [−5,−1], impact [0,+1], drift [+2,+10]. A CAR is missing if any day in the window is missing.

**Inference.** A t-test of the mean CAR *across events for one unit*. Tests across stocks on the same day would ignore
cross-sectional correlation and are not used.

**Shock beta.** Slope of CAR_total[0,+1] on the cumulative oil return over [0,+1] across events, with White standard
errors. It is an independent estimate of the total oil beta from ~140 trading days rather than ~1,000 weeks.

**Caveat found in the data.** Before down-shocks the index is already weak (−1.4% over [−5,−1], t = −2.4). Many large
oil declines are demand scares. The event study measures co-movement around oil news, not the causal effect of oil.

## 4. Scenarios and the out-of-sample test

**Scenario table.** Total betas from the last 260 weeks. Expected move for a Brent move *s*: `exp(β · ln(1+s)) − 1`,
with the beta's 95% interval mapped the same way. That interval is about the *expected* move only.
`P(same sign) = Φ(|β · ln(1.10)| / σ_non-oil)`, where σ_non-oil is the weekly standard deviation of everything oil does
not explain, is the probability that the stock actually moves in the predicted direction in a week where Brent moves
10%. Equinor: 92%. DNB: 51%.

**Out-of-sample test.** For each event, one-factor (= total) betas are estimated on the 260 weeks that ended *before*
the event date (at least 104 observations per stock, at least 15 stocks). Prediction = beta × realised oil move over
[0,+1]. It is compared with realised CAR_total across stocks by Spearman rank correlation and by the top-minus-bottom
tercile spread, for the impact window and for the drift window. Across 63 testable events:

| | mean | t | share > 0 |
|---|---|---|---|
| Rank correlation, impact [0,+1] | +0.28 | 10.5 | 90% |
| Tercile spread, impact | +2.4% | 6.9 | 86% |
| Rank correlation, drift [+2,+10] | −0.01 | −0.3 | 46% |
| Tercile spread, drift | −0.6% | −1.0 | 43% |

Reading: the cross-section of oil sensitivity is stable enough to be estimated in advance, which is what a scenario
table needs. There is no evidence that it predicts returns after the shock.

## 3b. What kind of shock was it?

Each event is labelled by the sign of the cumulative S&P 500 log return over the same [0,+1] window as the oil move
(prices forward-filled first, so a US holiday inside the window counts as no move rather than as missing):

* same sign as oil -> **demand-type** (a growth scare or boom moves oil and equities together)
* opposite sign    -> **supply-type** (an outage or OPEC decision moves oil against the economy)

Shock betas are then estimated per unit in one regression across events, with White standard errors:

    CAR = a + a_s·S + b_demand·(oil × D) + b_supply·(oil × S)

where S and D are the supply/demand indicators. `test_equal` gives the difference and its p-value; q-values correct
across the eleven aggregates. A threshold-free version regresses CAR on the oil move *and* the S&P 500 move, so
`beta_oil_net` is the reaction to oil with global equities held fixed.

This is an ex-post label for an event study, not an identification scheme: it uses the same two days as the reaction
it explains, and the S&P 500 is a proxy for global demand news rather than a measurement of it. A structural VAR of the
Kilian type would identify the shocks properly, from oil production, global activity and inventories; it needs monthly
data this project does not have.

## 4b. Multiple testing

Sixty-three stocks tested at the 5% level produce about three "significant" oil betas even when none has any oil
exposure. Every p-value across units therefore comes with a Benjamini-Hochberg q-value (`stats/multiple.py`): with m
tests sorted so that p(1) <= ... <= p(m),

    q(i) = min over j >= i of  p(j)·m/j

A finding with q <= 0.05 belongs to a set in which at most 5% are expected to be false discoveries. The family is the
kind of unit: the 63 stocks together, the 10 sectors together. Effect on the results: the 16 significantly positive
partial betas are unchanged, the significantly negative ones fall from 17 to 13.

## 5. Regimes

One regression per unit with the oil return split in two and a t-test that the two betas are equal (HAC covariance).
The market factor is orthogonalised against the same split terms, so both betas keep the "total" interpretation.

- *Direction*: `o⁺ = max(o, 0)`, `o⁻ = min(o, 0)`.
- *Volatility*: 26-week trailing Brent volatility, lagged one week, versus its expanding median (lagged, 52-week
  burn-in). Both are known before the week starts.

Direction matters for every sector; volatility for almost none.

## 6. PCA

SVD of standardised weekly returns for the 37 stocks with at least 98% coverage over the full sample. PC1 explains 28%
and is the market (correlation 0.94 with OSEBX). PC2 (7%) separates seafood from energy and correlates 0.28 with Brent.
PCA is run on returns, not on engineered columns such as moving averages, which are all functions of the same price and
would only rediscover that.

## Robustness: another oil series, a longer sample

Two alternatives run through the same code as the baseline (Brent front-month future from Yahoo, sample from July 2007):

| Variant | Oil series | Stock prices from | Index beta | Rank corr. with baseline |
|---|---|---|---|---|
| Baseline | Brent future (Yahoo) | 2007-07-30 | 0.29 | 1.00 |
| Spot, same sample | Brent spot, EIA via FRED | 2007-07-30 | 0.25 | 0.99 |
| Spot, from 2005 | Brent spot, EIA via FRED | 2005-01-03 | 0.25 | 0.99 |

The two oil series have a 0.92 weekly return correlation over 994 weeks; the largest change in any single stock's beta
is 0.12. The longer sample matters more than the vendor: two-year windows ending before September 2008 average an index
beta of 0.23 (87 windows, range 0.15 to 0.27) against 0.51 for windows ending 2009-2013. The level today (0.21 on
average since 2015) is close to the pre-crash level, so most of the "decline" is the 2008 crash leaving the window.

FRED publishes with about a week's lag, so this runs for the pinned paper only. The inputs are cached and fingerprinted
in the manifest like any other snapshot.

## The factsheet

`oilbeta stock <TICKER> --json <path>` writes one stock's sensitivity as a versioned JSON document
(`oilbeta.stock/1`, `outputs/factsheet.py`): both betas with Newey-West intervals and p-values over the full history and
the recent window, the scenario table, the share of weekly variance oil explains, sector context where the ticker is in
the universe, and the caveats. It is the contract with [equity-research-engine](https://github.com/oscarschjelderup-sketch/equity-research-engine),
which puts it in the risk section of a case. The schema is versioned so either project can be rewritten alone; a reader
that does not recognise the major version refuses the file rather than guessing.

## Live mode

`oilbeta live` sets the sample end to yesterday (an intraday run would otherwise mix half-finished daily bars into the
sample), drops the current unfinished week from the weekly returns, and writes to `live/` so the pinned results stay
reproducible. Shocks enter once their [0,+1] window exists; windows that reach past the end of the data are missing,
not partial sums, and such events are left out of the averaged CAR paths. The download is rejected if Brent or OSEBX
stop more than ten days before the requested end, in which case the previous snapshot is served and flagged as stale.

## Tests

Two golden tests pin the results (the pinned snapshot's headline numbers, and a seeded synthetic market pushed through
the whole chain). The other 56 tests cover the config rules, the price sources and the FDR correction, and use synthetic data with known answers: recovery of planted betas, the partial/total identity, HAC against
a naive double-loop, no-look-ahead checks that tamper with future data, the holiday-alignment rule, and an
out-of-sample test that must find skill on impact and none on drift in a world built that way.
