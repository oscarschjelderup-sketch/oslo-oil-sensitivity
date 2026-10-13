# 13. The daily study runs when the day is over, started by the loop

**Decision.** The quotes loop starts the daily study the moment the session is over and today's
official closes are published, and tells it to include today. The study's own schedule moves from
05:30 UTC to 17:30 UTC and becomes a fallback that skips itself when the loop has already run it.
The loop also gets five more kick-start schedules in the last hour before the open.

**What was measured.** Two things, both on real days.

*The morning schedule could never have been on time, and if it ever were it would lose a day.*
GitHub ran the 05:30 UTC schedule between 13:16 and 14:08 Oslo time on each of the five trading
days from 6 to 10 October 2026, five to eight hours late, and on 6 October had not run it at all by
14:04. Yahoo, meanwhile, blanks a session's daily bar for every Oslo ticker from midnight Oslo time
until mid-morning: on 5 October Equinor's close was there at 23:57 and gone at 00:03, and on the 6th
the quotes loop had to take its references from its own published document until 10:46. A study run
on time at 07:30 would have found no bar for the day before. The study only ever worked because the
schedule was late.

*The loop's own kick-starts miss the open.* Its four early schedules (01:17 to 07:17 UTC) produced a
first run between 09:18 and 09:37 Oslo time on every trading day from 6 to 12 October, one to two
ticks after the first one at 09:01. On 13 October none of them had fired by 09:44 and the loop was
started by hand.

**Why the evening.** After the closing auction and the 15-minute delay, the day's data is final and,
until midnight, present. The loop knows that moment exactly: its 17:01 tick publishes the official
closes, and `next-tick` then answers "done". Starting the study there means the betas, the event
study and the ranges on the page include the session that just ended, instead of the one before it,
and the page says "Prices through" the right date by the evening. The study takes a flag,
`--through-today`, because by default `oilbeta live` ends the sample at yesterday so that an
intraday run never mixes a half-finished daily bar into the sample; after the auction that reason
is gone.

**Guards.** Only the run that started before the close and saw the session end dispatches the study;
post-close refreshes from the safety schedules do not, so the study runs once. It is dispatched only
when the published document is today's and its last prices are official closes; otherwise the loop
says so and leaves the study to the fallback. The fallback checks, before building, whether a
dispatched study already succeeded today, and includes today's close only when it runs after the
auction and before midnight. A push still rebuilds with yesterday's data, as before, so a code
change never publishes a half day.

**Kick-starts.** Five schedules between 06:32 and 07:17 UTC join the three overnight ones. Each is
best-effort, but the concurrency group collapses duplicates, a run that starts early sleeps until
09:01, and the measured lateness of the early ones (hours, or never) argued for more draws close to
the open rather than fewer. What they deliver is measured in the loop's run list, like the last ones
were.

**Not done.** None of this makes GitHub's scheduler reliable; it stacks the odds. A run that starts
after 09:01 still loses the ticks before it. The study's first evening run is the test of the dispatch
itself; the loop's log says "daily study started with today's close" when it has happened.
