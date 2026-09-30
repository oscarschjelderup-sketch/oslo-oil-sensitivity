# 10. USD/NOK as a third factor: measured, not adopted

**Decision.** The krone enters the study as a *decomposition*, not as a factor in the headline model.
Every total oil beta is split exactly into three parts — direct, through the index, through the
krone — and the report shows the split (`analysis/krone.py`, Step 2 of the report). The two-factor
model of decision 1 stays the model.

**Why it had to be measured.** Brent is priced in dollars, Oslo Børs in kroner, and the krone is an
oil currency: over the sample a 1% rise in Brent came with a 0.11% stronger krone (weekly return
correlation −0.28). A stock could therefore look oil-sensitive because the currency moved. "USD oil,
NOK stocks" had been listed among the things the study could not tell you. A limitation that costs
one regression to measure should not stay a limitation.

**Why not a three-factor model.** The question the study answers is "what happens to this stock when
Brent moves?", and for a Norwegian investor the krone's response is part of the answer, not noise
around it. A three-factor model would hand the currency's share of every oil move to the currency
term and report a smaller oil beta that answers a narrower question — what happens when Brent moves
*and the krone does not*, which never happens. The identity makes the choice cheap:

    total = direct + β_mkt · γ_mkt + β_NOK · γ_NOK

all from the same weeks, where γ are the index's and the krone's own oil betas. The direct beta *is*
the three-factor oil beta, so nothing is lost by reporting the model as a split of the total rather
than as a replacement for it.

**What it found.** For the index, 0.03 of 0.29 runs through the krone: the krone beta is significant
(p = 0.002) but it is a small coefficient times a small slope. No sector's krone part exceeds 0.03 in
absolute value, and no sector's partial beta moves by more than 0.02 once the krone is held fixed;
16 stocks keep a significantly positive direct oil beta, the same 16 as before. Where the krone does
matter it works *against* the oil beta: the dollar earners — Frontline, MPC Container Ships, Okeanis
Eco Tankers, Hafnia — gain when the krone weakens, which is when oil falls, so their small total oil
betas are a positive direct effect partly cancelled by the currency. Norwegian Air Shuttle and Norsk
Hydro lose when the krone weakens. Over the last five years the krone's own oil beta has fallen from
−0.11 to −0.07: the channel is closing, not opening.

**Mechanics.** The same weeks for every term. Yahoo lacks USD/NOK for four weeks in August 2008, so
the totals in the krone table differ from Step 2's in the third decimal; the table carries its own
`identity_gap` column, checked to machine precision there and in the tests. The market row has no
through-the-index term. q-values across stocks, as everywhere else.

**Not done.** A translation adjustment for companies that report in dollars (Equinor, the shipping
names): their krone share prices carry a mechanical USD/NOK term that the krone beta absorbs but does
not separate from any operating effect. And a model in which the krone is a *priced* factor — that
is a different study.
