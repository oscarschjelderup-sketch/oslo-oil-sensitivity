# 8. A second price source, and what it is allowed to change

**Decision.** Price vendors sit behind a one-method interface (`data/sources.py`). Yahoo stays the
source of the study. FRED (U.S. Energy Information Administration Brent spot) is added as a *check*:
the same analysis is re-run with the spot series instead of the future, and once more with stock
prices from 2005 instead of 2007. Nothing from the check feeds back into a headline number; the
report only states how far they move.

**Why a second source.** Two questions could not be answered before:

1. *Does the answer depend on the vendor?* Yahoo's adjustments already produced four documented
   errors (decision 6). If a beta changes materially with another vendor's series, the beta was
   partly a vendor artefact.
2. *Is the early part of the sample a crisis artefact?* The Brent future on Yahoo starts in July
   2007, so the study opens straight into the autumn-2008 crash, when oil and equities fell together.
   FRED's spot series goes back to 1987 and Yahoo has the Oslo index from 2005, so the check can
   start two and a half years earlier.

**What it found.** The two oil series have a 0.92 weekly return correlation. The index beta is 0.25
on spot against 0.29 on the future, and the stock ranking is essentially identical (rank correlation
0.99, largest single change 0.12). So no conclusion rests on the vendor. The longer sample is the more
interesting result: two-year windows that end before September 2008 average a beta of 0.23, windows
ending 2009-2013 average 0.51, and the average since 2015 is 0.21. The "decline" in Oslo Børs's oil
beta is therefore largely the 2008 crash leaving the rolling window — the level today is close to the
level before it. That correction is in the report, not hidden in a test.

**Kept out of the live monitor.** FRED publishes with about a week's lag, so the check runs only for
the pinned paper.

**Mechanics worth knowing.** Adding `^GSPC` to the study meant the pinned snapshot lacked a series the
code now needed. Rather than re-downloading (which would change the snapshot's SHA-256 and every
number with it), missing series are fetched into a separate `prices_supplement.csv` for the same date
range and fingerprinted separately. The pinned file is never rewritten unless `--refresh` is asked
for. FRED also resets ordinary Python HTTPS connections, so the source uses `curl_cffi` with a browser
TLS profile.

**Not done.** A vendor with delisted companies (Refinitiv, Bloomberg, CRSP), which is the only real
fix for the survivorship bias. It costs money; the bias stays documented instead.
