# 12. The close is the official close, and a quote never goes back in time

**Decision.** In the 15-minute layer, every Oslo-listed series is measured from the *official* closing
price of the previous session, taken from the daily bars, and once the session is over its last price
is the official close as well. And within a session no published quote may be replaced by an older
one: if a response shows an earlier last bar for a series than the document already carries, the
published quote is kept and the document lists it.

**How it was found.** One local fetch gave exploration and production −0.45% for 2 October where the
published document said −0.56%. Comparing the two documents stock by stock, 62 of 63 were identical.
The odd one was Equinor: last price 404.4 at the 16:00 bar instead of 401.4 at the 16:15 bar. Yahoo
had answered that one request with a view of Equinor from about ten minutes before the close, two
hours after it; four fetches a day later were identical for all 66 series. A transient vendor
inconsistency, then, and nothing in the code stood in its way.

Checking which of Equinor's two prices was right showed that neither was. Euronext gives the closing
price on 2 October as 402.80 and the previous close as 401.80: the stock rose 0.25% on a day the page
said it fell 0.05%.

**What the measurement says.** Yahoo's 15-minute bars stop at the last continuous trade. They do not
contain the closing auction, which sets the official close. Over the five sessions from 28 September
to 2 October 2026, for the 63 stocks:

| | |
|---|---|
| Stocks whose last 15-minute bar equals the official close | 8% to 16% a day |
| Median gap between the two | 0.17% to 0.24% |
| Median error in the day's move when measured from bars | 0.23% to 0.32% |
| 90th percentile of that error | 0.60% to 0.79% |
| Largest error on 2 October (TGS) | −0.45% from bars, −1.56% official |
| Share of the day's volume missing from the bars, median stock | 38% to 50% |

An error of a quarter of a percent is as large as oil's whole part of a typical stock's move on a
quiet day (decision 11). The benchmark index is affected too, by up to 0.19%.

**Why the daily bars.** They carry the official close, they come from the same vendor in one extra
request, and they are what the whole study is estimated on, so the live layer and the betas now use
the same kind of price. During the session the last 15-minute bar is still the latest price there
is. The daily bar replaces it from 16:45 Oslo time, twenty minutes after the auction, when the
15-minute delay has passed; the refresh loop got one more tick, at 17:01, to fetch it. Brent and
USD/NOK have no auction and stay on their bars, aligned to Oslo's last bar (decision 11).

**Why not simply trust the newest response.** Because "newest response" and "newest data" are not the
same thing with a free feed. The rule is small: compare each series' last timestamp with the one
already published for the same session, keep the later. A series missing from a response altogether
is kept the same way. If the *index* comes back older, the whole response is rejected, because every
other number is aligned to the index's last bar; the refresh is retried, and failing that the
previous document is re-published marked stale, which was already the behaviour for a failed
download. A document from another session protects nothing.

**What the document says about itself.** Every Oslo-listed series carries `prev_close_basis` and
`last_basis`, "official close" or "last 15-minute bar", and a carried quote keeps its own;
`session.previous_close_basis` and `session.last_basis` are the index's. `coverage` counts the stocks
with an official reference and an official last price, lists the series carried forward, and lists
those whose reference came from a published document (below). If the daily bars cannot be fetched
the page still works from the 15-minute bars, and says which it used.

**Tested with real data: Monday 5 October 2026, the first full session with this code.** All 36
documents published that day were recovered from the quotes branch's history and checked against
Euronext's own historical-price download, an independent source.

| | |
|---|---|
| Documents published (ticks 09:16-17:01, the hand-off at 14:46, three refreshes after hours) | 36 |
| Series that went back in time between two published documents | none |
| Last prices equal to Euronext's official close, from 16:46 on (63 stocks and the index) | 64 of 64 |
| References equal to Friday's official close | 64 of 64 |
| Official closes that changed after 16:46 (checked at 17:01, 18:09, 20:50) | none |
| The 16:31 document, from 15-minute bars: last bar equal to the official close | 1 of 63 |
| ... median gap, and the largest (Okeanis Eco Tankers) | 0.24%, 1.32% |
| Yahoo's daily closes equal to Euronext's, 28 September to 2 October | 320 of 320 |

The guard caught a real failure. At 20:50 one stock's download failed inside yfinance ("database is
locked", the library's cache under parallel threads); its published official close was kept.

**Two things the real data showed that the design had missed.**

*Yahoo blanks a session's daily bar after midnight Oslo time.* At 23:57 Oslo Equinor's daily bar for
5 October had its close; at 00:03 it was empty, for every Oslo ticker (Brent, which settles elsewhere,
was not). An overnight refresh therefore cannot see the official close. Within the session the guard
already keeps the published one: replaying the refresh with real data at 00:08 reproduced all 64
published prices exactly. The *next morning's reference* was exposed, though: it would have fallen
back to the last 15-minute bar until Yahoo filled the row again. It now comes from the official close
this layer published the evening before (or, later in the morning, from the session's own published
reference), and `coverage.reference_from_published` lists the series that took it from there. When
Yahoo fills the row again is not measured yet. The daily study is exposed in the same way only if it
runs before then; its ten latest runs all started after 12:00 Oslo time, and the page always states
the date its prices run to.

*A carried quote lost its basis.* The 20:50 document reported 62 official closes out of 63 that were
all official, because bases were counted per fetch. They are now stated per series, as above.

A ticker missing from yfinance's parallel download is now fetched once more on its own.

**Not done.** The opening auction is not in the 15-minute bars either, but it only shifts volume, not
the day's move. Intraday quotes have no second source: Euronext's live quotes are not available to a
script, so a response that is stale but carries the same last bar label cannot be told apart. The
closing prices can be checked, and were, against Euronext's download.
