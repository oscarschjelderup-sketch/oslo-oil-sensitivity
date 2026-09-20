# 5. Run on GitHub Actions and a static page; no server, no scheduler, no database

**Decision.** A scheduled GitHub Actions workflow rebuilds the monitor the morning after each trading day and deploys
one static HTML file (data inlined) to GitHub Pages. CI runs lint and tests on every push.

**Why.** The whole job is: download ~70 price series, run 40 seconds of numpy, write one file. That needs a cron
trigger and somewhere to put a file. Actions and Pages provide both for free, run when no laptop is on, and leave an
audit trail of every run.

**Rejected.**
- *Streamlit / Dash app*: needs a running process and cold-starts on free hosting, to serve a page that does not need
  a server. The monitor's interactivity (what-if slider, unit picker, sortable table) is plain JavaScript over a JSON
  payload.
- *Airflow / Prefect / Dagster*: orchestration for a single linear job with one schedule.
- *A database*: the data is one 5 MB table that is re-downloaded in full; the last good copy lives in the Actions cache.
- *A scheduled task on a PC*: works, and the script is still in `scripts/`, but it stops when the PC is off.

**Failure handling.** Yahoo occasionally throttles cloud IPs. The job retries three times, then falls back to the
cached snapshot and marks the page as showing older data. It only fails, and sends an email, when the page has been
stale for more than a week.

**Known limitation.** GitHub disables scheduled workflows in a public repository after 60 days without repository
activity. Any commit re-arms it.
