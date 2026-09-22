# Decisions

Short notes on choices that someone reading the code would otherwise have to guess at. Each one says what was
decided, why, and what was given up.

| # | Decision |
|---|---|
| [1](0001-partial-and-total-oil-beta.md) | Report two oil betas: partial and total |
| [2](0002-weekly-betas-two-day-event-window.md) | Weekly returns for betas, a two-day impact window for events |
| [3](0003-own-newey-west-implementation.md) | Write OLS and Newey-West in numpy instead of importing statsmodels |
| [4](0004-pinned-paper-and-live-monitor.md) | Separate the pinned paper from the live monitor |
| [5](0005-github-actions-as-the-run-model.md) | Run on GitHub Actions and a static page; no server, no scheduler, no database |
| [6](0006-flags-never-silent-fixes.md) | Data problems are flagged and fixed in the config, never silently in code |
| [7](0007-demand-and-supply-shocks.md) | Split oil shocks into demand-type and supply-type; correct for multiple testing |
| [8](0008-second-price-source.md) | Add a second price source as a check, not as an input |
| [9](0009-live-layer-that-estimates-nothing.md) | A 15-minute live layer that estimates nothing |
