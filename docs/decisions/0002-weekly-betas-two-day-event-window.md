# 2. Weekly returns for betas, a two-day impact window for events

**Decision.** Betas are estimated on Friday-to-Friday returns. The event study uses daily data with the impact
measured over the shock day and the next day, [0,+1].

**Why.** Oslo closes at 16:25 CET; Brent settles roughly six hours later. With daily data, part of an oil move on day
*t* can only show up in Oslo prices on *t+1*, which biases a same-day beta towards zero. Weekly returns make that
boundary one day in five and also dilute stale prices in small caps (Bouvet has a zero return on 35% of its days).
An event study cannot be weekly, so it absorbs the timing gap by widening the impact window by one day instead.

**Rejected.** A Dimson-style regression with a lagged oil term on daily data: it fixes the same problem but doubles
the parameters and makes the rolling estimates noisier. Lagged correlations at longer horizons were rejected outright:
in markets this liquid they are a multiple-testing exercise, and the out-of-sample drift test confirms there is nothing
there (rank correlation −0.01, t = −0.3).

**Check.** The shock beta, estimated only from the ~140 shock days, agrees with the weekly beta (correlation 0.89
across stocks). Two methods with different frequencies and different samples land on the same cross-section.
