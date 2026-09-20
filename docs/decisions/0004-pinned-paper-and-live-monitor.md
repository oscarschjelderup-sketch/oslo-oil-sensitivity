# 4. Separate the pinned paper from the live monitor

**Decision.** `oilbeta run` produces the paper from a snapshot with a fixed end date; `oilbeta live` produces the
monitor from prices up to yesterday. They share every line of analysis code and nothing else.

| | Paper (`results/`) | Monitor (`live/`) |
|---|---|---|
| Sample end | fixed in `configs/study.yaml` | yesterday's close |
| Prose | written findings, checked against the snapshot | none hard-coded: every sentence is built from the numbers |
| Published as | GitHub Release `paper-<sample end>` + the Pages site | the Pages front page, rebuilt after every trading day |
| Guarded by | golden test on 22 headline numbers | end-to-end test on a synthetic market |

**Why.** A research claim needs numbers that stand still, so that "0.29" in the README means the same thing next
month. A monitor needs numbers that move. Mixing the two gives a report whose text silently goes out of date, which is
exactly what went wrong in the first draft of this project (figure titles asserting things the next data point could
overturn).

**Live-specific rules.** The current, unfinished week is dropped from the weekly returns. A new oil shock enters as
soon as its [0,+1] window exists; windows that reach past the end of the data are missing, never partial sums. If the
download fails, the last good snapshot is served and the page says so.

**Re-pinning the paper.** Change `sample.end`, run `oilbeta run --refresh`, review the report, update the pinned
numbers in `tests/integration/test_golden.py` and the README together, then publish a new release:
`gh release create paper-<end> results/report.html results/oil_sensitivity.xlsx results/dashboard.html`.
