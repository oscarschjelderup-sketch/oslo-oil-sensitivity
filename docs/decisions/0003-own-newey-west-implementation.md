# 3. Write OLS and Newey-West in numpy instead of importing statsmodels

**Decision.** `oilbeta.stats` contains about 100 lines: OLS by least squares, a Bartlett-kernel HAC covariance with
the `floor(4·(T/100)^(2/9))` lag rule and a `T/(T−k)` correction, t-based intervals and an equality test.

**Why.** Every interval in the report rests on this covariance, and the project is meant to be explained line by line.
Forty lines that can be read beat a dependency whose defaults have to be looked up. It also keeps the estimator
layer free of pandas: arrays in, numbers out, which is what makes the rolling loop cheap enough.

**How it is kept honest.** The tests compare it with scipy on the point estimates, with White's estimator at lag zero,
with a naive double-loop implementation of the same formula, and with the classical standard error under iid errors.
A further test checks that the interval widens under autocorrelation.

**Given up.** No diagnostics beyond what is used (no Durbin-Watson, no robust regression). If the project ever needs
them, statsmodels is the right import; it is deliberately not a dependency today.
