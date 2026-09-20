# 1. Report two oil betas: partial and total

**Decision.** Every stock and sector gets a *partial* oil beta (the index enters the regression as it is) and a
*total* oil beta (the index is first stripped of its own oil component). The total beta is the headline number.

**Why.** Oslo Børs is itself oil-heavy: the benchmark's own oil beta is 0.29 over the sample. A standard two-factor
regression therefore hides part of every stock's oil exposure inside its market beta. DNB's partial oil beta is −0.07,
which is the right answer to "does DNB carry oil risk beyond the index?" and the wrong answer to "what happens to DNB
when Brent falls 10%?". That second question is what a risk section needs, and its answer is +0.29.

**How.** `total = partial + β_mkt × γ`, where γ is the index's own oil beta. Because the orthogonalised index is
uncorrelated with oil in-sample, the total beta equals the one-factor oil beta; keeping the residual index in the
regression only removes noise and tightens the interval. The identity is unit-tested to machine precision.

**Given up.** The total beta attributes to oil everything that moves with oil, including global demand news that
moves oil and equities together. The report says so, and the event study shows where it bites (down-shocks).
