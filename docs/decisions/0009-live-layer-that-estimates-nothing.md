# 9. A 15-minute live layer that estimates nothing

**Decision.** The monitor gains a "Today" section: 15-minute quotes for Brent, the index, USD/NOK and
every stock in the universe, candlestick charts drawn with TradingView's open-source library, and a
predicted-versus-realised panel for the current session. None of it feeds an estimate. The betas are
still weekly, still re-estimated once a day; the live layer only applies them to today's Brent move
and shows what actually happened next to it.

**Why.** The study's claim is that oil sensitivity is stable enough to plan with. A page that shows
the claim being tested in the current session — Brent is down 3%, E&P "should" be down 1.6%, is down
2.1% — is the claim made concrete. It also answers the obvious visitor question ("what is happening
now?") without pretending the study is a trading tool.

**Three choices inside it.**

*TradingView's library, not TradingView's widget.* Lightweight Charts is what TradingView draws its
own charts with, released under Apache 2.0 and served from a CDN the page is allowed to load from.
It draws *our* bars, so the previous close, the session range and the betas can sit on the same
canvas. The embedded widget is an iframe of someone else's product: it shows a price and nothing
this study measured.

*A quotes branch, not a Pages deployment.* A Pages deploy replaces the whole site; doing that every
15 minutes would rebuild the study 40 times a day to change one small file. Instead a workflow
force-pushes a single-commit orphan branch holding `quotes.json`, which the page reads from
`raw.githubusercontent.com` (CORS-enabled, five-minute CDN cache). The branch never accumulates
history; the daily job never touches it.

*One measurement window for everything.* Every move is "since Oslo Børs's previous close". Brent
trades almost around the clock, so its move over that window starts the previous evening — which is
the right comparison, because that is the oil news Oslo prices at the open. Sector moves are
equal-weighted across the members that have traded, matching how the sector betas were built.

**What the page says about itself.** Prices are 15-minute delayed (an exchange rule for free data,
not a choice); the layer refreshes every 15 minutes in trading hours; a failed refresh re-publishes
the previous document marked stale rather than leaving a gap; and intraday moves are far noisier
than the weekly relationship, so a gap between predicted and realised is the normal case. Charts use
unadjusted prices, as a trader sees them; estimates use adjusted closes. The two never mix.

**Rejected.** A full trading terminal (indicators, drawing tools, watchlists): that is a product, not
research, and it would make the numbers look less credible, not more. A paid real-time feed: the
15-minute delay costs nothing that matters to a weekly study. A server with websockets: there is
nothing to push that a static file refreshed every 15 minutes cannot carry.
