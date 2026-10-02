# 11. A split with a range, not a forecast

**Decision.** The monitor's "Today" panel no longer sets one number against another under the words
"predicted" and "realised". It splits each move exactly into three parts — oil, the market beyond
oil, the unit's own news — draws the range in which the unit ends on 80% of days, and says up front
how much the oil beta can tell on a day of this size. The oil part is the same number as before;
what changed is what the page claims for it.

**What prompted it.** A reader opened the "Biggest movers" tab on a day Brent fell 1.6% and asked why
every prediction was so far off: predictions of a few tenths of a percent beside moves of two to four
percent. The question was fair and the fault was the page's. "Predicted" promised a forecast of the
stock's day. The number was only oil's share of it.

**What the measurements say** (pinned snapshot; `analysis/attribution.py`).

- For the typical stock oil accounts for 1.3% of weekly variance over the last five years, and oil
  plus the index for 15%. The rest is the company's own news, which moves the typical stock between
  −2.1% and +2.2% on 80% of days. On the day in question Brent's part was at most half a percent for
  any stock.
- Sorting by the size of the move selects the stocks with the most news of their own. "Biggest
  movers" is by construction where oil's part is smallest relative to the move.
- How well betas known beforehand rank stocks depends almost entirely on how far Brent moved. Over
  4,102 trading days since 2009:

  | Brent move, trailing σ | Days | Typical move | Mean rank correlation | Ranked the right way |
  |---|---|---|---|---|
  | under 0.5 | 1,936 | 0.5% | +0.03 | 54% |
  | 0.5 to 1 | 1,124 | 1.6% | +0.11 | 67% |
  | 1 to 1.5 | 561 | 2.6% | +0.13 | 72% |
  | 1.5 to 2.5 | 356 | 3.9% | +0.21 | 78% |
  | 2.5 or more | 125 | 7.9% | +0.27 | 84% |

  The last row agrees with the event study's +0.28 on de-clustered shocks. The day that prompted the
  question was a 0.5σ day: close to a coin flip, as the first row says it should be.

**Why not a better prediction.** There is none to be had from these factors. The two-factor model is
the study's model, and after oil and the index about 85% of a typical stock's variance is left. A
sector factor or a stock's own lagged return would raise the explained share, but they answer another
question than this study's. What can be made better is the claim: an exact split, a range and a
yardstick for the day.

**Three choices inside it.**

*The index move is used, and that is not a forecast.* Brent's move `x` and the index's move `m` are
both the ones that happened. With the scenario betas (last 260 weeks) and the index's own oil beta γ:

    oil = β_total · x        market = β_mkt · (m − γ · x)        own = the rest

The first term is everything oil did, through the index too; the second is what the rest of the
market did. The parts add up to the realised move by construction.

*The range is empirical and covers a full day.* It is the 10th and 90th percentile of each unit's
daily residual over the same 260 weeks, computed with the weekly betas. No normality assumption (the
fat tails are in it), exactly 80% coverage in sample, and a statement anyone can check against the
price history. It describes close-to-close days, so early in a session it is too wide; the page says
so.

*The yardstick is out-of-sample.* The table above uses betas from weeks that ended before each week
began, and volatility up to the day before. A test rewrites the future and checks that no earlier row
moves.

**A second fault, found while building this.** Every move was measured from Oslo's previous close,
but Brent's move ran to Brent's own latest bar. During the session that is the same moment. After
16:25 it is not: on 2 October Brent stood 1.85% below Oslo's previous close when Oslo stopped, then
rallied, and by early evening the page set Friday's stock moves against a Brent move of +0.70%. The
window has to end where Oslo ended as well as start where Oslo started, so the quotes document now
carries Brent's and USD/NOK's move up to Oslo's latest bar (`change_oslo`) beside the live one, the
split uses it, and the note says how far Brent has moved since. With the right oil move and the index
in the split, the energy sectors' Friday is explained almost to the basis point: exploration and
production −1.00% from oil, +0.55% from the market, −0.45% realised.

**What the live layer still does not do.** It estimates nothing (decision 9). The betas, the ranges
and the yardstick table come from the daily job. The page multiplies, subtracts, and computes one
descriptive statistic of the current cross-section: the rank correlation between oil's part and the
realised moves, and how many stocks sit inside their range.

**Rejected.** Dropping the "Biggest movers" tab: it is what a visitor wants to see, and with the
split it shows that those moves are own news. Hiding oil's part when it is small: it is the study's
subject, and its smallness on a quiet day is the finding. A normal band from the weekly residual:
daily returns have fat tails, and an empirical quantile needs no assumption. USD/NOK as a fourth
part: decision 10 measured it at 0.03 for the index; it would add a column and explain nothing.
