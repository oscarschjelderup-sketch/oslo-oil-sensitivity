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

**What the document says about itself.** `session.previous_close_basis` and `session.last_basis` are
"official close" or "last 15-minute bar"; `coverage` counts how many stocks got an official reference
and an official last price, and lists the series carried forward. If the daily bars cannot be
fetched the page still works from the 15-minute bars, and says which it used.

**Not done.** The opening auction is not in the 15-minute bars either, but it only shifts volume, not
the day's move. A second vendor for intraday prices would catch a stale response directly instead of
by its timestamp; a response that is stale but carries the same last bar label cannot be told apart.
