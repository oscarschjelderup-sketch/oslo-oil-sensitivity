# 7. Separate demand-type from supply-type oil shocks, and correct for multiple testing

Two additions that answer the two strongest objections to the headline numbers.

## Why an oil beta is not only about oil

Brent moves for two different reasons. A *supply* shock (an outage, an OPEC decision, a blockade)
moves oil against the rest of the economy. A *demand* shock (a growth scare, a pandemic, a boom)
moves oil together with everything else. A beta measured across both mixes the effect of oil with
the effect of whatever moved oil.

**Decision.** Each of the 69 shocks is labelled by one question: over the same two days as the oil
move, did the S&P 500 move with oil or against it? Shock betas are then estimated within each group,
with a test that the two differ, and a threshold-free version that simply holds the S&P 500 move
fixed in the regression.

**What it shows.** 79% of the large oil declines are demand-type against 50% of the large rises: the
falls this study measures are mostly growth scares. The index's shock beta is 0.30 in demand-type
shocks and 0.09 in supply-type ones (p = 0.002), and drops from 0.25 to 0.13 once the S&P 500 move is
held fixed. E&P is the opposite: 0.56 and 0.57, statistically indistinguishable. So energy reacts to
the oil price itself, while the rest of Oslo Børs mostly reacts to the news that moved it. That also
explains the asymmetry in decision 1 from the other side: the larger downside beta is largely the
demand shocks sitting on the downside.

**Rejected.** A structural VAR of the Kilian type, which identifies supply and demand shocks properly
from oil production, global activity and inventories. It is the right tool for a paper about oil, needs
monthly data the project does not have, and would add more machinery than the question here justifies.

**Limitation, stated in the report.** The label is ex post: it uses the same two days as the reaction
it helps explain. It explains past shocks; it does not forecast the next one. And the S&P 500 is a
proxy for global demand news, not a measurement of it.

## Why "significant at 5%" is not enough with 63 stocks

Testing 63 stocks at the 5% level produces about three false positives even if no stock has any oil
exposure. A test on synthetic data with zero true exposure confirms it: raw p-values flag around ten
of 200 stocks, Benjamini-Hochberg flags at most one.

**Decision.** Every p-value across units is reported next to a Benjamini-Hochberg q-value, and the
report, the figures and the asymmetry stars use q < 0.05. The family is the kind of unit: the 63
stocks are corrected together, the 10 sectors together.

**Effect on the results.** The 16 significantly positive partial betas survive unchanged; the count of
significantly *negative* ones falls from 17 to 13. Nothing in the headline story depends on it, which
is the point worth being able to say.

**Rejected.** Bonferroni: it controls the chance of even one false positive, which is far stricter than
this question needs and would throw away real findings.
