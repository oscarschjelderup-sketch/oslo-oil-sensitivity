# 6. Data problems are flagged and fixed in the config, never silently in code

**Decision.** The validation step only *reports* (coverage, stale prices, extreme prints). Any removal is a line in
`configs/data_exceptions.yaml` with a date and a written reason, and the config loader rejects an exception without a
reason or for a ticker that is not in the universe. There is no winsorising, no outlier filter and no forward-fill.

**Why.** An automatic filter cannot tell a vendor error from a crash. Both of these are one-day falls of more than
40% in the raw data:

- Aker Solutions, 25 Nov 2024 (−41%): an extraordinary dividend of about NOK 21 per share that Yahoo's adjustment
  misses. The shareholder lost nothing. Keeping it would put a fake crash into an oil-service beta.
- Norwegian Air Shuttle, 14 Apr 2020 (−44%): a real collapse. Removing it would hide exactly the risk the study is about.

A rule that drops one drops the other. So each flag was checked by hand against the unadjusted prices and Yahoo's own
corporate-action records; four vendor errors were removed and every real crash stayed in.

**Also covered.** A ticker whose early history belongs to a different business is trimmed the same way (Nel was the
diagnostics company DiaGenic until October 2014).

**Given up.** It does not scale to thousands of tickers, and it depends on someone looking. For 63 stocks that is the
right trade; the report lists every intervention so a reader can disagree with any of them.
